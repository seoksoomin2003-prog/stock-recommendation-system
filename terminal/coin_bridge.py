"""The coin part.  Two sources, the first one found is used.

Design: reports/CRYPTO_ENGINE_DESIGN_2026_11_21.md.

1. REGISTERED: the files the predictor of the user's other project, horizon_bot_beta, already writes (the registered score alpha of
   each coin at a four-hour close, the four-hour bars and the funding rates).  Read only: nothing is written there, and the book
   values of that project's paper ledgers are never read, since their verdicts are still to come.
2. SIMPLE: on a machine without those files, the exchange's public market data (terminal/coin_source.py) and a plain rank from the
   same three signals, each weighing the same.  It is not the registered score, it has no trained weights and no expected return,
   and it was never tested on returns: the screen says so wherever it is shown.

No order exists here in either case.

What the score is, and is not: alpha is the expected return over the next seven days above the median of the thirty largest
perpetuals, from three signals (funding, low volatility, low beta).  It is a rank among those coins.  It does not say a coin will
rise, it was measured on perpetuals with funding (a spot holder gets none), and its verdict is pending.
"""
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

ENV = "HORIZON_BOT_DIR"
PUBLIC_OFF = "QPP_COIN_PUBLIC_OFF"          # set to 1 and the exchange is never asked: without the predictor's files the screen says so
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
SIMPLE_NOTE = ("지금 보이는 순위는 등록된 점수(α)가 아닙니다. 이 기기에 horizon_bot_beta 예측기의 파일이 없어, 거래소 공개 시세로 같은 세 신호(자금조달비, 변동성, 베타)의 순위를 "
               "같은 비중으로 합친 간이 순위입니다. 학습된 가중치와 기대수익이 없고, 수익으로 시험한 적이 없습니다.")
CAVEATS = ["이 점수는 대상 코인끼리의 순위입니다. 오를지 내릴지를 말하지 않으며, 시장 전체가 내리면 순위가 높은 코인도 내립니다.",
           "바이낸스 USDT 무기한 선물 기준으로 잰 값입니다. 현물을 사는 사람은 자금조달비를 받지 못해, 점수의 근거 일부가 해당하지 않습니다.",
           "판정 전입니다. 과거 자료에서 점수 1위 코인 하나를 산 시험은 -62.7%였고(같은 기간 대상 평균 -79.2%, 비트코인 +40.2%), 앞으로의 기록으로 판정합니다.",
           "주문 기능은 없습니다. 투자 자문이 아닙니다."]
SIMPLE_CAVEATS = [SIMPLE_NOTE, CAVEATS[0], CAVEATS[1],
                  "등록된 점수조차 과거 자료에서 1위 코인 하나를 산 시험이 -62.7%였습니다(같은 기간 대상 평균 -79.2%, 비트코인 +40.2%). 간이 순위는 그보다 근거가 약합니다.", CAVEATS[3]]


def root() -> Path:
    return Path(os.environ.get(ENV) or DEFAULT) / FILES


def unit_of(symbol: str) -> float:
    """How many coins one unit of the contract stands for: 1000SHIBUSDT is quoted per thousand, 1000000MOGUSDT per million."""
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    digits = len(base) - len(base.lstrip("0123456789"))
    lead = base[:digits]
    return float(lead) if lead and lead.startswith("1") and set(lead[1:]) <= {"0"} and len(lead) >= 4 else 1.0


def coin_of(symbol: str) -> str:
    """BTCUSDT -> BTC, 1000SHIBUSDT -> SHIB, 1000000MOGUSDT -> MOG (the leading 1000... is the contract's unit, not the name)."""
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    return base[len(str(int(unit_of(symbol)))):] if unit_of(symbol) > 1 else base


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


def simple_rank(fund: Dict[str, Optional[float]], sig: Dict[str, Optional[float]], bet: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    """The plain rank of the SIMPLE source: for each signal the share of coins the coin beats from the favoured (low) end, the three
    shares averaged with the same weight.  A coin needs two of the three.  0 to 1, higher is better."""
    def share(values: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
        have = sorted(v for v in values.values() if v is not None)
        if len(have) < 2:
            return {s: None for s in values}
        return {s: None if v is None else (sum(1 for x in have if x > v) + 0.5 * (sum(1 for x in have if x == v) - 1)) / (len(have) - 1) for s, v in values.items()}
    parts = [share(fund), share(sig), share(bet)]
    out = {}
    for s in fund:
        got = [p[s] for p in parts if p.get(s) is not None]
        out[s] = sum(got) / len(got) if len(got) >= 2 else None
    return out


def _predictor(folder: Path) -> Dict[str, Any]:
    """The newest scored close of the predictor and the arrays behind it, or the reason there is none."""
    if not folder.is_dir():
        return {"reason": f"예측기 폴더가 없습니다: {folder}."}
    try:
        rows = _alpha_rows(folder / "shadow_alpha.jsonl")
    except OSError:
        rows = []
    if not rows:
        return {"reason": "예측기의 점수 파일(shadow_alpha.jsonl)이 없거나 비어 있습니다."}
    close_ms = max(int(r["close_ms"]) for r in rows)
    scored = {r["symbol"]: r for r in rows if int(r["close_ms"]) == close_ms}
    if len(scored) < MIN_COINS:
        return {"reason": f"예측기의 마지막 마감에 점수가 {len(scored)}개뿐입니다."}
    bars = {s: _closed(folder, s, close_ms) for s in scored}
    return {"close_ms": close_ms, "alpha": {s: float(r["alpha"]) for s, r in scored.items()}, "version": next(iter(scored.values())).get("version"),
            "bars": bars, "funding": {s: _funding(folder, s, close_ms) for s in scored}}


def read(now_ms: Optional[int] = None, folder: Optional[Path] = None, base: Optional[Path] = None, public: Optional[Any] = None) -> Dict[str, Any]:
    """The coins of the newest close and the market around them.  The predictor's files when they exist; otherwise, when ``base``
    (the terminal's own folder) is given, the exchange's public data through ``public`` (terminal.coin_source.load).
    UNAVAILABLE says why."""
    folder = Path(folder) if folder else root()
    now_ms = int(now_ms if now_ms is not None else time.time() * 1000)
    note = {"caveats": CAVEATS, "cost_round_trip": COST}
    got = _predictor(folder)
    if "reason" not in got:
        return _build(got["close_ms"], got["alpha"], got["bars"], got["funding"], now_ms,
                      {**note, "mode": "REGISTERED", "version": got["version"], "source": "horizon_bot_beta 예측기 (바이낸스 USDT 무기한 선물 공개 시세)"})
    why = got["reason"] + f" 폴더가 다른 곳에 있으면 .env에 {ENV}=경로 를 적으세요."
    if base is None or os.environ.get(PUBLIC_OFF, "").strip() not in ("", "0"):
        return {"status": "UNAVAILABLE", "reason": why, "source": "horizon_bot_beta 예측기", **note}
    if public is None:
        from terminal import coin_source
        public = coin_source.load
    doc = public(Path(base), now_ms)
    if not doc.get("arrays"):
        return {"status": "UNAVAILABLE", "reason": f"예측기 파일이 없고, 거래소 공개 시세도 받지 못했습니다({doc.get('error') or '응답 없음'}). 인터넷 연결을 확인하고 잠시 뒤 다시 열어 보세요.",
                "source": "바이낸스 USDT 무기한 선물 공개 시세", **note}
    close_ms = int(doc["close_ms"])
    bars = {s: b[b[:, 0] + BAR_MS <= close_ms] for s, b in doc["arrays"]["bars"].items()}
    funding = {}
    for s in bars:
        f = doc["arrays"]["funding"].get(s)
        f = f[f[:, 0] <= close_ms] if f is not None and len(f) else None
        funding[s] = {"last": None, "week": None} if f is None or not len(f) else {"last": float(f[-1, 1]), "week": float(f[-21:, 1].mean())}
    return _build(close_ms, None, bars, funding, now_ms,
                  {"caveats": SIMPLE_CAVEATS, "cost_round_trip": COST, "mode": "SIMPLE", "version": None, "mode_note": SIMPLE_NOTE,
                   "source": "바이낸스 USDT 무기한 선물 공개 시세 (터미널이 직접 받음, 최근 거래대금 상위 30개)", "fetch_error": doc.get("error")})


def _build(close_ms: int, alpha: Optional[Dict[str, float]], bars: Dict[str, Optional[np.ndarray]], fund: Dict[str, Dict[str, Optional[float]]], now_ms: int,
           note: Dict[str, Any]) -> Dict[str, Any]:
    """Rows and market from one close.  ``alpha`` None: no registered score, the coins are ordered by ``simple_rank``."""
    symbols = list(alpha) if alpha is not None else list(bars)
    age = (now_ms - close_ms) / 3600000
    closes = {s: b[:, 4] for s, b in bars.items() if b is not None and len(b) >= 2}
    span = max((len(c) for c in closes.values()), default=0)
    rets = {s: np.concatenate([np.full(span - len(c), np.nan), np.concatenate([[np.nan], np.diff(np.log(c))])]) for s, c in closes.items()}
    stack = np.vstack(list(rets.values())) if rets else np.zeros((0, 0))
    have = np.isfinite(stack).sum(axis=0) if stack.size else np.array([])
    market = np.where(have > 0, np.nansum(stack, axis=0) / np.maximum(have, 1), np.nan) if stack.size else np.array([])      # the equal-weight mean of the coins
    sig = {s: (sigma(rets[s]) if s in rets else None) for s in symbols}
    bet = {s: (beta(rets[s], market) if s in rets else None) for s in symbols}
    last_f = {s: (fund.get(s) or {}).get("last") for s in symbols}
    plain = simple_rank(last_f, sig, bet) if alpha is None else {}
    if alpha is None:
        symbols = [s for s in symbols if plain.get(s) is not None]
        ranked = sorted(symbols, key=lambda s: (-plain[s], s))
    else:
        ranked = sorted(symbols, key=lambda s: (-alpha[s], s))
    n = len(ranked)
    if n < MIN_COINS:
        return {"status": "UNAVAILABLE", "reason": f"점수를 낼 수 있는 코인이 {n}개뿐입니다.", **note}

    def change(c: Optional[np.ndarray], bars_back: int) -> Optional[float]:
        return None if c is None or len(c) <= bars_back or not c[-1 - bars_back] else float(c[-1] / c[-1 - bars_back] - 1)

    def above_ma(c: Optional[np.ndarray]) -> Optional[bool]:
        daily = None if c is None else c[::-1][::BARS_PER_DAY][::-1]
        return None if daily is None or len(daily) < MA_DAYS else bool(daily[-1] > daily[-MA_DAYS:].mean())
    out = []
    for k, s in enumerate(ranked):
        c, f = closes.get(s), fund.get(s) or {}
        a = None if alpha is None else alpha[s]
        out.append({"symbol": s, "coin": coin_of(s), "name": NAMES_KO.get(coin_of(s)), "per_thousand": s.startswith("1000"), "rank": k + 1, "of": n,
                    "score": round(100 * (n - 1 - k) / (n - 1), 1) if alpha is not None else round(100 * plain[s], 1), "alpha": a, "beats_cost": None if a is None else a > COST,
                    "price": None if c is None else float(c[-1]), "change_1d": change(c, BARS_PER_DAY), "change_7d": change(c, 7 * BARS_PER_DAY), "change_30d": change(c, 30 * BARS_PER_DAY),
                    "sigma_day": None if sig[s] is None else sig[s] * math.sqrt(BARS_PER_DAY), "sigma_place": _place(sig, s), "beta": bet[s], "beta_place": _place(bet, s),
                    "funding": f.get("last"), "funding_week": f.get("week"), "funding_year": None if f.get("last") is None else f["last"] * FUNDING_PER_YEAR,
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
             "note": "참고 표시입니다. horizon_bot_beta의 시험(v17)에서 시장 방향 예측은 실제와 맞지 않았습니다(상관 -0.08). 이 값으로 오를지 내릴지를 읽지 마세요."}
    return {"status": "STALE" if age > STALE_HOURS else "REAL", "close_ms": close_ms, "age_hours": round(age, 1), "stale_after_hours": STALE_HOURS, "horizon_days": 7, "rows": out, "market": state, **note}
