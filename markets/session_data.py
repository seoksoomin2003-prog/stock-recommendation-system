"""Has the data of the session a recorder is about to use arrived?  The one place that answers it.

Every recorder (the score scan, the Korean model scan, paper tracking, the stored downloads) asks this first, and each used to
answer it with its own code.  The free provider (Yahoo) publishes a Korean day in pieces, and each piece broke a different
recorder once.  What was measured, and the rule each led to:

==================  ==========================================================  ==========================================
when (KST)          what the provider returned                                  rule here
==================  ==========================================================  ==========================================
2026-11-10 night    requests failed outright (the Mac asleep mid-download)      a failed request is told apart from a day
                                                                                not published (``record_verdict``)
2026-11-11 02:27    the day's bar for 28% of the stocks; the stored file was    a stored download is reused only when most
                    reused all day and a scan of two stocks was recorded        symbols reach the session (``store_reaches``)
2026-11-13 07-09    the KOSPI index series a session behind the stocks; the     the calendar also follows a large
                    model scan scored the day before the last one               constituent (``kr_calendar``)
2026-11-14 00:08    the index had the day, the day's bar was empty for every    a day is recorded only when nearly all
                    one of 300 stocks                                           stocks are at the session (``record_verdict``)
2026-11-14 09:01    the index bar of the last session with an open and no       an index *value* counts only from a bar
                    close; 30 comparisons were stored as not-a-number           with both (``whole_index``)
==================  ==========================================================  ==========================================

Two different questions are kept apart on purpose.  *Which days were sessions* (``kr_calendar``): any completed bar of the index
or of the anchor stock is evidence.  *What the index was worth* (``whole_index``): only a bar with an open and a close.  The
tracker measures a stock against the index, so its calendar is the second kind; the scans only need the first.

Records built from the KRX daily files (regime weights, the Korean method, the market-value universe) do not come through here:
a KRX day is on file whole or not at all.  The US calendar is the exchange clock (``utils/nyse_calendar``); the shares below are
what the US scan uses as well.

Nothing here downloads, scores or writes.  The thresholds are the ones the recorders already used; they are named once here.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from markets.kr import calendar as krcal

KR_ANCHOR = "005930.KS"        # Samsung Electronics: trades on every KRX session
STORE_REUSE_SHARE = 0.8        # a stored download where fewer symbols than this reach the session was taken too early
RECORD_SHARE = 0.9             # a day is recorded, and a chunk kept for the day, only with this share of stocks at the session

DOWNLOAD_FAILED = "DOWNLOAD_FAILED"                # price requests failed outright: the day may well be published
KR_BEHIND = "KR_BEHIND"                            # the Korean session found is older than the last weekday that should be complete
UNIVERSE_TOO_SMALL = "UNIVERSE_TOO_SMALL"          # the Korean universe came out far below its size, which a partial day does
NOT_PUBLISHED = "NOT_PUBLISHED"                    # replies came back without the session for too many stocks
BENCHMARK_NOT_READY = "BENCHMARK_NOT_READY"        # the benchmark has no bar at the session
REASONS = (DOWNLOAD_FAILED, KR_BEHIND, UNIVERSE_TOO_SMALL, NOT_PUBLISHED, BENCHMARK_NOT_READY)


# ----------------------------------------------------------------------------- index values
def whole_index(df: pd.DataFrame, need: Sequence[str] = ("Open", "Close")) -> Tuple[pd.DataFrame, List[str]]:
    """The index bars whose values may be used, and the dates held back.  A bar counts when every column in ``need`` is a finite
    number.  The series ends before its first bar that is not whole, so a day is never skipped: it joins when the source has it."""
    if df is None or df.empty:
        return df, []
    ok = np.ones(len(df), dtype=bool)
    for col in need:
        ok &= np.isfinite(pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float))
    if bool(ok.all()):
        return df, []
    cut = int(np.argmin(ok))
    return df.iloc[:cut], [str(pd.Timestamp(d).date()) for d in df.index[cut:]]


# ----------------------------------------------------------------------------- which days were sessions
@dataclass(frozen=True)
class Calendar:
    """The KRX sessions seen so far.  ``index_last`` and ``anchor_last`` say where each source ends, so a caller can report a lag."""
    sessions: pd.DatetimeIndex
    latest: pd.Timestamp
    index_last: Optional[pd.Timestamp] = None
    anchor_last: Optional[pd.Timestamp] = None
    notes: List[str] = field(default_factory=list)

    @property
    def index_behind(self) -> bool:
        return self.index_last is not None and self.index_last < self.latest

    def summary(self) -> Dict[str, Any]:
        day = lambda t: None if t is None else str(pd.Timestamp(t).date())       # noqa: E731
        return {"latest": day(self.latest), "index_last": day(self.index_last), "anchor_last": day(self.anchor_last),
                "index_behind": self.index_behind, "notes": list(self.notes)}


def _days(df: Optional[pd.DataFrame], now, close_col: Optional[str] = None) -> pd.DatetimeIndex:
    if df is None or df.empty:
        return pd.DatetimeIndex([])
    if close_col:
        df = df.dropna(subset=[close_col])
    return pd.DatetimeIndex(pd.to_datetime(krcal.drop_incomplete(df, now).index)).normalize()


def kr_calendar(index: pd.DataFrame, anchor: Optional[pd.DataFrame], now) -> Calendar:
    """Sessions = the days the KOSPI index has a completed bar, joined with the days the anchor stock closed.  The index alone can
    end a session behind in the morning; the anchor alone would do as well, and both are read so that one failed request does not
    move the calendar.  Raises when neither has a day."""
    idx, anc = _days(index, now), _days(anchor, now, "Close")
    sessions = idx.union(anc)
    if len(sessions) == 0:
        raise ValueError("no completed KRX session observed")
    notes = []
    if len(anc) == 0:
        notes.append("ANCHOR_UNAVAILABLE")
    if len(idx) == 0:
        notes.append("INDEX_UNAVAILABLE")
    return Calendar(sessions=sessions, latest=pd.Timestamp(sessions.max()).normalize(), index_last=idx.max() if len(idx) else None,
                    anchor_last=anc.max() if len(anc) else None, notes=notes)


def latest_complete_date(rows: Iterable[Dict[str, Any]], now) -> Optional[str]:
    """The newest date among daily rows (dicts with ``date``) whose bar is complete by the clock; None when there is none.  The
    caller passes the index rows and the anchor's rows together."""
    days = sorted(r["date"] for r in rows if krcal.bar_is_complete(r["date"], now))
    return days[-1] if days else None


# ----------------------------------------------------------------------------- did the stocks reach the session
def store_reaches(df: pd.DataFrame, session, share: float = STORE_REUSE_SHARE) -> bool:
    """True when most symbols of a stored download (long frame: ticker, date) have a bar on ``session`` or later.  A complete
    download has it for every symbol (measured on six stored files: 100%); one taken while the provider was still publishing the
    day has it for a part (28% on 2026-11-11 02:27 KST)."""
    if df is None or df.empty:
        return False
    last = df.groupby("ticker")["date"].max()
    return float((last >= pd.Timestamp(session)).mean()) >= share


def rows_at(rows: Optional[List[Dict[str, Any]]], session: str) -> bool:
    """True when the newest bar on or before ``session`` is the session's own."""
    cut = [r for r in rows or [] if r["date"] <= session]
    return bool(cut) and cut[-1]["date"] == session


def count_at(series: Iterable[Optional[List[Dict[str, Any]]]], session: str) -> int:
    return sum(1 for rows in series if rows_at(rows, session))


def enough(at_session: int, total: int, share: float = RECORD_SHARE) -> bool:
    return at_session >= share * total


def record_verdict(total: int, at_session: int, failures: Sequence[str] = (), bench_ok: bool = True, behind: bool = False,
                   small: bool = False) -> Dict[str, Any]:
    """Whether a scan of ``total`` stocks, ``at_session`` of them at the session, may be recorded as the day.  Recording a day of
    partial bars stores it for good, so any one failed check holds the record back and the scan is tried again later.  ``reason``
    names the first cause in the order a person would look for it: a failed request before a day not published."""
    few = not enough(at_session, max(total, 1))
    if bench_ok and not behind and not small and not few:
        return {"ready": True, "reason": None, "few": False}
    reason = DOWNLOAD_FAILED if failures else KR_BEHIND if behind else UNIVERSE_TOO_SMALL if small else NOT_PUBLISHED if few else BENCHMARK_NOT_READY
    return {"ready": False, "reason": reason, "few": few}
