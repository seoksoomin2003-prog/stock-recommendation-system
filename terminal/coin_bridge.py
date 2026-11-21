"""The coin part: a read-only bridge to the predictor of the user's other project, horizon_bot_beta.

Design: reports/CRYPTO_ENGINE_DESIGN_2026_11_21.md.  The terminal makes no coin score of its own and fetches no coin data.  It reads
the files that project's predictor already writes (the registered score alpha of each coin at a four-hour close, the four-hour bars
and the funding rates) and shows them.  Nothing is written there, no order exists here, and the book values of that project's paper
ledgers are never read: their verdicts are still to come.

What the score is, and is not: alpha is the expected return over the next seven days above the median of the thirty largest
perpetuals, from three signals (funding, low volatility, low beta).  It is a rank among those coins.  It does not say a coin will
rise, it was measured on perpetuals with funding (a spot holder gets none), and its verdict is pending.
"""
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ENV = "HORIZON_BOT_DIR"
DEFAULT = Path.home() / "Projects" / "horizon_bot_beta"
FILES = Path("runtime") / "predictor"
BAR_MS = 4 * 3600 * 1000
BARS_PER_DAY = 6
STALE_HOURS = 9.0              # two four-hour closes without a new score: the predictor stopped or the machine slept
COST = 0.0020                  # the round trip that project registered for a market order (v18)
HALF_LIFE, VOL_MIN = 84, 42    # research/risk.py of that project: two weeks of four-hour bars
BETA_WINDOW, BETA_MIN = 360, 180
MA_DAYS = 200
FUNDING_PER_YEAR = 3 * 365
MIN_COINS = 10
NAMES_KO = {"BTC": "비트코인", "ETH": "이더리움", "XRP": "리플", "SOL": "솔라나", "BNB": "비앤비", "DOGE": "도지코인", "ADA": "에이다", "TRX": "트론", "AVAX": "아발란체", "LINK": "체인링크",
            "DOT": "폴카닷", "BCH": "비트코인캐시", "LTC": "라이트코인", "SHIB": "시바이누", "ATOM": "코스모스", "ETC": "이더리움클래식", "XLM": "스텔라루멘", "NEAR": "니어프로토콜",
            "UNI": "유니스왑", "APT": "앱토스", "FIL": "파일코인", "AAVE": "에이브", "SUI": "수이", "ARB": "아비트럼", "OP": "옵티미즘", "AXS": "엑시인피니티", "DASH": "대시", "ALGO": "알고랜드", "ZEC": "지캐시", "HBAR": "헤데라", "ICP": "인터넷컴퓨터", "SAND": "샌드박스",
            "MANA": "디센트럴랜드", "XMR": "모네로", "EOS": "이오스", "GALA": "갈라", "APE": "에이프코인", "BAT": "베이직어텐션토큰", "AR": "아르위브"}
CAVEATS = ["이 점수는 대상 코인끼리의 순위입니다. 오를지 내릴지를 말하지 않으며, 시장 전체가 내리면 순위가 높은 코인도 내립니다.",
           "바이낸스 USDT 무기한 선물 기준으로 잰 값입니다. 현물을 사는 사람은 자금조달비를 받지 못해, 점수의 근거 일부가 해당하지 않습니다.",
           "판정 전입니다. 과거 자료에서 점수 1위 코인 하나를 산 시험은 -62.7%였고(같은 기간 대상 평균 -79.2%, 비트코인 +40.2%), 앞으로의 기록으로 판정합니다.",
           "주문 기능은 없습니다. 투자 자문이 아닙니다."]


def root() -> Path:
    return Path(os.environ.get(ENV) or DEFAULT) / FILES


def coin_of(symbol: str) -> str:
    """BTCUSDT -> BTC, 1000SHIBUSDT -> SHIB (the contract is quoted per thousand)."""
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    return base[4:] if base.startswith("1000") else base


def _alpha_rows(path: Path) -> List[Dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue                    # a line cut by a crash is skipped, the lines around it stand
        if isinstance(r, dict) and r.get("symbol") and r.get("close_ms") is not None and r.get("alpha") is not None:
            out.append(r)
    return out


def _closed(folder: Path, symbol: str, close_ms: int) -> Optional[np.ndarray]:
    """The symbol's bars that had closed by ``close_ms``: (open time, open, high, low, close, volume)."""
    try:
        bars = np.load(folder / f"{symbol}.bars.npy", allow_pickle=False)
    except (OSError, ValueError):
        return None
    if bars.ndim != 2 or bars.shape[1] < 5:
        return None
    return bars[bars[:, 0] + BAR_MS <= close_ms]


def _funding(folder: Path, symbol: str, close_ms: int) -> Dict[str, Optional[float]]:
    try:
        f = np.load(folder / f"{symbol}.funding.npy", allow_pickle=False)
        f = f[f[:, 0] <= close_ms]
    except (OSError, ValueError, IndexError):
        return {"last": None, "week": None}
    if not len(f):
        return {"last": None, "week": None}
    return {"last": float(f[-1, 1]), "week": float(f[-21:, 1].mean())}


def sigma(returns: np.ndarray) -> Optional[float]:
    """Per-bar volatility as that project measures it: an exponentially weighted mean of squared returns, mean taken as zero."""
    r = returns[np.isfinite(returns)]
    if len(r) < VOL_MIN:
        return None
    w = 0.5 ** (np.arange(len(r))[::-1] / HALF_LIFE)
    return float(math.sqrt((w * r ** 2).sum() / w.sum()))


def beta(coin: np.ndarray, market: np.ndarray) -> Optional[float]:
    both = np.isfinite(coin) & np.isfinite(market)
    x, y = market[both][-BETA_WINDOW:], coin[both][-BETA_WINDOW:]
    if len(x) < BETA_MIN or x.var() <= 0:
        return None
    return float(((x * y).mean() - x.mean() * y.mean()) / x.var())


def _place(values: Dict[str, Optional[float]], symbol: str) -> Optional[int]:
    """Where the coin stands from the low end: 1 is the lowest (for all three signals the low end is the favoured one)."""
    have = sorted(v for v in values.values() if v is not None)
    return None if values.get(symbol) is None else 1 + sum(1 for v in have if v < values[symbol])


def read(now_ms: Optional[int] = None, folder: Optional[Path] = None) -> Dict[str, Any]:
    """The newest close the predictor scored, every coin of it, and the market around it.  UNAVAILABLE says why."""
    folder = Path(folder) if folder else root()
    note = {"source": "horizon_bot_beta 예측기 (바이낸스 USDT 무기한 선물 공개 시세)", "caveats": CAVEATS, "cost_round_trip": COST}
    if not folder.is_dir():
        return {"status": "UNAVAILABLE", "reason": f"예측기 폴더가 없습니다: {folder}. 폴더가 다른 곳에 있으면 .env에 {ENV}=경로 를 적으세요.", **note}
    try:
        rows = _alpha_rows(folder / "shadow_alpha.jsonl")
    except OSError:
        rows = []
    if not rows:
        return {"status": "UNAVAILABLE", "reason": "예측기의 점수 파일(shadow_alpha.jsonl)이 없거나 비어 있습니다. 그 프로젝트에서 ./run_predictor.sh start 로 예측기를 켜야 합니다.", **note}
    close_ms = max(int(r["close_ms"]) for r in rows)
    scored = {r["symbol"]: r for r in rows if int(r["close_ms"]) == close_ms}
    if len(scored) < MIN_COINS:
        return {"status": "UNAVAILABLE", "reason": f"마지막 마감에 점수가 {len(scored)}개뿐입니다.", **note}
    now_ms = int(now_ms if now_ms is not None else __import__("time").time() * 1000)
    age = (now_ms - close_ms) / 3600000
    bars = {s: _closed(folder, s, close_ms) for s in scored}
    closes = {s: b[:, 4] for s, b in bars.items() if b is not None and len(b) >= 2}
    span = max((len(c) for c in closes.values()), default=0)
    rets = {s: np.concatenate([np.full(span - len(c), np.nan), np.concatenate([[np.nan], np.diff(np.log(c))])]) for s, c in closes.items()}
    stack = np.vstack(list(rets.values())) if rets else np.zeros((0, 0))
    have = np.isfinite(stack).sum(axis=0) if stack.size else np.array([])
    market = np.where(have > 0, np.nansum(stack, axis=0) / np.maximum(have, 1), np.nan) if stack.size else np.array([])      # the equal-weight mean of the scored coins
    sig = {s: (sigma(rets[s]) if s in rets else None) for s in scored}
    bet = {s: (beta(rets[s], market) if s in rets else None) for s in scored}
    fund = {s: _funding(folder, s, close_ms) for s in scored}
    last_f = {s: fund[s]["last"] for s in scored}
    ranked = sorted(scored.values(), key=lambda r: (-float(r["alpha"]), r["symbol"]))
    n = len(ranked)

    def change(c: Optional[np.ndarray], bars_back: int) -> Optional[float]:
        return None if c is None or len(c) <= bars_back or not c[-1 - bars_back] else float(c[-1] / c[-1 - bars_back] - 1)

    def above_ma(c: Optional[np.ndarray]) -> Optional[bool]:
        daily = None if c is None else c[::-1][::BARS_PER_DAY][::-1]
        return None if daily is None or len(daily) < MA_DAYS else bool(daily[-1] > daily[-MA_DAYS:].mean())
    out = []
    for k, r in enumerate(ranked):
        s, c = r["symbol"], closes.get(r["symbol"])
        a = float(r["alpha"])
        out.append({"symbol": s, "coin": coin_of(s), "name": NAMES_KO.get(coin_of(s)), "per_thousand": s.startswith("1000"), "rank": k + 1, "of": n,
                    "score": round(100 * (n - 1 - k) / (n - 1), 1) if n > 1 else None, "alpha": a, "beats_cost": a > COST,
                    "price": None if c is None else float(c[-1]), "change_1d": change(c, BARS_PER_DAY), "change_7d": change(c, 7 * BARS_PER_DAY), "change_30d": change(c, 30 * BARS_PER_DAY),
                    "sigma_day": None if sig[s] is None else sig[s] * math.sqrt(BARS_PER_DAY), "sigma_place": _place(sig, s), "beta": bet[s], "beta_place": _place(bet, s),
                    "funding": fund[s]["last"], "funding_week": fund[s]["week"], "funding_year": None if fund[s]["last"] is None else fund[s]["last"] * FUNDING_PER_YEAR,
                    "funding_place": _place(last_f, s), "above_200d": above_ma(c)})
    btc = closes.get("BTCUSDT")
    daily = None if btc is None else btc[::-1][::BARS_PER_DAY][::-1]
    known = [x["above_200d"] for x in out if x["above_200d"] is not None]
    funds = [x["funding"] for x in out if x["funding"] is not None]
    state = {"btc_price": None if btc is None else float(btc[-1]), "btc_change_7d": change(btc, 7 * BARS_PER_DAY), "btc_change_30d": change(btc, 30 * BARS_PER_DAY),
             "btc_vs_200d": None if daily is None or len(daily) < MA_DAYS else float(daily[-1] / daily[-MA_DAYS:].mean() - 1),
             "btc_from_high_1y": None if daily is None or len(daily) < 30 else float(daily[-1] / daily[-365:].max() - 1),
             "above_200d": sum(1 for x in known if x), "above_200d_of": len(known), "funding_mean": float(np.mean(funds)) if funds else None,
             "falling_7d": sum(1 for x in out if (x["change_7d"] or 0) < 0), "coins": n,
             "note": "참고 표시입니다. 그 프로젝트의 시험(v17)에서 시장 방향 예측은 실제와 맞지 않았습니다(상관 -0.08). 이 값으로 오를지 내릴지를 읽지 마세요."}
    return {"status": "STALE" if age > STALE_HOURS else "REAL", "close_ms": close_ms, "age_hours": round(age, 1), "stale_after_hours": STALE_HOURS, "version": ranked[0].get("version"),
            "horizon_days": 7, "rows": out, "market": state, **note}
