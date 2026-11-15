"""The forecast layer FC-1: what the program says in numbers about one stock, written down daily and scored.  Rules: reports/QSF_FORECAST_PROTOCOL.md.

A price range comes from exponentially weighted volatility (RiskMetrics) whose width is set by how far past moves went against their
own forecast.  Expected excess return and the chance of beating half the universe follow the Grinold rule (IC x volatility x z); every
evidence-based IC is zero today, so those read 0 and 50%, and an assumed IC is recorded beside them under that name.  Every number is
about a single stock, not a portfolio.  The historical check runs once.  Nothing here changes the live score, a limit or a stop.
"""
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from terminal.qsf import kr_forward as kf
from terminal.qsf.ledger import Ledger

VERSION = "FC-1"
PROTOCOL = "reports/QSF_FORECAST_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_FORECAST_TEST.json"
FOLDERS = {"KR": Path("research_data") / "forecast_kr", "US": Path("research_data") / "forecast_us"}
VIEW = Path("data") / "qsf" / "forecast_status.json"
KR_PRICES = Path("research_data") / "krx" / "prices.npz"
US_PRICES = Path("data") / "qsf" / "research" / "prices15y_pit.npz"
FIRST = "2026-11-13"            # the newest ledger session on the day the protocol was written; nothing earlier is filled in
WINDOW = 480                    # sessions of adjusted closes read back, the day itself included
HORIZONS = (5, 20)
LAMBDA = {5: 0.94, 20: 0.97}    # RiskMetrics: daily and monthly decay
SEED = 20                       # returns whose mean square starts the variance
MIN_RETURNS = 120               # returns a stock needs in the window to be forecast
MIN_CAL_RETURNS = 60            # returns a past day needs before its move joins the calibration pool
MIN_POOL = 20000                # pooled past moves below which the normal constants are used
LEVELS = (80, 50)
NORMAL = {80: 1.2816, 50: 0.6745}
BANDS = {80: (0.75, 0.85), 50: (0.45, 0.55)}
STEP = 5
TEST_END_ROOM = 20              # sessions that must follow a test day
MIN_TEST_STOCKS = 50
KR_SIZE = 300
US_MIN_CLOSES = 250
MIN_ROWS = 200                  # fewer scored stocks than this is a partial day
MIN_DATE_SHARE = 0.3            # a date is a session when at least this share of the stocks has a bar on it
READ_AT = 240                   # matured recorded days at the one forward reading
STRESS = 0.5                    # a day whose 80% range held fewer than half of the stocks
DIRECTION_H = {"SWING": 20, "LONG_TERM": 63}        # the horizons of reports/QSF_LIVE_FORWARD_PROTOCOL.md
REL_LAMBDA = 0.97
Z_CAP = 3.0
IC_ASSUMED = 0.03               # an assumption, never called a forecast
# Zero unless a past test of that score passed condition A inside today's scan universe.  Only the live-forward evaluation changes a
# value, as a new version with a date.
IC_EVIDENCE = {("US", "SWING"): 0.0, ("US", "LONG_TERM"): 0.0, ("KR", "SWING"): 0.0, ("KR", "LONG_TERM"): 0.0}
# Why each evidence IC is zero, in the words of the protocol's table.  Shown beside every 0 and 50% so the number never stands alone.
IC_REASON = {("US", "SWING"): "과거 검증(2014~2026)에서 점수가 높을수록 수익이 좋다는 근거를 찾지 못했습니다(NO_EVIDENCE).",
             ("US", "LONG_TERM"): "과거 검증(2014~2026)에서 점수가 높을수록 수익이 좋다는 근거를 찾지 못했습니다(NO_EVIDENCE).",
             ("KR", "SWING"): "2026-11-11에 구성을 바꿔 과거 성적이 없습니다. 이전 구성은 IC +0.028, t 1.90으로 기준(t 2.24)에 못 미쳤습니다.",
             ("KR", "LONG_TERM"): "지금 대상(시가총액 상위 300) 안에서 과거 기준에 못 미쳤습니다(IC +0.052, t 2.46이지만 전반 구간의 비용 차감 스프레드가 음수)."}
PATH_NOTE = "범위는 그 거래일 수 뒤의 종가에 대한 것입니다. 그 사이에 한 번이라도 어떤 가격에 닿을 가능성은 이보다 높고, '기준에 닿을 가능성'(FC-2)에 따로 적습니다."
LIMITS = ["범위 예측은 오를지 내릴지를 말하지 않습니다. 움직임의 크기만 말합니다.",
          "한국 2010~2026, 미국 2011~2026 가격은 수익 시험에 이미 여러 번 쓴 구간입니다. 범위의 폭을 점검한 것은 이번이 처음입니다.",
          "폭을 과거 결과에 맞추는 방식이라 평균 포함률은 목표 근처가 되기 쉽습니다. 시장이 급변한 날에는 여러 종목이 한꺼번에 범위를 벗어납니다.",
          "미국 과거 자료에는 인수·파산으로 사라진 종목 일부가 없습니다. 한국 자료는 상장폐지 종목을 포함합니다."]


class NotReady(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------- the range of one day
def log_returns(win: np.ndarray) -> np.ndarray:
    """Daily log changes down each column; a day without both closes has none."""
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.log(win[1:] / win[:-1])
    return np.where(np.isfinite(r), r, np.nan)


def ewma_vol(r: np.ndarray, lam: float) -> Tuple[np.ndarray, np.ndarray]:
    """Daily volatility known at the close of each row of ``r`` and the number of returns seen by then.  The variance starts as the
    mean square of the first ``SEED`` returns and is updated from the next one on; a day without a return changes nothing."""
    days, n = r.shape
    var, ssq, cnt = np.full(n, np.nan), np.zeros(n), np.zeros(n, dtype=int)
    out, counts = np.full((days, n), np.nan), np.zeros((days, n), dtype=int)
    for t in range(days):
        x = r[t]
        ok = np.isfinite(x)
        sq = np.where(ok, x * x, 0.0)
        cnt = cnt + ok
        seeding = ok & (cnt <= SEED)
        ssq = ssq + np.where(seeding, sq, 0.0)
        var = np.where(seeding & (cnt == SEED), ssq / SEED, var)
        var = np.where(ok & (cnt > SEED), lam * var + (1 - lam) * sq, var)
        out[t], counts[t] = np.sqrt(var), cnt
    return out, counts


def day_forecast(adj: np.ndarray, i: int, cols: np.ndarray, window: int = WINDOW) -> Dict[str, Any]:
    """Horizon volatility of every stock in ``cols`` at the close of row ``i`` and the day's two width factors per horizon.
    Reads rows ``i - window + 1 .. i`` and nothing after ``i``."""
    win = adj[max(0, i - window + 1):i + 1][:, cols].astype(float)
    r = log_returns(win)
    days = r.shape[0]
    out: Dict[str, Any] = {"vol": {}, "k": {}, "returns": r}
    for h in HORIZONS:
        if days == 0:
            out["vol"][h], out["k"][h] = np.full(len(cols), np.nan), {**NORMAL, "pool": 0, "source": "NORMAL"}
            continue
        sig, cnt = ewma_vol(r, LAMBDA[h])
        ok = np.isfinite(win[-1]) & (cnt[-1] >= MIN_RETURNS) & np.isfinite(sig[-1]) & (sig[-1] > 0)
        out["vol"][h] = np.where(ok, sig[-1] * math.sqrt(h), np.nan)
        pool = np.empty(0)
        if days - h >= 1:                                   # past closes ``s`` whose move to ``s + h`` had ended by row ``i``
            with np.errstate(invalid="ignore", divide="ignore"):
                z = np.abs(np.log(win[1 + h:] / win[1:days - h + 1])) / (sig[:days - h] * math.sqrt(h))
            use = np.isfinite(z) & (cnt[:days - h] >= MIN_CAL_RETURNS) & ok[None, :]
            pool = z[use]
        if pool.size >= MIN_POOL:
            k50, k80 = np.quantile(pool, [0.5, 0.8])
            out["k"][h] = {80: float(k80), 50: float(k50), "pool": int(pool.size), "source": "EMPIRICAL"}
        else:
            out["k"][h] = {**NORMAL, "pool": int(pool.size), "source": "NORMAL"}
    return out


def outcome(adj: np.ndarray, i: int, cols: np.ndarray, h: int) -> np.ndarray:
    """Log move from the close of row ``i`` to the close ``h`` rows later.  A stock gone before then ends at its last close inside
    the horizon; one with no close at all inside it has no outcome."""
    fut = adj[i + 1:i + h + 1][:, cols].astype(float)
    have = np.isfinite(fut)
    last = fut.shape[0] - 1 - np.argmax(have[::-1], axis=0)
    exit_ = fut[last, np.arange(len(cols))]
    exit_[~have.any(axis=0)] = np.nan
    with np.errstate(invalid="ignore", divide="ignore"):
        move = np.log(exit_ / adj[i, cols].astype(float))
    return np.where(np.isfinite(move), move, np.nan)


def cover(move: np.ndarray, vol: np.ndarray, k: float) -> Optional[Dict[str, Any]]:
    """Share of the stocks whose move stayed inside ``+-k x vol``, and the shares that left above and below."""
    ok = np.isfinite(move) & np.isfinite(vol)
    if not ok.any():
        return None
    m, edge = move[ok], k * vol[ok]
    return {"n": int(ok.sum()), "inside": float((np.abs(m) <= edge).mean()), "above": float((m > edge).mean()), "below": float((m < -edge).mean())}


# ---------------------------------------------------------------------- the one historical check
def check_rows(n_dates: int) -> List[int]:
    return [i for i in range(WINDOW - 1, n_dates, STEP) if i + TEST_END_ROOM < n_dates]


def evaluate_day(adj: np.ndarray, i: int, cols: np.ndarray) -> Optional[Dict[str, Any]]:
    if len(cols) < MIN_TEST_STOCKS:
        return None
    f = day_forecast(adj, i, cols)
    row: Dict[str, Any] = {"stocks": int(len(cols))}
    for h in HORIZONS:
        vol, k, move = f["vol"][h], f["k"][h], outcome(adj, i, cols, h)
        c80 = cover(move, vol, k[80])
        if c80 is None or c80["n"] < MIN_TEST_STOCKS:
            return None
        ok = np.isfinite(move) & np.isfinite(vol)
        order = np.argsort(vol[ok], kind="mergesort")
        thirds = np.array_split(order, 3)
        inside = np.abs(move[ok]) <= k[80] * vol[ok]
        row[str(h)] = {"n": c80["n"], "uncounted": int((np.isfinite(vol) & ~np.isfinite(move)).sum()), "cover80": c80["inside"], "above80": c80["above"], "below80": c80["below"],
                       "cover50": cover(move, vol, k[50])["inside"], "normal80": cover(move, vol, NORMAL[80])["inside"], "normal50": cover(move, vol, NORMAL[50])["inside"],
                       "k80": k[80], "k50": k[50], "source": k["source"], "half_width": float(np.median(np.exp(k[80] * vol[ok]) - 1)),
                       "by_vol": [float(inside[t].mean()) for t in thirds]}
    return row


def _mean(x: Sequence[float]) -> Optional[float]:
    return float(np.mean(x)) if len(x) else None


def _parts(days: List[Dict[str, Any]], h: int, key: str) -> Dict[str, Optional[float]]:
    x = [d[str(h)][key] for d in days]
    half = len(x) // 2
    return {"all": _mean(x), "early": _mean(x[:half]), "late": _mean(x[half:])}


def in_band(parts: Dict[str, Optional[float]], level: int) -> bool:
    lo, hi = BANDS[level]
    return all(v is not None and lo - 1e-12 <= v <= hi + 1e-12 for v in parts.values())


def summarize(days: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Means over the test days, the twelve band checks and the reference figures."""
    out: Dict[str, Any] = {"days": len(days), "first": days[0]["date"] if days else None, "last": days[-1]["date"] if days else None,
                           "mean_stocks": _mean([d["stocks"] for d in days]), "horizons": {}, "failed": []}
    for h in HORIZONS:
        c80, c50 = _parts(days, h, "cover80"), _parts(days, h, "cover50")
        years: Dict[str, List[float]] = {}
        for d in days:
            years.setdefault(d["date"][:4], []).append(d[str(h)]["cover80"])
        worst = min(years.items(), key=lambda kv: np.mean(kv[1])) if years else None
        for level, parts in ((80, c80), (50, c50)):
            for part, v in parts.items():
                lo, hi = BANDS[level]
                if v is None or not lo - 1e-12 <= v <= hi + 1e-12:
                    out["failed"].append({"horizon": h, "level": level, "part": part, "value": v, "band": [lo, hi]})
        out["horizons"][str(h)] = {"cover80": c80, "cover50": c50, "pass80": in_band(c80, 80), "pass50": in_band(c50, 50),
                                   "normal80": _mean([d[str(h)]["normal80"] for d in days]), "normal50": _mean([d[str(h)]["normal50"] for d in days]),
                                   "stress_share": _mean([float(d[str(h)]["cover80"] < STRESS) for d in days]),
                                   "worst_year": None if worst is None else {"year": worst[0], "cover80": float(np.mean(worst[1])), "days": len(worst[1])},
                                   "by_vol": [_mean([d[str(h)]["by_vol"][t] for d in days]) for t in range(3)],
                                   "above80": _mean([d[str(h)]["above80"] for d in days]), "below80": _mean([d[str(h)]["below80"] for d in days]),
                                   "half_width": float(np.median([d[str(h)]["half_width"] for d in days])) if days else None,
                                   "k80": _mean([d[str(h)]["k80"] for d in days]), "k50": _mean([d[str(h)]["k50"] for d in days]),
                                   "normal_days": int(sum(d[str(h)]["source"] == "NORMAL" for d in days)), "uncounted": int(sum(d[str(h)]["uncounted"] for d in days)),
                                   "stock_days": int(sum(d[str(h)]["n"] for d in days))}
    out["verdict"] = "RANGE_CALIBRATED" if days and not out["failed"] else "RANGE_NOT_CALIBRATED"
    return out


def evaluate(adj: np.ndarray, dates: Sequence[str], universe: Callable[[int], np.ndarray], log=lambda m: None) -> Dict[str, Any]:
    days = []
    rows = check_rows(len(dates))
    for n, i in enumerate(rows):
        row = evaluate_day(adj, i, universe(i))
        if row:
            days.append({"date": str(dates[i]), **row})
        if n % 100 == 0:
            log(f"{n}/{len(rows)} {dates[i]}")
    return summarize(days)


def kr_universe(d: Dict[str, np.ndarray]) -> Callable[[int], np.ndarray]:
    """The 300 largest eligible stocks of the day, the same kind of universe the live Korean scan covers."""
    from terminal.qsf import kr_risk_grade, research_kr as kr
    return lambda i: np.flatnonzero(kr_risk_grade.members(d, i, kr.eligible(d, i), KR_SIZE))


def us_universe(adj: np.ndarray) -> Callable[[int], np.ndarray]:
    """Every stock with a close on the day and at least ``US_MIN_CLOSES`` closes in the window."""
    seen = np.cumsum(np.isfinite(adj), axis=0)

    def pick(i: int) -> np.ndarray:
        lo = max(0, i - WINDOW + 1)
        inside = seen[i] - (seen[lo - 1] if lo > 0 else 0)
        return np.flatnonzero(np.isfinite(adj[i]) & (inside >= US_MIN_CLOSES))
    return pick


def _load_markets(base: Path) -> Dict[str, Tuple[np.ndarray, List[str], Callable[[int], np.ndarray]]]:
    out = {}
    with np.load(Path(base) / KR_PRICES, allow_pickle=False) as z:
        d = {k: z[k] for k in z.files}
    out["KR"] = (d["adj_close"], [str(x) for x in d["dates"]], kr_universe(d))
    with np.load(Path(base) / US_PRICES, allow_pickle=False) as z:
        adj, dates = z["adj_close"], [str(x) for x in z["dates"]]
    out["US"] = (adj, dates, us_universe(adj))
    return out


def run_once(base: Path, log=print, loaders: Optional[Callable[[Path], Dict[str, Any]]] = None) -> Dict[str, Any]:
    """The one run over both markets.  A stored result is returned as it is and nothing is computed again."""
    path = Path(base) / REPORT
    if path.exists():
        return {**json.loads(path.read_text(encoding="utf-8")), "status": "ALREADY_RUN"}
    markets = {}
    for market, (adj, dates, universe) in (loaders or _load_markets)(Path(base)).items():
        log(f"{market}: {dates[0]} ~ {dates[-1]}")
        markets[market] = {"data_first": dates[0], "data_last": dates[-1], **evaluate(adj, dates, universe, log)}
    doc = {"status": "REAL", "version": VERSION, "protocol": PROTOCOL, "ran_at": _utcnow().isoformat(),
           "settings": {"window": WINDOW, "horizons": list(HORIZONS), "lambda": {str(h): LAMBDA[h] for h in HORIZONS}, "seed": SEED, "min_returns": MIN_RETURNS,
                        "min_cal_returns": MIN_CAL_RETURNS, "min_pool": MIN_POOL, "step": STEP, "bands": {str(k): list(v) for k, v in BANDS.items()}, "stress": STRESS},
           "markets": markets, "limits": LIMITS}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return doc


def check_result(base: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((Path(base) / REPORT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------- direction: the Grinold rule
def phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def z_scores(scores: np.ndarray) -> np.ndarray:
    """Each score against the day's mean and spread, cut at ``Z_CAP``; a stock without a score has none."""
    ok = np.isfinite(scores)
    out = np.full(len(scores), np.nan)
    if ok.sum() >= 2 and scores[ok].std() > 0:
        out[ok] = np.clip((scores[ok] - scores[ok].mean()) / scores[ok].std(), -Z_CAP, Z_CAP)
    return out


def relative_vol(r: np.ndarray, h: int) -> np.ndarray:
    """Horizon volatility of each stock's daily move against the day's average move of the same stocks."""
    if r.shape[0] == 0:
        return np.full(r.shape[1], np.nan)
    have = np.isfinite(r).sum(axis=1, keepdims=True)
    mean = np.nansum(np.where(np.isfinite(r), r, 0.0), axis=1, keepdims=True) / np.where(have > 0, have, np.nan)
    sig, cnt = ewma_vol(r - mean, REL_LAMBDA)
    return np.where((cnt[-1] >= MIN_RETURNS) & np.isfinite(sig[-1]) & (sig[-1] > 0), sig[-1] * math.sqrt(h), np.nan)


def direction(z: float, omega: Optional[float], ic: float) -> Dict[str, Optional[float]]:
    """Expected excess return and the chance of ending above half the universe under an information coefficient of ``ic``."""
    return {"p": phi(ic * z / math.sqrt(1 - ic * ic)), "alpha": None if omega is None else ic * omega * z}


# ---------------------------------------------------------------------- the daily record
def matrix(tickers: Sequence[str], loader: Callable[[str], List[Dict[str, Any]]], last: Optional[str] = None, first: Optional[str] = None) -> Tuple[np.ndarray, List[str]]:
    """Adjusted closes by session and stock from the scan's own bars, up to ``last``.  A date is a session when enough stocks traded."""
    series: Dict[str, Dict[str, float]] = {}
    seen: Counter = Counter()
    for t in tickers:
        s = {}
        for b in loader(t) or []:
            day, v = b.get("date"), b.get("adj_close") or b.get("close")
            if day and v and (last is None or day <= last) and (first is None or day >= first):
                s[day] = float(v)
        series[t] = s
        seen.update(s.keys())
    have = sum(1 for s in series.values() if s)
    dates = sorted(d for d, n in seen.items() if n >= max(1, MIN_DATE_SHARE * have))
    row = {d: n for n, d in enumerate(dates)}
    out = np.full((len(dates), len(tickers)), np.nan)
    for j, t in enumerate(tickers):
        for day, v in series[t].items():
            if day in row:
                out[row[day], j] = v
    return out, dates


def _session_snaps(led: Ledger, market: str, session: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in led._live_rows():
        if r["market"] == market and r["session"] == session:
            out += led._load(r)
    return out


def build_doc(session: str, market: str, snaps: List[Dict[str, Any]], loader: Callable[[str], List[Dict[str, Any]]]) -> Dict[str, Any]:
    """What the layer says at the close of ``session`` about every stock scored that day.  No later price is read."""
    fresh = [s for s in snaps if s.get("data_date") == session and s.get("score") is not None and s.get("strategy") in DIRECTION_H]
    tickers = sorted({s["ticker"] for s in fresh})
    if len(tickers) < MIN_ROWS:
        raise NotReady("TOO_FEW_STOCKS")
    adj, dates = matrix(tickers, loader, last=session)
    if not dates or dates[-1] != session or np.isfinite(adj[-1]).sum() < MIN_ROWS:
        raise NotReady("PRICES_NOT_AT_SESSION")
    i, cols = len(dates) - 1, np.arange(len(tickers))
    f = day_forecast(adj, i, cols)
    from terminal.qsf import forecast_touch          # FC-2 reads this module's volatility, so it is imported here and not at the top
    touch = {"touch": forecast_touch.table_doc(forecast_touch.day_touch(adj, i, cols))} if session >= forecast_touch.FIRST else {}
    by = {(s["ticker"], s["strategy"]): s for s in fresh}
    side: Dict[str, Dict[str, np.ndarray]] = {}
    for strategy, h in DIRECTION_H.items():
        sc = np.array([float(by[(t, strategy)]["score"]) if (t, strategy) in by else np.nan for t in tickers])
        side[strategy] = {"score": sc, "z": z_scores(sc), "omega": relative_vol(f["returns"], h)}
    num = lambda v, nd=6: None if v is None or not np.isfinite(v) else round(float(v), nd)        # noqa: E731
    rows = []
    for j, t in enumerate(tickers):
        any_snap = by.get((t, "SWING")) or by.get((t, "LONG_TERM"))
        row: Dict[str, Any] = {"ticker": t, "close": num(any_snap.get("price"), 4), "vol": {str(h): num(f["vol"][h][j]) for h in HORIZONS}}
        for strategy, key in (("SWING", "swing"), ("LONG_TERM", "long")):
            z = side[strategy]["z"][j]
            if not np.isfinite(z):
                row[key] = None
                continue
            omega = num(side[strategy]["omega"][j])
            real, assumed = direction(float(z), omega, IC_EVIDENCE[(market, strategy)]), direction(float(z), omega, IC_ASSUMED)
            row[key] = {"score": num(side[strategy]["score"][j], 3), "z": num(z, 4), "omega": omega, "p": num(real["p"], 4), "alpha": num(real["alpha"]),
                        "p_assumed": num(assumed["p"], 4), "alpha_assumed": num(assumed["alpha"])}
        rows.append(row)
    return {"session": session, "market": market, "protocol": PROTOCOL, "version": VERSION, "window": WINDOW, "sessions_read": len(dates),
            "model_versions": sorted({str(s.get("model_version")) for s in fresh}),
            "k": {str(h): {"k80": round(f["k"][h][80], 6), "k50": round(f["k"][h][50], 6), "pool": f["k"][h]["pool"], "source": f["k"][h]["source"]} for h in HORIZONS},
            "ic_evidence": {s: IC_EVIDENCE[(market, s)] for s in DIRECTION_H}, "ic_assumed": IC_ASSUMED, "direction_horizons": dict(DIRECTION_H),
            "forecast": int(sum(r["vol"][str(HORIZONS[-1])] is not None for r in rows)), **touch, "rows": rows}


def record(base: Path, market: str, loader: Callable[[str], List[Dict[str, Any]]], now: Callable[[], datetime] = _utcnow, first: str = FIRST) -> Dict[str, Any]:
    """OK: every ledger session of ``market`` from ``first`` is written.  WAITING: the newest one cannot be written yet."""
    led = Ledger(Path(base))
    if led.verify()["status"] != "OK":
        return {"status": "FAILED", "market": market, "reason": "LEDGER_BROKEN"}
    at, folder = now(), FOLDERS[market]
    sessions = sorted({r["session"] for r in led._live_rows() if r["market"] == market and r["session"] >= first})
    done = {r["session"] for r in kf.read_index(base, folder)}
    wrote, waiting = [], None
    for day in sessions:
        if day in done:
            continue
        try:
            if kf.write_record(base, day, at, day != sessions[-1], store=folder, scorer=lambda b, d: build_doc(d, market, _session_snaps(led, market, d), loader)):
                wrote.append(day)
        except NotReady as exc:
            waiting = {"session": day, "reason": str(exc)}
            if day == sessions[-1]:
                break
    return {"status": "WAITING" if waiting and waiting["session"] == sessions[-1] else "OK", "market": market, "written": wrote, "waiting": waiting,
            "last": max(done | set(wrote), default=None), "sessions": len(done) + len(wrote)}


# ---------------------------------------------------------------------- reading the record
def _docs(base: Path, market: str) -> List[Dict[str, Any]]:
    folder = Path(base) / FOLDERS[market]
    return [kf._read_day(folder, r["session"]) for r in kf.read_index(base, FOLDERS[market])]


def follow(docs: List[Dict[str, Any]], adj: np.ndarray, dates: Sequence[str], col: Dict[str, int]) -> Dict[str, Any]:
    """Coverage of every recorded day whose horizon has ended, and the direction figures.  ``adj`` holds prices after the records."""
    from terminal.qsf import forecast_touch
    row_of = {d: n for n, d in enumerate(dates)}
    ranges: Dict[int, List[Dict[str, Any]]] = {h: [] for h in HORIZONS}
    touches: Dict[int, List[Dict[str, Any]]] = {h: [] for h in HORIZONS}
    sides: Dict[str, List[Dict[str, Any]]] = {s: [] for s in DIRECTION_H}
    for doc in docs:
        i = row_of.get(doc["session"])
        if i is None:
            continue
        rows = [r for r in doc["rows"] if r["ticker"] in col]
        cols = np.array([col[r["ticker"]] for r in rows], dtype=int)
        for h in HORIZONS:
            if not len(rows) or i + h >= len(dates):
                continue
            vol = np.array([np.nan if r["vol"][str(h)] is None else r["vol"][str(h)] for r in rows], dtype=float)
            move, k = outcome(adj, i, cols, h), doc["k"][str(h)]
            c80, c50 = cover(move, vol, k["k80"]), cover(move, vol, k["k50"])
            if c80:
                ranges[h].append({"session": doc["session"], "n": c80["n"], "cover80": c80["inside"], "cover50": c50["inside"], "above80": c80["above"], "below80": c80["below"],
                                  "uncounted": int((np.isfinite(vol) & ~np.isfinite(move)).sum())})
            touched = forecast_touch.follow_day(doc, adj, i, cols, rows, h)
            if touched:
                touches[h].append(touched)
        for strategy, key in (("SWING", "swing"), ("LONG_TERM", "long")):
            h = DIRECTION_H[strategy]
            if not len(rows) or i + h >= len(dates):
                continue
            move = outcome(adj, i, cols, h)
            z = np.array([np.nan if not r.get(key) else r[key]["z"] for r in rows], dtype=float)
            p = np.array([np.nan if not r.get(key) else r[key]["p_assumed"] for r in rows], dtype=float)
            ok = np.isfinite(move) & np.isfinite(z)
            if ok.sum() < 30:
                continue
            beat = (move[ok] > np.median(move[ok])).astype(float)
            zz = z[ok]
            share = lambda m: None if not m.any() else float(beat[m].mean())      # noqa: E731
            sides[strategy].append({"session": doc["session"], "n": int(ok.sum()), "high": share(zz >= 1), "middle": share(np.abs(zz) < 1), "low": share(zz <= -1),
                                    "brier_assumed": float(np.mean((p[ok] - beat) ** 2)), "brier_half": float(np.mean((0.5 - beat) ** 2))})
    out: Dict[str, Any] = {"ranges": {}, "direction": {}, "touch": {str(h): forecast_touch.read(touches[h]) for h in HORIZONS}}
    for h in HORIZONS:
        days = ranges[h]
        fixed = days[:READ_AT] if len(days) >= READ_AT else None
        reading = None
        if fixed:
            c80, c50 = _halves([d["cover80"] for d in fixed]), _halves([d["cover50"] for d in fixed])
            reading = {"days": READ_AT, "first": fixed[0]["session"], "last": fixed[-1]["session"], "cover80": c80, "cover50": c50,
                       "verdict": "RANGE_CALIBRATED" if in_band(c80, 80) and in_band(c50, 50) else "RANGE_NOT_CALIBRATED"}
        out["ranges"][str(h)] = {"matured": len(days), "first": days[0]["session"] if days else None, "last": days[-1]["session"] if days else None,
                                 "cover80": _mean([d["cover80"] for d in days]), "cover50": _mean([d["cover50"] for d in days]),
                                 "above80": _mean([d["above80"] for d in days]), "below80": _mean([d["below80"] for d in days]),
                                 "stock_days": int(sum(d["n"] for d in days)), "uncounted": int(sum(d["uncounted"] for d in days)), "read_at": READ_AT, "reading": reading}
    for strategy, days in sides.items():
        pick = lambda k: _mean([d[k] for d in days if d[k] is not None])        # noqa: E731
        out["direction"][strategy] = {"horizon": DIRECTION_H[strategy], "matured": len(days), "high": pick("high"), "middle": pick("middle"), "low": pick("low"),
                                      "brier_assumed": pick("brier_assumed"), "brier_half": pick("brier_half")}
    return out


def _halves(x: Sequence[float]) -> Dict[str, Optional[float]]:
    half = len(x) // 2
    return {"all": _mean(x), "early": _mean(x[:half]), "late": _mean(x[half:])}


def today(doc: Dict[str, Any]) -> Dict[str, Any]:
    """The newest recorded day in the units a reader uses: the half-width of each range as a share of the price."""
    out: Dict[str, Any] = {"session": doc["session"], "universe": len(doc["rows"]), "forecast": doc["forecast"], "k": doc["k"], "recorded_at": doc.get("recorded_at"), "half_width": {}}
    for h in HORIZONS:
        vol = np.array([r["vol"][str(h)] for r in doc["rows"] if r["vol"][str(h)] is not None], dtype=float)
        k = doc["k"][str(h)]
        out["half_width"][str(h)] = None if not len(vol) else {"p80_median": float(np.median(np.exp(k["k80"] * vol) - 1)), "p50_median": float(np.median(np.exp(k["k50"] * vol) - 1)),
                                                               "p80_low": float(np.quantile(np.exp(k["k80"] * vol) - 1, 0.1)), "p80_high": float(np.quantile(np.exp(k["k80"] * vol) - 1, 0.9))}
    return out


def stock_range(row: Dict[str, Any], doc: Dict[str, Any]) -> Dict[str, Any]:
    """One stock's ranges as prices, from a recorded row."""
    out: Dict[str, Any] = {"ticker": row["ticker"], "close": row["close"], "ranges": {}}
    for h in HORIZONS:
        vol, k = row["vol"][str(h)], doc["k"][str(h)]
        if vol is None or row["close"] is None:
            out["ranges"][str(h)] = None
            continue
        out["ranges"][str(h)] = {"p80": [row["close"] * math.exp(-k["k80"] * vol), row["close"] * math.exp(k["k80"] * vol)],
                                 "p50": [row["close"] * math.exp(-k["k50"] * vol), row["close"] * math.exp(k["k50"] * vol)],
                                 "half_width80": math.exp(k["k80"] * vol) - 1}
    return out


def write_status(base: Path, loaders: Dict[str, Callable[[str], List[Dict[str, Any]]]]) -> Dict[str, Any]:
    """The view file: the historical check as stored, each market's record and the figures of the days that have ended."""
    from terminal.qsf import forecast_touch
    base = Path(base)
    test, touch_test = check_result(base), forecast_touch.check_result(base)
    out: Dict[str, Any] = {"status": "REAL", "version": VERSION, "protocol": PROTOCOL, "written_at": _utcnow().isoformat(), "first": FIRST, "horizons": list(HORIZONS),
                           "bands": {str(k): list(v) for k, v in BANDS.items()}, "ic_assumed": IC_ASSUMED, "limits": LIMITS, "markets": {},
                           "touch": {"version": forecast_touch.VERSION, "protocol": forecast_touch.PROTOCOL, "first": forecast_touch.FIRST, "grid": list(forecast_touch.GRID),
                                     "tolerance": {str(k): v for k, v in forecast_touch.TOLERANCE.items()}, "basis": "close", "limits": forecast_touch.LIMITS}}
    for market, loader in loaders.items():
        docs = _docs(base, market)
        m: Dict[str, Any] = {"record": {"sessions": len(docs), "first": docs[0]["session"] if docs else None, "last": docs[-1]["session"] if docs else None},
                             "ic_evidence": {s: IC_EVIDENCE[(market, s)] for s in DIRECTION_H},
                             "test": None if not test or market not in test.get("markets", {}) else {k: test["markets"][market].get(k) for k in ("verdict", "days", "first", "last", "mean_stocks", "horizons", "failed")},
                             "touch_test": None if not touch_test or market not in touch_test.get("markets", {}) else {k: touch_test["markets"][market].get(k) for k in ("verdict", "days", "first", "last", "mean_stocks", "horizons", "failed")}}
        if docs:
            tickers = sorted({r["ticker"] for d in docs for r in d["rows"]})
            adj, dates = matrix(tickers, loader, first=docs[0]["session"])
            m["today"] = {**today(docs[-1]), "touch": docs[-1].get("touch")}
            m["followed"] = follow(docs, adj, dates, {t: j for j, t in enumerate(tickers)})
        out["markets"][market] = m
    path = base / VIEW
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return out


def status(base: Path) -> Dict[str, Any]:
    try:
        return json.loads((Path(base) / VIEW).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "NO_RECORD", "version": VERSION, "protocol": PROTOCOL}


# ---------------------------------------------------------------------- the screen: reads stored records only, computes no forecast
_NEWEST: Dict[str, Tuple[Tuple[int, int], Optional[Dict[str, Any]], str]] = {}


def _newest(base: Path, market: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """The newest recorded day.  A store whose hash chain does not verify is not shown.  Kept until the index file changes."""
    index = Path(base) / FOLDERS[market] / "index.jsonl"
    try:
        st = index.stat()
    except OSError:
        return None, "NO_RECORD"
    key, slot = (st.st_mtime_ns, st.st_size), f"{Path(base).resolve()}|{market}"
    hit = _NEWEST.get(slot)
    if hit and hit[0] == key:
        return hit[1], hit[2]
    rows = kf.read_index(base, FOLDERS[market])
    if not rows:
        doc, state = None, "NO_RECORD"
    elif kf.verify(base, FOLDERS[market])["status"] != "OK":
        doc, state = None, "BROKEN"
    else:
        doc, state = kf._read_day(Path(base) / FOLDERS[market], rows[-1]["session"]), "REAL"
    _NEWEST[slot] = (key, doc, state)
    return doc, state


def _test_brief(base: Path, market: str) -> Optional[Dict[str, Any]]:
    """The stored historical check of one market in the few figures a reader needs; None when it has not been run."""
    test = check_result(base)
    m = (test or {}).get("markets", {}).get(market)
    if not m:
        return None
    return {"verdict": m.get("verdict"), "days": m.get("days"), "first": m.get("first"), "last": m.get("last"), "failed": m.get("failed") or [],
            "horizons": {h: {k: v.get(k) for k in ("cover80", "cover50", "by_vol", "stress_share", "half_width")} for h, v in (m.get("horizons") or {}).items()}}


def stock(base: Path, market: str, ticker: str) -> Dict[str, Any]:
    """One stock on the newest recorded day: its ranges as prices, where it sits by volatility and what the direction side recorded.

    Nothing is computed from prices here; a stock the record does not hold gets no range rather than an estimate."""
    if market not in FOLDERS:
        raise ValueError("INVALID_MARKET")
    head = {"version": VERSION, "protocol": PROTOCOL, "market": market, "ticker": ticker}
    from terminal.qsf import forecast_touch
    doc, state = _newest(base, market)
    if doc is None:
        return {**head, "status": state}
    row = next((r for r in doc["rows"] if r["ticker"] == ticker), None)
    if row is None:
        return {**head, "status": "NOT_IN_RECORD", "session": doc["session"], "universe": len(doc["rows"])}
    out = {**head, "status": "REAL", "session": doc["session"], "recorded_at": doc.get("recorded_at"), "universe": len(doc["rows"]), "close": row["close"],
           "ranges": {}, "test": _test_brief(base, market), "bands": {str(k): list(v) for k, v in BANDS.items()}, "ic_assumed": doc.get("ic_assumed", IC_ASSUMED), "path_note": PATH_NOTE, "direction": {},
           "touch": forecast_touch.screen(doc, base, market)}
    priced = stock_range(row, doc)["ranges"]
    for h in HORIZONS:
        vol, k, r = row["vol"][str(h)], doc["k"][str(h)], priced[str(h)]
        if r is None:
            out["ranges"][str(h)] = None                      # too little price history: no range, never a filled-in one
            continue
        vols = sorted(x["vol"][str(h)] for x in doc["rows"] if x["vol"][str(h)] is not None)
        below = sum(1 for v in vols if v < vol)
        out["ranges"][str(h)] = {**r, "vol": vol, "half_width50": math.exp(k["k50"] * vol) - 1, "log_half80": k["k80"] * vol, "log_half50": k["k50"] * vol,
                                 "source": k["source"], "vol_third": min(2, below * 3 // len(vols)), "forecast": len(vols)}
    for strategy, key in (("SWING", "swing"), ("LONG_TERM", "long")):
        side = row.get(key)
        out["direction"][strategy] = None if not side else {**side, "horizon": DIRECTION_H[strategy], "ic": IC_EVIDENCE[(market, strategy)], "reason": IC_REASON[(market, strategy)]}
    return out


def view(base: Path, market: str) -> Dict[str, Any]:
    """The tracking card of one market: the stored historical check, the record so far and why each direction figure is zero."""
    if market not in FOLDERS:
        raise ValueError("INVALID_MARKET")
    s = status(base)
    m = (s.get("markets") or {}).get(market)
    out = {"status": s.get("status"), "version": VERSION, "protocol": PROTOCOL, "market": market, "first": FIRST, "read_at": READ_AT,
           "bands": {str(k): list(v) for k, v in BANDS.items()}, "ic_assumed": IC_ASSUMED, "limits": LIMITS, "path_note": PATH_NOTE,
           "direction_horizons": dict(DIRECTION_H), "ic_reason": {s_: IC_REASON[(market, s_)] for s_ in DIRECTION_H}}
    if not m:
        return {**out, "status": "NO_RECORD"}
    from terminal.qsf import forecast_touch
    check = kf.verify(base, FOLDERS[market])
    return {**out, "written_at": s.get("written_at"), "integrity": check["status"], **m, "touch": forecast_touch.screen(_newest(base, market)[0], base, market)}
