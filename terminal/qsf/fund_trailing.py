"""Trailing-four-quarter fundamentals, for the record kept beside the live annual score.  Rules: reports/QSF_FUND_PERIOD_PROTOCOL.md.

A period row is ``{start, end, val, filed}`` for a flow and ``{end, val, filed}`` for a balance (plus ``alias``, ``basis`` and
``currency`` where the annual reader carries them).  ``view`` turns period rows into series shaped like the annual reader's: one
row per end, the ends a year apart and the last one the newest period on file by ``as_of``.  ``fundamentals.metrics`` then applies
unchanged, so the factors, weights and anchors are the live ones and only the period of the figures differs.

    flow     last fiscal year + this year to date - the same months a year before; all three or nothing
    balance  the newest quarter end
    EPS      US: trailing profit over the newest reported average count.  Korea (no count is reported): the same sum as any
             flow, kept only when the share counts behind its three parts agree

The live score does not read this module unless the market's one reading said TRAILING_BETTER (``fund_period.live_period``).
"""
from datetime import date, timedelta
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Tuple

from terminal.qsf import fundamentals
from terminal.qsf.fundamentals import US_CAPEX_FALLBACK, US_FLOW, US_INSTANT, US_REAL_ESTATE_SPENDING

FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")
HISTORY_DAYS = 6 * 365 + 120     # five yearly points back from the newest quarter, and the year before the oldest of them
FY_MIN_DAYS, YTD_MAX_DAYS = 340, 300
NEAR_DAYS = 12                   # a fiscal year end, or the same quarter a year before, is found within this many days
YEAR_TOL = 20                    # yearly points: the same quarter a year earlier within this many days of 365
KEEP_VINTAGES = 2                # filings kept per period in the stored rows: the newest two
COUNT_GAP = 1.25                 # share counts behind the parts of a summed EPS further apart than this: a split or an issue in between
KR_FLOW = ("revenue", "op_income", "net_income", "net_income_all", "ocf", "capex", "eps", "dividends")
KR_INSTANT = ("equity", "equity_all", "assets", "liabilities", "current_assets", "current_liabilities", "cash")
SOURCE = {"US": "SEC EDGAR 10-K·10-Q (최근 4분기)", "KR": "OpenDART 사업·분기보고서 (최근 4분기)"}
_date = lru_cache(maxsize=20000)(date.fromisoformat)


def _days(a: str, b: str) -> int:
    return (_date(b) - _date(a)).days


# ---------------------------------------------------------------------- US: period rows from the SEC facts already downloaded
def us_periods(facts: Dict[str, Any]) -> Dict[str, Dict[str, List[Dict]]]:
    """{"flow": {metric: rows}, "instant": {metric: rows}} from 10-K and 10-Q filings.  The tags and their order are the annual
    reader's: for one period and filing the first-listed tag wins.  Only what a view can use is kept: the last ``HISTORY_DAYS``
    and the newest ``KEEP_VINTAGES`` filings of each period."""
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}

    def collect(concepts: List[str], flow: bool) -> List[Dict]:
        got: Dict[Tuple, Dict] = {}
        for name in concepts:
            for unit, rows in ((gaap.get(name) or {}).get("units") or {}).items():
                if unit not in ("USD", "shares", "USD/shares"):
                    continue
                for r in rows:
                    if r.get("form") not in FORMS or r.get("val") is None or not r.get("end") or not r.get("filed"):
                        continue
                    rec = {"end": r["end"], "val": float(r["val"]), "filed": r["filed"], "alias": name}
                    if flow:
                        if not r.get("start") or not 80 <= _days(r["start"], r["end"]) <= 385:
                            continue
                        rec["start"] = r["start"]
                    got.setdefault((r.get("start") if flow else None, r["end"], r["filed"]), rec)
        return list(got.values())

    out = {"flow": {m: collect(c, True) for m, c in US_FLOW.items()}, "instant": {m: collect(c, False) for m, c in US_INSTANT.items()}}
    if US_CAPEX_FALLBACK:           # the annual reader's rule (QSF-1.6.0): another capital-spending tag only for a period the three do not report
        span = lambda r: (r.get("start"), r["end"])        # noqa: E731
        skip = {span(r) for r in out["flow"]["capex"]} | {span(r) for r in collect(US_REAL_ESTATE_SPENDING, True)}
        out["flow"]["capex"] += [r for r in collect(US_CAPEX_FALLBACK, True) if span(r) not in skip and r["val"] > 0]
    ends = [r["end"] for kind in out.values() for rows in kind.values() for r in rows]
    if not ends:
        return out
    oldest = (_date(max(ends)) - timedelta(days=HISTORY_DAYS)).isoformat()
    for kind in out.values():
        for m, rows in kind.items():
            per: Dict[Tuple, List[Dict]] = {}
            for r in rows:
                if r["end"] >= oldest:
                    per.setdefault((r.get("start"), r["end"]), []).append(r)
            kind[m] = sorted((r for group in per.values() for r in sorted(group, key=lambda x: x["filed"])[-KEEP_VINTAGES:]), key=lambda x: (x["end"], x["filed"]))
    return out


# ---------------------------------------------------------------------- Korea: period rows from the annual and quarterly series
def _months_before(day: str, months: int) -> str:
    """The first day of the period of ``months`` months that ends on ``day`` (a month end)."""
    nxt = _date(day) + timedelta(days=1)
    y, m = nxt.year, nxt.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, 1).isoformat()


def kr_periods(annual: Dict[str, Any], quarters: Dict[str, Any], months: int) -> Dict[str, Dict[str, List[Dict]]]:
    """``annual`` and ``quarters`` are ``fundamentals.extract_kr`` series: the fiscal years, and the same quarter (the first
    ``months`` months) of several years."""
    def rows(series: Dict[str, Any], key: str, length: Optional[int]) -> List[Dict]:
        return [{**r, **({"start": _months_before(r["end"], length)} if length else {})} for r in series.get(key) or []]
    # Profit and equity are the parent's where the statements have that line, otherwise the whole group's
    # (``fundamentals.extract_kr`` settles it per set of reports).  When the two sets settled it differently, a parent's year would
    # be added to a group's quarter: both are then read as the whole group's, the one figure both sets have.
    annual, quarters = dict(annual), dict(quarters)
    for metric, whole in fundamentals.PARENT_OF.items():
        if (whole in annual) != (whole in quarters):
            for side in (annual, quarters):
                if whole in side:
                    side[metric] = side.pop(whole)
    return {"flow": {k: rows(annual, k, 12) + rows(quarters, k, months) for k in KR_FLOW},
            "instant": {k: sorted(rows(annual, k, None) + rows(quarters, k, None), key=lambda r: (r["end"], r["filed"])) for k in KR_INSTANT}}


# ---------------------------------------------------------------------- the yearly view
def _known(rows: List[Dict], as_of: str) -> List[Dict]:
    """Per period, the newest filing on file by ``as_of``."""
    per: Dict[Tuple, Dict] = {}
    for r in rows:
        if r["filed"] <= as_of:
            k = (r.get("start"), r["end"])
            if k not in per or r["filed"] >= per[k]["filed"]:
                per[k] = r
    return list(per.values())


def _near(rows: List[Dict], key: str, target: date, tol: int = NEAR_DAYS) -> Optional[Dict]:
    best, gap = None, tol + 1
    for r in rows:
        g = abs((_date(r[key]) - target).days)
        if g < gap:
            best, gap = r, g
    return best


def _one_kind(*rows: Dict) -> bool:
    """The same consolidation basis and currency: figures of two kinds are never added."""
    return len({(r.get("basis"), r.get("currency")) for r in rows}) == 1


def trailing_points(rows: List[Dict], as_of: str, agree: Optional[Callable[[Dict, Dict, Dict], bool]] = None) -> List[Dict]:
    """The trailing-four-quarter value at every period end on file by ``as_of``.  A fiscal year is its own value.  A year-to-date
    period needs the fiscal year before it and the same months a year earlier; without both it gives no point."""
    known = _known(rows, as_of)
    fy = [r for r in known if _days(r["start"], r["end"]) >= FY_MIN_DAYS]
    ytd = [r for r in known if _days(r["start"], r["end"]) <= YTD_MAX_DAYS]
    out = {r["end"]: {k: v for k, v in r.items() if k != "start"} for r in fy}
    longest: Dict[str, Dict] = {}
    for r in ytd:
        if r["end"] not in out and (r["end"] not in longest or r["start"] < longest[r["end"]]["start"]):
            longest[r["end"]] = r                       # the year to date, not the three months that end on the same day
    for end, r in longest.items():
        start, length = _date(r["start"]), _days(r["start"], end)
        last_fy = _near(fy, "end", start - timedelta(days=1))
        same = [x for x in ytd if abs(_days(x["start"], x["end"]) - length) <= 15 and abs((_date(x["end"]) - (_date(end) - timedelta(days=365))).days) <= NEAR_DAYS]
        prior = _near(same, "start", start - timedelta(days=365))
        if last_fy and prior and _one_kind(last_fy, r, prior) and (agree is None or agree(last_fy, r, prior)):
            out[end] = {**{k: v for k, v in r.items() if k != "start"}, "val": last_fy["val"] + r["val"] - prior["val"], "filed": max(last_fy["filed"], r["filed"], prior["filed"])}
    return [out[k] for k in sorted(out)]


def newest_reported(rows: List[Dict], as_of: str) -> List[Dict]:
    """Per period end, the shortest period's value: the most current average share count."""
    best: Dict[str, Dict] = {}
    for r in _known(rows, as_of):
        cur = best.get(r["end"])
        if cur is None or _days(r["start"], r["end"]) < _days(cur["start"], cur["end"]):
            best[r["end"]] = r
    return [{k: v for k, v in best[e].items() if k != "start"} for e in sorted(best)]


def yearly(points: List[Dict]) -> List[Dict]:
    """Back from the newest point a year at a time, so every year-over-year figure compares the same quarter."""
    if not points:
        return []
    out = [points[-1]]
    while True:
        target = _date(out[-1]["end"]) - timedelta(days=365)
        hit = _near([p for p in points if p["end"] < out[-1]["end"]], "end", target, YEAR_TOL)
        if not hit:
            return out[::-1]
        out.append(hit)


def _counts_agree(profit: List[Dict], as_of: str) -> Callable[[Dict, Dict, Dict], bool]:
    """For a summed EPS: the share count behind each part (profit / EPS of the same period) must be known and within
    ``COUNT_GAP`` of the others.  A split or a large issue between the parts would otherwise add figures of two share bases."""
    by = {(r["start"], r["end"]): r["val"] for r in _known(profit, as_of)}

    def check(*parts: Dict) -> bool:
        counts = []
        for p in parts:
            n = by.get((p["start"], p["end"]))
            if n is None or not p["val"] or n * p["val"] <= 0:
                return False
            counts.append(n / p["val"])
        return max(counts) / min(counts) < COUNT_GAP
    return check


def view(periods: Dict[str, Dict[str, List[Dict]]], as_of: str, market: str) -> Dict[str, List[Dict]]:
    """Series for ``fundamentals.metrics``: trailing flows, quarter-end balances, a year apart."""
    flow, instant = periods.get("flow") or {}, periods.get("instant") or {}
    out: Dict[str, List[Dict]] = {}
    for m, rows in flow.items():
        if m == "shares_avg":
            out[m] = yearly(newest_reported(rows, as_of))
        elif m != "eps":
            out[m] = yearly(trailing_points(rows, as_of))
    for m, rows in instant.items():
        per: Dict[str, Dict] = {}
        for r in _known(rows, as_of):
            per[r["end"]] = r
        out[m] = yearly([per[k] for k in sorted(per)])
    if market == "US":
        profit = {r["end"]: r for r in out.get("net_income") or []}
        out["eps"] = [{"end": s["end"], "val": profit[s["end"]]["val"] / s["val"], "filed": max(profit[s["end"]]["filed"], s["filed"])}
                      for s in out.get("shares_avg") or [] if s["end"] in profit and s["val"] > 0]
    else:
        out["eps"] = yearly(trailing_points(flow.get("eps") or [], as_of, _counts_agree(flow.get("net_income") or [], as_of)))
    return fundamentals.drop_stale_series(out)


def fiscal_year_ends(periods: Dict[str, Dict[str, List[Dict]]], as_of: str) -> set:
    return {r["end"] for rows in (periods.get("flow") or {}).values() for r in _known(rows, as_of) if _days(r["start"], r["end"]) >= FY_MIN_DAYS}


def metrics(periods: Dict[str, Dict[str, List[Dict]]], close: Optional[float], as_of: str, market: str, **kw: Any) -> Dict[str, Any]:
    """``fundamentals.metrics`` on the trailing view.  ``period_basis`` says whether a quarter newer than the last fiscal year was
    read (TRAILING) or the newest period on file is a fiscal year, in which case the figures are the annual ones (ANNUAL)."""
    series = view(periods, as_of, market)
    m = fundamentals.metrics(series, close, as_of, source=SOURCE[market], **kw)
    if m.get("status") == "UNAVAILABLE":
        return m
    return {**m, "period_basis": "ANNUAL" if m.get("fiscal_end") in fiscal_year_ends(periods, as_of) else "TRAILING"}


# ---------------------------------------------------------------------- Korea: which reports to read
REPORT_OF_MONTHS = {9: "11014", 6: "11012", 3: "11013"}
ASK_AFTER_DAYS = 25             # a quarter's report is not asked for before this many days after the quarter's end
YEARS_BACK = 4                  # the same quarter of this many earlier years


def kr_quarter_candidates(as_of: date, fiscal_month: int = 12) -> List[Tuple[int, int, str]]:
    """(business year, months, period end) of the quarters whose report may be on file, newest first: quarters of the business
    year now running that ended at least ``ASK_AFTER_DAYS`` ago."""
    year = fundamentals.last_business_year(as_of, fiscal_month) + 1
    fy_end = date(year + (fiscal_month == 12), fiscal_month % 12 + 1, 1) - timedelta(days=1)
    start = _months_before(fy_end.isoformat(), 12)
    out = []
    for months in (9, 6, 3):
        y, m = _date(start).year, _date(start).month + months
        while m > 12:
            y, m = y + 1, m - 12
        end = date(y, m, 1) - timedelta(days=1)
        if (as_of - end).days >= ASK_AFTER_DAYS:
            out.append((year, months, end.isoformat()))
    return out


def fill_first_quarter(ytd: Dict[str, Dict], three_months: Dict[str, Dict]) -> Dict[str, Dict]:
    """A first-quarter report often leaves the year-to-date column empty: its three months are the year to date."""
    return {k: (three_months.get(k) if (v or {}).get("status") != "REAL" and (three_months.get(k) or {}).get("status") == "REAL" else v) for k, v in ytd.items()}


KR_KEPT = ("status", "value", "period_end", "receipt_date", "basis", "currency")      # what ``fundamentals.extract_kr`` reads of a concept


def slim(concepts: Dict[str, Dict]) -> Dict[str, Dict]:
    """A report's concepts for the cache: only the fields the series are built from, and only the ones reported."""
    return {k: {f: v.get(f) for f in KR_KEPT} for k, v in concepts.items() if (v or {}).get("status") == "REAL"}


def latest_basis(annual: Dict[str, Any]) -> Optional[str]:
    """The consolidation basis of the newest annual figure: the quarterly reports are read on that basis only."""
    rows = [r for k, v in annual.items() if isinstance(v, list) and not k.startswith("_") for r in v if r.get("basis")]
    return max(rows, key=lambda r: (r["end"], r["filed"]))["basis"] if rows else None
