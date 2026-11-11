"""The next earnings date estimated from the company's own past dates, for stocks whose calendar date is missing.

Yahoo shows no upcoming date for most Korean stocks and, right after a report, for about half of the US ones.  Those stocks were
never held back before earnings.  A company reports a quarter close to the day it reported the same quarter a year earlier: in the
2026-11-11 check the estimate was within 7 days for 96% of Korean preliminary results and 90% of US 8-K item 2.02 filings
(reports/QSF_EARNINGS_DATE_RESEARCH_2026_11_11.md).  An estimate is an estimate: it is labelled, and the rule that reads it uses a
wider window than for a calendar date.  Nothing here says the rule earns anything; it keeps a known event from being walked into.

Pure functions: the caller passes the dates it already has.
"""
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional

LOOKBACK_DAYS = 460        # past events this recent give an estimate: the last five quarters
MATCH_DAYS = 21            # an actual event this close to an estimate is that estimate's event
MIN_GAP_DAYS = 200         # and it must be of the following year, not the same event again
OVERDUE_DAYS = 14          # an estimate this far behind with no event is given up (99% of Korean events came within 14 days)
MAX_EVENTS = 7             # more past events than this in the window is not a quarterly pattern (monthly sales under the same title)

KR_PRELIMINARY = "영업(잠정)실적"
KR_CONSOLIDATED = "연결재무제표기준영업(잠정)실적"
KR_PERIODIC = ("분기보고서", "반기보고서", "사업보고서")
US_RESULTS_ITEM = "2.02"


def _day(text: str) -> Optional[date]:
    s = str(text or "").replace("-", "")
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def _year_on(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:                                   # 29 February
        return d.replace(year=d.year + 1, day=28)


def next_estimate(past: Iterable[str], as_of: str) -> Optional[Dict[str, Any]]:
    """The earliest estimate not yet met by an actual event.  ``overdue``: the estimated day has passed and no event has come."""
    a = _day(as_of)
    events = sorted({d for d in (_day(x) for x in past) if d and d <= a})
    recent = [d for d in events if (a - d).days <= LOOKBACK_DAYS]
    if not recent or len(recent) > MAX_EVENTS:
        return None
    pending = []
    for d in recent:
        c = _year_on(d)
        met = any(abs((e - c).days) <= MATCH_DAYS for e in events if (e - d).days >= MIN_GAP_DAYS)
        if not met and c >= a - timedelta(days=OVERDUE_DAYS):
            pending.append((c, d))
    if not pending:
        return None
    c, d = min(pending)
    return {"date": c.isoformat(), "from": d.isoformat(), "overdue": c < a}


def us_result_dates(filings: Iterable[Dict[str, Any]]) -> List[str]:
    """Filing dates of 8-Ks carrying Item 2.02 (results of operations), from the stored SEC list."""
    return sorted({f["date"] for f in filings or [] if f.get("form") == "8-K" and US_RESULTS_ITEM in [x.strip() for x in str(f.get("items") or "").split(",")] and f.get("date")})


def kr_result_dates(rows: Iterable[Dict[str, Any]], as_of: Optional[str] = None) -> Dict[str, Any]:
    """From DART list rows (report_nm, rcept_dt): the preliminary results disclosures, the consolidated title preferred because the
    plain one also carries monthly sales for some companies; without any, the periodic reports.  Corrections are not events.
    With ``as_of``: a company whose preliminary title appears more often than quarterly (monthly figures) is read by its periodic
    reports instead."""
    first = [r for r in rows or [] if not str(r.get("report_nm") or "").lstrip().startswith("[") and r.get("rcept_dt")]
    def dates(match):
        return sorted({f"{r['rcept_dt'][:4]}-{r['rcept_dt'][4:6]}-{r['rcept_dt'][6:8]}" for r in first if match(str(r["report_nm"]))})
    def quarterly(found):
        a = _day(as_of) if as_of else None
        return not a or sum(1 for d in found if 0 <= (a - _day(d)).days <= LOOKBACK_DAYS) <= MAX_EVENTS
    for found in (dates(lambda n: KR_CONSOLIDATED in n), dates(lambda n: KR_PRELIMINARY in n)):
        if found and quarterly(found):
            return {"dates": found, "kind": "PRELIMINARY"}
    return {"dates": dates(lambda n: any(k in n for k in KR_PERIODIC)), "kind": "PERIODIC"}
