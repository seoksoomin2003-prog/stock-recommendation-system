"""Common yardstick for prospective comparison (identical for every model, P6-11B included).

Entry at the entry session's OPEN, exit at the CLOSE of the H-th session (entry session = session 1),
total-return basis (dividend factor adj_close/close).  Equal-weight basket.  A ticker without a price is
dropped and counted (never 0); a cohort missing more than 20% of its names is INCOMPLETE.
Daily cohorts overlap, so the effective number of independent observations is ~ matured / H.
"""
import math
from typing import Dict, List, Optional

import numpy as np

from terminal.lab.panel import BENCH, Panel

HORIZONS = (5, 20, 60)
MAX_MISSING = 0.2
MIN_INDEPENDENT = 12


def _entry_px(p: Panel, j: int, e: int) -> Optional[float]:
    o, c, a = p.f("open")[e, j], p.f("close")[e, j], p.f("adj_close")[e, j]
    if not (np.isfinite(o) and np.isfinite(c) and np.isfinite(a)) or c <= 0:
        return None
    return float(o * a / c)


def ticker_return(p: Panel, ticker: str, e: int, x: int) -> Optional[float]:
    j = p.col.get(ticker)
    if j is None:
        return None
    ep, xp = _entry_px(p, j, e), p.f("adj_close")[x, j]
    return float(xp / ep - 1) if ep and np.isfinite(xp) else None


def cohort_outcome(p: Panel, tickers: List[str], entry_session: str, h: int) -> Dict:
    """Outcome of one basket for horizon h: PENDING / MATURED / INCOMPLETE / NO_ENTRY_DATA."""
    if entry_session not in p.idx:
        last = p.last or ""
        return {"status": "PENDING" if entry_session > last else "NO_ENTRY_DATA"}
    e = p.idx[entry_session]
    x = e + h - 1
    if x >= len(p.dates):
        return {"status": "PENDING", "sessions_held": len(p.dates) - e}
    rets = {t: ticker_return(p, t, e, x) for t in tickers}
    got = [r for r in rets.values() if r is not None]
    missing = [t for t, r in rets.items() if r is None]
    bench = ticker_return(p, BENCH, e, x)
    if not tickers or len(missing) > MAX_MISSING * len(tickers) or bench is None:
        return {"status": "INCOMPLETE", "missing": missing, "exit_session": p.dates[x]}
    r = float(np.mean(got))
    return {"status": "MATURED", "return": r, "bench": bench, "excess": r - bench, "missing": missing,
            "exit_session": p.dates[x], "n": len(got)}


def aggregate(outcomes: List[Dict], h: int) -> Dict:
    m = [o for o in outcomes if o["status"] == "MATURED"]
    n = len(m)
    out = {"horizon": h, "matured": n, "pending": sum(o["status"] == "PENDING" for o in outcomes),
           "incomplete": sum(o["status"] in ("INCOMPLETE", "NO_ENTRY_DATA") for o in outcomes),
           "independent": n / h if n else 0.0}
    if n:
        ex = [o["excess"] for o in m]
        out.update(mean_return=float(np.mean([o["return"] for o in m])), mean_excess=float(np.mean(ex)),
                   hit_rate=float(np.mean([e > 0 for e in ex])))
    else:
        out.update(mean_return=None, mean_excess=None, hit_rate=None)
    out["verdict"] = "판단 보류" if out["independent"] < MIN_INDEPENDENT else "관찰 가능"
    return out


def compare(p: Optional[Panel], cohorts: Dict[str, List[Dict]]) -> Dict[str, Dict]:
    """cohorts: model -> [{entry_session, tickers}] -> per-model, per-horizon aggregates."""
    res = {}
    for model, cs in cohorts.items():
        per = {}
        for h in HORIZONS:
            outs = [cohort_outcome(p, c["tickers"], c["entry_session"], h) if p else {"status": "PENDING"}
                    for c in cs]
            per[str(h)] = aggregate(outs, h)
        res[model] = {"cohorts": len(cs), "first_entry": min((c["entry_session"] for c in cs), default=None),
                      "last_entry": max((c["entry_session"] for c in cs), default=None), "horizons": per}
    return res


def finite(x):
    return x if isinstance(x, float) and math.isfinite(x) else None
