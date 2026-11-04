"""KRX session rules (KR-DATA-0.1).

KRX regular session 09:00-15:30 Asia/Seoul.  Holidays are *observed*, not hard-coded: a date is a KRX
session iff the KOSPI index (^KS11) has a daily bar for it.  This avoids an unverified lunar-holiday
table.  Future-session logic therefore never names a date in advance: the paper entry is "the first
observed session on/after ``entry_not_before``", resolved only when the bar exists.

A daily bar dated D is treated as complete only after 18:00 KST on D (the close is 15:30; the margin
covers provider delay), so an intraday partial bar can never be used as a close.
"""
from datetime import time
from typing import Any, Dict

import pandas as pd

KST = "Asia/Seoul"
SESSION_OPEN = time(9, 0)
SESSION_CLOSE = time(15, 30)
BAR_COMPLETE_AFTER = time(18, 0)


def to_kst(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert(KST)


def bar_is_complete(bar_date, now) -> bool:
    n = to_kst(now)
    d = pd.Timestamp(bar_date).date()
    if d < n.date():
        return True
    return d == n.date() and n.time() >= BAR_COMPLETE_AFTER


def drop_incomplete(frame: pd.DataFrame, now, date_col: str = None) -> pd.DataFrame:
    """Drop rows whose daily bar is not complete yet (index or ``date_col`` holds the bar date)."""
    dates = frame[date_col] if date_col else frame.index.to_series()
    keep = [bar_is_complete(d, now) for d in dates]
    return frame[keep]


def classify_signal(ts) -> Dict[str, Any]:
    """Entry rule for a recommendation made at ``ts``.

    Before 09:00 KST on a weekday      -> PREMARKET:     entry at that day's open if it is a session.
    Any later time, or a weekend        -> next session:  entry at the open of the first session after
                                                          the signal date.
    ``entry_not_before`` is a calendar date; the actual entry session is the first observed KRX
    session on/after it (holidays are skipped automatically)."""
    k = to_kst(ts)
    d = k.normalize().tz_localize(None)
    if k.weekday() < 5 and k.time() < SESSION_OPEN:
        cls, nb = "PREMARKET", d
    elif k.weekday() < 5 and k.time() <= SESSION_CLOSE:
        cls, nb = "REGULAR_SESSION", d + pd.Timedelta(days=1)
    elif k.weekday() < 5:
        cls, nb = "AFTER_CLOSE", d + pd.Timedelta(days=1)
    else:
        cls, nb = "NON_SESSION_DAY", d + pd.Timedelta(days=1)
    return {"signal_utc": k.tz_convert("UTC").isoformat(), "signal_kst": k.isoformat(),
            "classification": cls, "entry_not_before": str(nb.date()),
            "entry_rule": "open of the first observed KRX session on/after entry_not_before"}


def latest_completed_session(index_bars: pd.DataFrame, now) -> pd.Timestamp:
    complete = drop_incomplete(index_bars, now)
    if complete.empty:
        raise ValueError("no completed KRX session observed")
    return pd.Timestamp(complete.index.max()).normalize()
