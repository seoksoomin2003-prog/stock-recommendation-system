"""Point-in-time trailing-twelve-month fundamentals and sector-relative ranks for the QSF 1.2 candidate.

Research only until the user approves a change: the live score does not import this module.  Everything is computed from
what had been filed by ``as_of``.  TTM = last fiscal year + current year-to-date - same period a year earlier.
"""
from bisect import bisect_right
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from terminal.qsf.fundamentals import US_FLOW, US_INSTANT, _days

FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")
FLOW_NOT_SUMMABLE = ("shares_avg", "eps")
SECTOR_KEYS = {"pe": False, "pb": False, "fcf_yield": True, "roe": True, "op_margin": True, "gross_margin": True, "rev_growth": True, "eps_growth": True,
               "rev_cagr3": True, "eps_cagr3": True, "fcf_margin": True, "debt_equity": False}      # True: higher is better
MIN_PEERS = 5


def extract_full(facts: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """{metric: [{start?, end, val, filed}]} from 10-K and 10-Q, every vintage, first-listed concept winning per period."""
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    out: Dict[str, List[Dict]] = {}

    def collect(metric, concepts, flow):
        got: Dict[str, Dict] = {}
        for name in concepts:
            for unit, rows in ((gaap.get(name) or {}).get("units") or {}).items():
                if unit not in ("USD", "shares", "USD/shares"):
                    continue
                for r in rows:
                    if r.get("form") not in FORMS or r.get("val") is None or not r.get("end") or not r.get("filed"):
                        continue
                    rec = {"end": r["end"], "val": float(r["val"]), "filed": r["filed"]}
                    if flow:
                        if not r.get("start") or not 80 <= _days(r["start"], r["end"]) <= 385:
                            continue
                        rec["start"] = r["start"]
                    got.setdefault(f"{r.get('start')}|{r['end']}|{r['filed']}", rec)
        out[metric] = sorted(got.values(), key=lambda x: (x["end"], x["filed"]))
    for m, c in US_FLOW.items():
        collect(m, c, True)
    for m, c in US_INSTANT.items():
        collect(m, c, False)
    return out


def _latest(rows: List[Dict], as_of: str) -> Dict[Tuple, Dict]:
    per: Dict[Tuple, Dict] = {}
    for r in rows:
        if r["filed"] <= as_of:
            k = (r.get("start"), r["end"])
            if k not in per or r["filed"] >= per[k]["filed"]:
                per[k] = r
    return per


def _near(rows: List[Dict], key: str, target: date, tol: int = 12) -> Optional[Dict]:
    best, gap = None, tol + 1
    for r in rows:
        g = abs((date.fromisoformat(r[key]) - target).days)
        if g < gap:
            best, gap = r, g
    return best


def ttm_points(rows: List[Dict], as_of: str) -> List[Dict]:
    """Trailing-twelve-month value at every period end known by ``as_of``.  A period that cannot be built is skipped."""
    per = list(_latest(rows, as_of).values())
    fy = [r for r in per if _days(r["start"], r["end"]) >= 340]
    ytd = [r for r in per if _days(r["start"], r["end"]) <= 300]
    out = {r["end"]: {"end": r["end"], "val": r["val"], "filed": r["filed"]} for r in fy}
    longest: Dict[str, Dict] = {}
    for r in ytd:
        if r["end"] not in out and (r["end"] not in longest or r["start"] < longest[r["end"]]["start"]):
            longest[r["end"]] = r
    for end, r in longest.items():
        start, stop = date.fromisoformat(r["start"]), date.fromisoformat(end)
        last_fy = _near(fy, "end", start - timedelta(days=1))
        same = [x for x in ytd if abs(_days(x["start"], x["end"]) - _days(r["start"], end)) <= 15]
        same = [x for x in same if abs((date.fromisoformat(x["end"]) - (stop - timedelta(days=365))).days) <= 12]
        prior = _near(same, "start", start - timedelta(days=365))
        if last_fy and prior:
            out[end] = {"end": end, "val": last_fy["val"] + r["val"] - prior["val"], "filed": max(last_fy["filed"], r["filed"], prior["filed"])}
    return [out[k] for k in sorted(out)]


def _yearly(points: List[Dict]) -> List[Dict]:
    """Walk back from the latest point one year at a time, so a year-over-year formula compares like with like."""
    if not points:
        return []
    out, cur = [points[-1]], date.fromisoformat(points[-1]["end"])
    while True:
        cur -= timedelta(days=365)
        hit = _near([p for p in points if p["end"] < out[-1]["end"]], "end", cur, 45)
        if not hit:
            return out[::-1]
        out.append(hit)
        cur = date.fromisoformat(hit["end"])


def _latest_reported(rows: List[Dict], as_of: str) -> List[Dict]:
    """Per period end, the shortest period's value (the most current share count)."""
    best: Dict[str, Dict] = {}
    for r in _latest(rows, as_of).values():
        cur = best.get(r["end"])
        if cur is None or _days(r["start"], r["end"]) < _days(cur["start"], cur["end"]):
            best[r["end"]] = r
    return [best[k] for k in sorted(best)]


def ttm_view(full: Dict[str, List[Dict]], as_of: str) -> Dict[str, List[Dict]]:
    """A yearly-spaced view shaped like ``extract_us`` so ``fundamentals.metrics`` applies unchanged."""
    view: Dict[str, List[Dict]] = {}
    for m in US_FLOW:
        rows = full.get(m) or []
        if m == "eps":
            continue
        view[m] = _yearly(_latest_reported(rows, as_of) if m in FLOW_NOT_SUMMABLE else ttm_points(rows, as_of))
    for m in US_INSTANT:
        pts: Dict[str, Dict] = {}
        for r in _latest(full.get(m) or [], as_of).values():
            pts[r["end"]] = r
        view[m] = _yearly([pts[k] for k in sorted(pts)])
    return view


class Splits:
    """Cumulative split factor between dates.  ``[(date, ratio)]``: a 4-for-1 on 2020-08-31 is ("2020-08-31", 4.0)."""
    def __init__(self, events: List[Tuple[str, float]]):
        ev = sorted((d, float(r)) for d, r in events if r and r > 0 and r != 1)
        self.dates = [d for d, _ in ev]
        self.cum = [1.0]
        for _, r in ev:
            self.cum.append(self.cum[-1] * r)

    def factor(self, after: str, until: Optional[str] = None) -> float:
        """Product of splits dated in (after, until]."""
        a = bisect_right(self.dates, after)
        b = bisect_right(self.dates, until) if until else len(self.dates)
        return self.cum[max(a, b)] / self.cum[a]


def adjust_shares(view: Dict[str, List[Dict]], as_of: str, splits: Splits) -> Dict[str, List[Dict]]:
    """Put per-share series on the share basis of ``as_of``: a split after filing raises shares and lowers EPS."""
    out = dict(view)
    if out.get("shares_avg"):
        out["shares_avg"] = [{**r, "val": r["val"] * splits.factor(r["filed"], as_of)} for r in out["shares_avg"] if r["filed"] <= as_of]
    if out.get("eps"):
        out["eps"] = [{**r, "val": r["val"] / splits.factor(r["filed"], as_of)} for r in out["eps"] if r["filed"] <= as_of]
    return out


def with_ttm_eps(view: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
    """EPS from TTM net income and the split-adjusted share count, so a split inside the window cannot distort it."""
    ni = {r["end"]: r for r in view.get("net_income") or []}
    eps = []
    for s in view.get("shares_avg") or []:
        r = ni.get(s["end"])
        if r and s["val"] > 0:
            eps.append({"end": s["end"], "val": r["val"] / s["val"], "filed": max(r["filed"], s["filed"])})
    return {**view, "eps": eps}


def sector_ranks(funds: Dict[str, Dict[str, Any]], sectors: Dict[str, Optional[str]]) -> Dict[str, Dict[str, float]]:
    """{ticker: {key: percentile 0..1, 1 is best}} within one date and sector.  A key with under MIN_PEERS values is left out,
    so the factor keeps its absolute anchor.  PER at or below zero is not ranked: the factor scores it zero."""
    groups: Dict[str, List[str]] = {}
    for t in funds:
        if sectors.get(t):
            groups.setdefault(sectors[t], []).append(t)
    out: Dict[str, Dict[str, float]] = {t: {} for t in funds}
    for members in groups.values():
        for key, higher in SECTOR_KEYS.items():
            vals = [(funds[t][key], t) for t in members if funds[t].get(key) is not None and not (key == "pe" and funds[t][key] <= 0)]
            if len(vals) < MIN_PEERS:
                continue
            ordered = sorted(v for v, _ in vals)
            n = len(ordered)
            for v, t in vals:
                hi = bisect_right(ordered, v) - 1           # ties share their average position
                eq = sum(1 for x in ordered if x == v)
                pos = (hi - (eq - 1) / 2) / (n - 1)
                out[t][key] = pos if higher else 1 - pos
    return out
