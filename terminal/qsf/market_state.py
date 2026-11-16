"""Market state and what followed in the index (MKT-1).  Rules: reports/QSF_MARKET_STATE_PROTOCOL.md, written before any return.

The live score's regime domain is one value for every stock of a day: it cannot move a rank, it moves every score together.
Whether that is the right way round - a low regime value followed by a worse market - is an index question, and this is its one
run.  The signals are the live regime factors' own formulas (``factors.ramp`` and the same averages) on the inputs that exist on
disk.  Nothing here feeds the live score."""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from terminal.qsf import config, factors, regime_weights
from terminal.qsf.validate import rank

PROTOCOL = "reports/QSF_MARKET_STATE_PROTOCOL.md"
REPORT = Path("reports") / "qsf" / "QSF_MARKET_STATE.json"
US_PRICES = Path("data") / "qsf" / "research" / "prices_2008.npz"
KR_PRICES = Path("research_data") / "krx" / "prices.npz"
VIX_FILE = Path("research_data") / "sentiment" / "VIX_History.csv"
H = 20                          # sessions of the outcome
SKIP = 1                        # the outcome starts at the close after the signal's close
MID = 0.5                       # the middle of the 0..1 scale: at or above is a favourable day
MIN_T = 2.39                    # three signals are judged
NW_LAG = 20
MIN_GROUP, MIN_HALF = 100, 30
MA_LONG, MA_SHORT = 200, 50
VIX_RAMP = (35.0, 12.0)         # factors.vix_regime
BREADTH_RAMP = (0.30, 0.70)     # factors.breadth, factors.index_trend_breadth
KR_TOP = 300
MIN_BREADTH_STOCKS = 50         # the live Korean scan asks for as many before it writes a breadth
POINTS = {"R_US": {"vix": 5.0, "trend_breadth": 7.0}, "R_KR": {"trend": 5.0, "breadth": 4.0}}
LIMITS = ["시장의 길은 하나입니다. 날 수는 많아도 큰 하락은 몇 번뿐이라 독립된 사례가 적습니다.",
          "지난 시험들과 같은 연도입니다. 지수 수익률을 상태별로 본 것은 처음이지만 완전히 새 자료는 아닙니다.",
          "국면 영역의 일부만 다시 만들었습니다(미국 20점 중 12점, 한국 15점 중 9점). 한국에는 공포지수 입력이 없습니다.",
          "미국 가격 묶음에는 사라진 회사 일부가 없어 시장 폭이 실제보다 조금 높습니다.",
          "종목 선택은 시험하지 않았습니다. 지수만 봤습니다.",
          "지수를 종가에 비용 없이 사고팔 수는 없습니다."]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------- signals (nothing after the row is read)
def trend(c: np.ndarray) -> np.ndarray:
    """(close > 200-day mean) + (50-day mean > 200-day mean) + (close > 50-day mean), over three: ``factors.index_trend``."""
    c = np.asarray(c, dtype=float)
    out = np.full(len(c), np.nan)
    for i in range(MA_LONG - 1, len(c)):
        w = c[i - MA_LONG + 1:i + 1]
        if np.isfinite(w).all():
            ma200, ma50 = float(w.mean()), float(w[-MA_SHORT:].mean())
            out[i] = (int(c[i] > ma200) + int(ma50 > ma200) + int(c[i] > ma50)) / 3
    return out


def _window_sums(a: np.ndarray):
    fin = np.isfinite(a)
    cs = np.vstack([np.zeros((1, a.shape[1])), np.cumsum(np.where(fin, a, 0.0), axis=0)])
    cn = np.vstack([np.zeros((1, a.shape[1]), dtype=np.int64), np.cumsum(fin, axis=0, dtype=np.int64)])
    return fin, cs, cn


def share_above(a: np.ndarray, members: Optional[Callable[[int], np.ndarray]] = None, whole_window: bool = False) -> np.ndarray:
    """Per row, the share of stocks whose close is above the mean of their last 200 rows.  The US rule averages the days that have
    a value (the live panel rule); ``whole_window`` asks for all 200 (the live Korean scan asks for 200 bars).  ``members(i)`` is
    the day's stock mask."""
    a = np.asarray(a, dtype=float)
    fin, cs, cn = _window_sums(a)
    out = np.full(len(a), np.nan)
    for i in range(MA_LONG - 1, len(a)):
        s, k = cs[i + 1] - cs[i + 1 - MA_LONG], cn[i + 1] - cn[i + 1 - MA_LONG]
        ok = fin[i] & ((k == MA_LONG) if whole_window else (k > 0))
        if members is not None:
            ok &= members(i)
        if ok.sum() >= (MIN_BREADTH_STOCKS if whole_window else 1):
            out[i] = float((a[i][ok] > s[ok] / k[ok]).mean())
    return out


def top_by_cap(cap: np.ndarray, n: int = KR_TOP) -> Callable[[int], np.ndarray]:
    cap = np.asarray(cap, dtype=float)

    def members(i: int) -> np.ndarray:
        row = np.where(np.isfinite(cap[i]) & (cap[i] > 0), cap[i], -np.inf)
        mask = np.zeros(cap.shape[1], dtype=bool)
        order = np.argsort(-row, kind="mergesort")[:n]
        mask[order[np.isfinite(row[order])]] = True
        return mask
    return members


def _ramp(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.array([np.nan if (v := factors.ramp(float(t), lo, hi)) is None else v for t in x], dtype=float)


def us_signals(dates: Sequence[str], spy: np.ndarray, stocks: np.ndarray, vix: Dict[str, float]) -> Dict[str, np.ndarray]:
    v = _ramp(np.array([vix.get(d, np.nan) for d in dates], dtype=float), *VIX_RAMP)
    tb = (trend(spy) + _ramp(share_above(stocks), *BREADTH_RAMP)) / 2           # factors.index_trend_breadth: the mean of the two
    p = POINTS["R_US"]
    return {"R_US": (p["vix"] * v + p["trend_breadth"] * tb) / (p["vix"] + p["trend_breadth"]), "V_US": v}


def kr_signals(index: np.ndarray, stocks: np.ndarray, cap: np.ndarray) -> Dict[str, np.ndarray]:
    br = _ramp(share_above(stocks, top_by_cap(cap), whole_window=True), *BREADTH_RAMP)
    p = POINTS["R_KR"]
    return {"R_KR": (p["trend"] * trend(index) + p["breadth"] * br) / (p["trend"] + p["breadth"])}


# ---------------------------------------------------------------------- outcomes
def outcomes(index: np.ndarray) -> Dict[str, np.ndarray]:
    """For row t: the 20 sessions from the close of t+1 to the close of t+21."""
    index = np.asarray(index, dtype=float)
    n = len(index)
    ret, vol, mdd = (np.full(n, np.nan) for _ in range(3))
    for t in range(max(0, n - H - SKIP)):
        seg = index[t + SKIP:t + SKIP + H + 1]
        if np.isfinite(seg).all() and (seg > 0).all():
            ret[t] = seg[-1] / seg[0] - 1
            vol[t] = float(np.std(np.diff(np.log(seg)), ddof=1))
            mdd[t] = float((seg / np.maximum.accumulate(seg) - 1).min())
    return {"ret": ret, "vol": vol, "mdd": mdd}


def nw_diff(y: np.ndarray, d: np.ndarray, lag: int = NW_LAG) -> Optional[Dict[str, Any]]:
    """mean(y | d) - mean(y | not d) and its t value with Newey-West (Bartlett) errors: the days overlap, so they are not independent."""
    y, x = np.asarray(y, dtype=float), np.asarray(d, dtype=float)
    n = len(y)
    if n < 4 or x.sum() < 2 or n - x.sum() < 2:
        return None
    X = np.column_stack([np.ones(n), x])
    inv = np.linalg.inv(X.T @ X)
    b = inv @ X.T @ y
    g = X * (y - X @ b)[:, None]
    S = g.T @ g
    for k in range(1, min(lag, n - 1) + 1):
        G = g[k:].T @ g[:-k]
        S += (1 - k / (lag + 1)) * (G + G.T)
    se = math.sqrt(max(float((inv @ S @ inv)[1, 1]), 0.0))
    return {"diff": float(b[1]), "t": float(b[1] / se) if se > 0 else None}


def _group(o: Dict[str, np.ndarray], rows: np.ndarray) -> Dict[str, Any]:
    return {"days": int(len(rows)), "ret": float(o["ret"][rows].mean()) if len(rows) else None, "vol": float(o["vol"][rows].mean()) if len(rows) else None,
            "mdd": float(o["mdd"][rows].mean()) if len(rows) else None, "up_share": float((o["ret"][rows] > 0).mean()) if len(rows) else None}


def judge(sig: np.ndarray, o: Dict[str, np.ndarray]) -> Dict[str, Any]:
    rows = np.flatnonzero(np.isfinite(sig) & np.isfinite(o["ret"]) & np.isfinite(o["vol"]))
    good = sig[rows] >= MID
    half = len(rows) // 2
    parts = {"all": slice(0, len(rows)), "first": slice(0, half), "second": slice(half, len(rows))}
    out: Dict[str, Any] = {"days": int(len(rows)), "favourable": _group(o, rows[good]), "adverse": _group(o, rows[~good])}
    enough = min(int(good.sum()), int((~good).sum())) >= MIN_GROUP and all(
        min(int(good[parts[k]].sum()), int((~good[parts[k]]).sum())) >= MIN_HALF for k in ("first", "second"))
    for name, y, flag in (("return", o["ret"], good), ("risk", o["vol"], ~good)):       # return: favourable - adverse; risk: adverse - favourable
        out[name] = {k: nw_diff(y[rows][s], flag[s]) for k, s in parts.items()}
    out["half_days"] = {k: {"favourable": int(good[parts[k]].sum()), "adverse": int((~good[parts[k]]).sum())} for k in ("first", "second")}
    if not enough:
        return {**out, "return_verdict": "NOT_TESTED", "risk_verdict": "NOT_TESTED"}

    def held(name: str, sign: int) -> bool:
        a, f, s = (out[name][k] for k in ("all", "first", "second"))
        return bool(a and f and s and a["t"] is not None and sign * a["t"] >= MIN_T and sign * a["diff"] > 0 and sign * f["diff"] > 0 and sign * s["diff"] > 0)
    out["return_verdict"] = "RETURN_FOLLOWS" if held("return", 1) else "RETURN_OPPOSITE" if held("return", -1) else "RETURN_NOT_DISTINCT"
    out["risk_verdict"] = "RISK_HIGHER_WHEN_ADVERSE" if held("risk", 1) else "RISK_NOT_DISTINCT"
    return out


# ---------------------------------------------------------------------- figures only
def _path_stats(r: np.ndarray) -> Dict[str, Any]:
    if not len(r):
        return {"days": 0}
    level = np.cumprod(1 + r)
    return {"days": int(len(r)), "annual_return": float(level[-1] ** (252 / len(r)) - 1), "annual_vol": float(r.std(ddof=1) * math.sqrt(252)),
            "max_drawdown": float((level / np.maximum.accumulate(np.concatenate([[1.0], level]))[1:] - 1).min())}


def gate(index: np.ndarray, sig: np.ndarray, cost: float) -> Dict[str, Any]:
    """In the index while the signal is at or above the middle, in cash otherwise.  The signal of row t changes the holding at the
    close of t+1, so it earns from the day t+2.  A day without a signal keeps the holding."""
    index, n = np.asarray(index, dtype=float), len(index)
    have = np.flatnonzero(np.isfinite(sig))
    if not len(have) or have[0] + 2 >= n:
        return {"days": 0}
    days = np.arange(have[0] + 2, n)
    pos, cur = np.zeros(len(days)), 0.0
    for j, d in enumerate(days):
        if np.isfinite(sig[d - 2]):
            cur = 1.0 if sig[d - 2] >= MID else 0.0
        pos[j] = cur
    r = index[days] / index[days - 1] - 1
    switch = np.concatenate([[0.0], np.abs(np.diff(pos))])
    return {"always_in": _path_stats(r), "gate": _path_stats(pos * r), "gate_after_cost": _path_stats(pos * r - switch * cost),
            "invested_share": float(pos.mean()), "switches": int(switch.sum()), "cost_per_switch": cost}


def _corr(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    if len(a) < 10 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    return float(np.corrcoef(rank(a), rank(b))[0, 1])


def spaced_rank(sig: np.ndarray, o: Dict[str, np.ndarray]) -> Dict[str, Any]:
    ok = np.isfinite(sig) & np.isfinite(o["ret"]) & np.isfinite(o["vol"])
    have = np.flatnonzero(ok)
    rows = np.array([t for t in range(int(have[0]), len(sig), H) if ok[t]], dtype=int) if len(have) else np.array([], dtype=int)
    return {"days": int(len(rows)), "signal_vs_return": _corr(sig[rows], o["ret"][rows]), "signal_vs_vol": _corr(sig[rows], o["vol"][rows])}


def by_state(index: np.ndarray, o: Dict[str, np.ndarray]) -> Dict[str, Any]:
    out: Dict[str, List[int]] = {s: [] for s in regime_weights.STATES}
    for i in np.flatnonzero(np.isfinite(o["ret"]) & np.isfinite(o["vol"])):
        s = regime_weights.state(index, int(i))
        if s:
            out[s].append(int(i))
    return {s: _group(o, np.array(rows, dtype=int)) for s, rows in out.items()}


def follow(index: np.ndarray, a: np.ndarray, members: Optional[Callable[[int], np.ndarray]] = None) -> Dict[str, Any]:
    """Not a forecast: inside the same 20 sessions, how many stocks rose when the index rose and when it fell."""
    a, index = np.asarray(a, dtype=float), np.asarray(index, dtype=float)
    rows: Dict[str, List[List[float]]] = {"index_up": [], "index_down": []}
    for t in range(MA_LONG - 1, len(index) - H, H):
        m = index[t + H] / index[t] - 1
        ok = np.isfinite(a[t]) & np.isfinite(a[t + H]) & (a[t] > 0)
        if members is not None:
            ok &= members(t)
        if not np.isfinite(m) or ok.sum() < MIN_BREADTH_STOCKS:
            continue
        r = a[t + H][ok] / a[t][ok] - 1
        rows["index_up" if m > 0 else "index_down"].append([float((r > 0).mean()), float(np.median(r)), float(m), float((r > m).mean())])
    out = {}
    for k, v in rows.items():
        x = np.array(v, dtype=float).reshape(len(v), 4)
        out[k] = {"windows": len(v), "stocks_up_share": float(x[:, 0].mean()) if len(v) else None, "median_stock_return": float(x[:, 1].mean()) if len(v) else None,
                  "index_return": float(x[:, 2].mean()) if len(v) else None, "beat_index_share": float(x[:, 3].mean()) if len(v) else None}
    return out


# ---------------------------------------------------------------------- inputs on disk
def us_inputs(base: Path) -> Dict[str, Any]:
    from terminal.qsf.research_sentiment import parse_vix
    z = np.load(Path(base) / US_PRICES, allow_pickle=False)
    syms = [str(s) for s in z["symbols"]]
    a = z["adj_close"].astype(float)
    j = syms.index("SPY")
    dates = [str(d) for d in z["dates"]]
    stocks = np.delete(a, j, axis=1)
    return {"market": "US", "dates": dates, "index": a[:, j], "stocks": stocks, "members": None,
            "signals": us_signals(dates, a[:, j], stocks, parse_vix((Path(base) / VIX_FILE).read_text(encoding="utf-8")))}


def kr_inputs(base: Path) -> Dict[str, Any]:
    z = np.load(Path(base) / KR_PRICES, allow_pickle=False)
    dates = [str(d) for d in z["dates"]]
    index = np.array([b["close"] for b in regime_weights.kospi_index({k: z[k] for k in ("adj_close", "cap", "kospi", "dates")})], dtype=float)
    cap = z["cap"].astype(np.float32)
    ever = np.zeros(cap.shape[1], dtype=bool)                  # only the columns that were ever in a day's top 300: the rest never count
    pick = top_by_cap(cap)
    for i in range(len(dates)):
        ever |= pick(i)
    a, cap = z["adj_close"][:, ever].astype(float), cap[:, ever].astype(float)
    return {"market": "KR", "dates": dates, "index": index, "stocks": a, "members": top_by_cap(cap), "signals": kr_signals(index, a, cap)}


def evaluate(inp: Dict[str, Any]) -> Dict[str, Any]:
    o = outcomes(inp["index"])
    cost = config.round_trip_cost(inp["market"]) / 2
    sigs = {}
    for name, sig in inp["signals"].items():
        have = np.flatnonzero(np.isfinite(sig) & np.isfinite(o["ret"]))
        sigs[name] = {**judge(sig, o), "first_day": inp["dates"][int(have[0])] if len(have) else None, "last_day": inp["dates"][int(have[-1])] if len(have) else None,
                      "gate": gate(inp["index"], sig, cost), "spaced_rank": spaced_rank(sig, o)}
    return {"signals": sigs, "states": by_state(inp["index"], o), "follow": follow(inp["index"], inp["stocks"], inp["members"]),
            "days_on_file": len(inp["dates"]), "first_file_day": inp["dates"][0], "last_file_day": inp["dates"][-1]}


def run_once(base: Path, log=print, loaders: Optional[Dict[str, Callable[[Path], Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """The single run.  A second call returns the stored report and computes nothing."""
    path = Path(base) / REPORT
    if path.exists():
        return {**json.loads(path.read_text(encoding="utf-8")), "status": "ALREADY_RUN"}
    markets = {}
    for market, load in (loaders or {"US": us_inputs, "KR": kr_inputs}).items():
        log(f"{market}: reading prices")
        markets[market] = evaluate(load(Path(base)))
        for name, s in markets[market]["signals"].items():
            log(f"{market} {name}: {s['return_verdict']}, {s['risk_verdict']} ({s['days']} days)")
    doc = {"status": "REAL", "protocol": PROTOCOL, "run_at": _utcnow().isoformat(), "horizon": H,
           "settings": {"skip": SKIP, "mid": MID, "min_t": MIN_T, "nw_lag": NW_LAG, "min_group": MIN_GROUP, "min_half": MIN_HALF, "points": POINTS,
                        "vix_ramp": VIX_RAMP, "breadth_ramp": BREADTH_RAMP, "kr_top": KR_TOP},
           "markets": markets, "limits": LIMITS}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


if __name__ == "__main__":              # python -m terminal.qsf.market_state <base folder>
    res = run_once(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("."))
    print(res["status"])
