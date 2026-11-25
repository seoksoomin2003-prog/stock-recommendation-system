"""Is the last daily bar on a screen the newest one there should be?  (third maturity assessment, 2026-11-25, P0 item 2)

The score path has judged a price by the market's session since QSF-1.1 (terminal/qsf/service.py ``_session``).  The screens
(quote tiles, charts, the trade forms' price, the alert check) called a bar REAL when it lay within five calendar days, so a
reply that stopped two to four days earlier (Yahoo did that on 2026-11-24) was shown as current and an alert was judged on it.

Rule here, per kind of symbol:
- US stocks, funds and US indices: the NYSE calendar (``utils/nyse_calendar``).  Any completed session after the bar is a miss.
- Korean stocks, funds and indices: no holiday list is kept for Korea, so one missing weekday is allowed (it may be a holiday)
  and two are a miss.  Inside one reply, a Korean symbol older than another Korean symbol of that reply is a miss too: the
  newer one proves the session happened.
- Everything else (currencies, futures, rates, foreign indices): two missing weekdays are a miss.
A miss reads STALE.  Nothing here feeds a score.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from utils import nyse_calendar

SEOUL = ZoneInfo("Asia/Seoul")
KR_INDEX = ("^KS11", "^KQ11", "^KS200")
US_INDEX = ("^GSPC", "^IXIC", "^DJI", "^RUT", "^VIX", "^NDX", "^SOX")
KR_DONE = (15, 45)          # the close plus the settlement allowance terminal.services._intraday uses


def kind(symbol: str) -> str:
    s = (symbol or "").upper()
    if s.endswith((".KS", ".KQ")) or s in KR_INDEX or (s.isdigit() and len(s) == 6):
        return "KR"
    if s in US_INDEX:
        return "US"
    if s.startswith("^") or "=" in s or s.endswith(".NYB") or s.endswith("-USD"):
        return "OTHER"
    return "US"


def _day(d) -> date:
    return d if isinstance(d, date) and not isinstance(d, datetime) else datetime.strptime(str(d)[:10], "%Y-%m-%d").date()


def _weekdays_after(last: date, ref: date) -> int:
    n, d = 0, last + timedelta(days=1)
    while d <= ref:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


def expected(group: str, now: datetime) -> date:
    """The newest day a completed daily bar can exist for.  US: the NYSE's latest completed session.  Otherwise the latest
    weekday whose Korean session has ended by the clock (holidays unknown)."""
    if group == "US":
        return nyse_calendar.latest_completed_session(now)
    local = now.astimezone(SEOUL)
    d = local.date()
    if not (d.weekday() < 5 and (local.hour, local.minute) >= KR_DONE):
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def missed(last_date, ref: date, group: str) -> int:
    """Sessions after the bar up to ``ref`` that should have a bar.  Korea and the rest forgive one weekday."""
    last = _day(last_date)
    if last >= ref:
        return 0
    if group == "US":
        return len(nyse_calendar.sessions_between(last + timedelta(days=1), ref))
    return max(0, _weekdays_after(last, ref) - 1)


def behind(last_date, symbol: str, now: datetime, ref: Optional[date] = None, newest_in_reply: Optional[str] = None) -> bool:
    """True when the bar is older than it should be.  ``ref``: judge against this day instead of today's expected session, never
    later than it (a trade form asking for a past date).  ``newest_in_reply``: the newest bar date among the same kind of symbols
    in the same reply."""
    group = kind(symbol)
    exp = expected(group, now)
    if missed(last_date, min(ref, exp) if ref else exp, group) > 0:
        return True
    return bool(newest_in_reply) and ref is None and group == "KR" and str(last_date)[:10] < str(newest_in_reply)[:10]


def newest(dates_by_symbol: Iterable, group: str = "KR") -> Optional[str]:
    """The newest bar date among the symbols of one kind in a reply: [(symbol, date), ...]."""
    got = [str(d)[:10] for s, d in dates_by_symbol if d and kind(s) == group]
    return max(got) if got else None
