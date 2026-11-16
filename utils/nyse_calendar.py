"""NYSE regular-session calendar for prospective tracking (P6-20).

Dependency-free (pandas only). Covers:
* regular full-day holidays with NYSE observance rules (Saturday -> Friday,
  Sunday -> Monday; **except** New Year's Day on a Saturday, which NYSE does
  not observe on the preceding Friday);
* scheduled early closes at 13:00 ET (July 3 Mon-Thu, day after Thanksgiving,
  Christmas Eve on a weekday);
* known special closures since 2001 (e.g. national days of mourning).

Unscheduled future closures cannot be known in advance; the tracking layer
therefore never assumes a bar exists - it rolls forward to the first session
whose bar is actually observed and records the delay.
"""
import os
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from typing import Dict, Optional

import pandas as pd
from pandas.tseries.holiday import (GoodFriday, Holiday, MO, USLaborDay, USMartinLutherKingJr,
                                    USMemorialDay, USThanksgivingDay, nearest_workday)

ET = "America/New_York"
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)

SPECIAL_CLOSURES = {
    date(2001, 9, 11), date(2001, 9, 12), date(2001, 9, 13), date(2001, 9, 14),
    date(2004, 6, 11), date(2007, 1, 2), date(2012, 10, 29), date(2012, 10, 30),
    date(2018, 12, 5), date(2025, 1, 9),
}


def extra_closures() -> frozenset:
    """Closures announced after this file was last edited (a day of mourning, a storm), given by the user as
    ``NYSE_EXTRA_CLOSURES=2028-03-06,2029-01-02`` in ``.env`` (reports/RUNBOOK.md).  Without it such a day stays a session on
    this calendar for good: the record screen and the daily message count it as a missing day every day after.  A value that is
    not a date is ignored."""
    out = set()
    for part in os.getenv("NYSE_EXTRA_CLOSURES", "").replace(";", ",").split(","):
        try:
            out.add(date.fromisoformat(part.strip()))
        except ValueError:
            continue
    return frozenset(out)


def _new_year(year: int) -> Optional[date]:
    d = date(year, 1, 1)
    if d.weekday() == 5:          # Saturday: NYSE does not close on Friday Dec 31
        return None
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def holidays(year: int) -> frozenset:
    return _holidays(year, extra_closures())


@lru_cache(maxsize=256)
def _holidays(year: int, extra: frozenset) -> frozenset:
    start, end = pd.Timestamp(year, 1, 1), pd.Timestamp(year, 12, 31)
    rules = [
        USMartinLutherKingJr,
        Holiday("WashingtonsBirthday", month=2, day=1, offset=pd.DateOffset(weekday=MO(3))),
        GoodFriday,
        USMemorialDay,
        Holiday("Juneteenth", month=6, day=19, observance=nearest_workday, start_date="2022-01-01"),
        Holiday("IndependenceDay", month=7, day=4, observance=nearest_workday),
        USLaborDay,
        USThanksgivingDay,
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]
    out = set()
    for rule in rules:
        out.update(d.date() for d in rule.dates(start, end))
    ny = _new_year(year)
    if ny:
        out.add(ny)
    out.update(d for d in SPECIAL_CLOSURES | extra if d.year == year)
    return frozenset(out)


def _as_date(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return pd.Timestamp(d).date()


def is_session(d) -> bool:
    d = _as_date(d)
    return d.weekday() < 5 and d not in holidays(d.year)


def is_early_close(d) -> bool:
    d = _as_date(d)
    if not is_session(d):
        return False
    if d.month == 7 and d.day == 3 and d.weekday() <= 3:
        return True
    if d.month == 12 and d.day == 24:
        return True
    thanksgiving = {h for h in holidays(d.year) if h.month == 11 and h.weekday() == 3}
    return any(d == t + timedelta(days=1) for t in thanksgiving)


def session_close_time(d) -> time:
    return EARLY_CLOSE if is_early_close(d) else REGULAR_CLOSE


def next_session(d) -> date:
    d = _as_date(d) + timedelta(days=1)
    while not is_session(d):
        d += timedelta(days=1)
    return d


def previous_session(d) -> date:
    d = _as_date(d) - timedelta(days=1)
    while not is_session(d):
        d -= timedelta(days=1)
    return d


def sessions_between(start, end):
    """Sessions in [start, end] inclusive."""
    d, end = _as_date(start), _as_date(end)
    out = []
    while d <= end:
        if is_session(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def latest_completed_session(now_utc: Optional[datetime] = None) -> date:
    """Latest session whose daily bar is complete (17:00 ET boundary, as the freshness gate)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    et = pd.Timestamp(now_utc).tz_convert(ET) if pd.Timestamp(now_utc).tzinfo else \
        pd.Timestamp(now_utc).tz_localize("UTC").tz_convert(ET)
    d = et.date()
    if not (is_session(d) and et.time() >= time(17, 0)):
        d = previous_session(d)
    return d


def classify_signal(ts_utc) -> Dict[str, str]:
    """Market phase of a recommendation timestamp and its first eligible entry session.

    Entry reference = the regular-session OPEN of the first session that starts strictly
    after the recommendation became available:
      PREMARKET (session day, before 09:30 ET)         -> that day's open
      REGULAR_SESSION (09:30 ET <= t < close)          -> next session's open
      AFTER_HOURS (session day, at/after the close)    -> next session's open
      NON_SESSION_DAY (weekend / holiday)              -> next session's open
    A regular-session signal is not filled at an intraday price because daily bars do
    not reveal the price at the signal time; the next open is the first price observable
    without look-ahead.
    """
    ts = pd.Timestamp(ts_utc)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    et = ts.tz_convert(ET)
    d = et.date()
    if is_session(d):
        if et.time() < REGULAR_OPEN:
            phase, entry = "PREMARKET", d
        elif et.time() < session_close_time(d):
            phase, entry = "REGULAR_SESSION", next_session(d)
        else:
            phase, entry = "AFTER_HOURS", next_session(d)
    else:
        phase, entry = "NON_SESSION_DAY", next_session(d)
    return {"signal_utc": ts.isoformat(), "signal_et": et.isoformat(), "exchange_timezone": ET,
            "signal_calendar_date_et": d.isoformat(), "market_phase": phase,
            "entry_session": entry.isoformat(), "entry_session_early_close": is_early_close(entry)}
