"""markets/session_data.py: the one place that says whether a session's data has arrived.  Each case below is something the
provider really returned (dates in the module's table) and the recorder it broke."""
import inspect
from datetime import datetime, timezone

import pandas as pd
import pytest

from markets import session_data as sd
from markets.kr import acquisition, pipeline, tracking
from terminal.qsf import service

NAN = float("nan")
MORNING = datetime(2026, 11, 13, 23, 50, tzinfo=timezone.utc)        # 2026-11-14 08:50 KST, a Saturday


def _bars(days, close=None):
    n = len(days)
    return pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": close if close is not None else [1.0] * n}, index=pd.DatetimeIndex(days))


# ----------------------------------------------------------------------------- which days were sessions
def test_calendar_follows_the_anchor_when_the_index_is_a_session_behind():
    """2026-11-13 morning: the index ended at 11-11, the stocks had 11-12, and the model scan scored the day before."""
    cal = sd.kr_calendar(_bars(["2026-11-10", "2026-11-11"]), _bars(["2026-11-10", "2026-11-11", "2026-11-12"]), datetime(2026, 11, 12, 23, tzinfo=timezone.utc))
    assert cal.latest == pd.Timestamp("2026-11-12") and cal.index_behind
    assert cal.summary() == {"latest": "2026-11-12", "index_last": "2026-11-11", "anchor_last": "2026-11-12", "index_behind": True, "notes": []}


def test_calendar_without_the_anchor_is_the_index_alone_and_says_so():
    cal = sd.kr_calendar(_bars(["2026-11-12", "2026-11-13"]), None, MORNING)
    assert cal.latest == pd.Timestamp("2026-11-13") and not cal.index_behind and cal.notes == ["ANCHOR_UNAVAILABLE"]
    assert sd.kr_calendar(pd.DataFrame(), _bars(["2026-11-13"]), MORNING).notes == ["INDEX_UNAVAILABLE"]
    with pytest.raises(ValueError):
        sd.kr_calendar(pd.DataFrame(), None, MORNING)


def test_calendar_never_takes_a_bar_that_is_not_complete_by_the_clock():
    intraday = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)      # 12:00 KST on the 13th: the day's bar is a partial one
    cal = sd.kr_calendar(_bars(["2026-11-12", "2026-11-13"]), _bars(["2026-11-12", "2026-11-13"]), intraday)
    assert cal.latest == pd.Timestamp("2026-11-12")


def test_an_anchor_bar_without_a_close_is_not_a_session():
    cal = sd.kr_calendar(_bars(["2026-11-12"]), _bars(["2026-11-12", "2026-11-13"], close=[1.0, NAN]), MORNING)
    assert cal.latest == pd.Timestamp("2026-11-12")


def test_an_index_bar_with_an_open_only_still_says_the_day_was_a_session():
    """Two questions kept apart: the day happened (calendar), but its index value cannot be used yet (whole_index)."""
    idx = _bars(["2026-11-12", "2026-11-13"], close=[1.0, NAN])
    assert sd.kr_calendar(idx, None, MORNING).latest == pd.Timestamp("2026-11-13")
    kept, held = sd.whole_index(idx)
    assert list(kept.index) == [pd.Timestamp("2026-11-12")] and held == ["2026-11-13"]


def test_latest_complete_date_reads_index_and_anchor_rows_together():
    rows = [{"date": "2026-11-11"}, {"date": "2026-11-12"}, {"date": "2026-11-13"}, {"date": "2026-11-14"}]
    assert sd.latest_complete_date(rows, MORNING) == "2026-11-13"              # the 14th is today and not complete
    assert sd.latest_complete_date(reversed(rows), MORNING) == "2026-11-13"    # order does not matter
    assert sd.latest_complete_date([], MORNING) is None


# ----------------------------------------------------------------------------- index values
def test_whole_index_stops_at_the_first_hole_and_never_skips_a_day():
    days = pd.bdate_range("2026-11-02", periods=5)
    kept, held = sd.whole_index(_bars(days, close=[1.0, 1.0, NAN, 1.0, 1.0]))
    assert list(kept.index) == list(days[:2]) and held == ["2026-11-04", "2026-11-05", "2026-11-06"]
    assert sd.whole_index(_bars(days))[1] == [] and sd.whole_index(pd.DataFrame())[1] == [] and sd.whole_index(None) == (None, [])
    text = _bars(days, close=["1.0", "x", "1.0", "1.0", "1.0"])                # a value that is not a number is a hole too
    assert sd.whole_index(text)[1][0] == "2026-11-03"


# ----------------------------------------------------------------------------- did the stocks reach the session
def _store(share_at):
    rows = []
    for i in range(100):
        rows.append({"ticker": f"{i:06d}", "date": pd.Timestamp("2026-11-10")})
        if i < share_at:
            rows.append({"ticker": f"{i:06d}", "date": pd.Timestamp("2026-11-11")})
    return pd.DataFrame(rows)


def test_a_store_taken_while_the_day_was_being_published_is_not_reused():
    """2026-11-11 02:27 KST: 28% of the symbols had the day; the file was reused and two stocks were scored."""
    assert not sd.store_reaches(_store(28), "2026-11-11")
    assert not sd.store_reaches(_store(79), "2026-11-11")
    assert sd.store_reaches(_store(80), "2026-11-11") and sd.store_reaches(_store(100), "2026-11-11")
    assert not sd.store_reaches(pd.DataFrame(), "2026-11-11") and not sd.store_reaches(None, "2026-11-11")


def test_rows_at_the_session_ignores_later_bars_and_empty_series():
    rows = [{"date": "2026-11-12"}, {"date": "2026-11-13"}, {"date": "2026-11-16"}]
    assert sd.rows_at(rows, "2026-11-13") and not sd.rows_at(rows, "2026-11-14")
    assert not sd.rows_at([], "2026-11-13") and not sd.rows_at(None, "2026-11-13")
    assert sd.count_at([rows, [], None, rows[:1]], "2026-11-13") == 1
    assert sd.enough(270, 300) and not sd.enough(269, 300)


def test_verdict_holds_a_day_back_for_any_one_failed_check_and_names_the_cause():
    ok = sd.record_verdict(300, 300)
    assert ok == {"ready": True, "reason": None, "few": False}
    assert sd.record_verdict(300, 0)["reason"] == sd.NOT_PUBLISHED                       # 2026-11-14 00:08: every bar empty
    assert sd.record_verdict(300, 0, failures=["ConnectionError"])["reason"] == sd.DOWNLOAD_FAILED   # asleep, not unpublished
    assert sd.record_verdict(2, 2, small=True)["reason"] == sd.UNIVERSE_TOO_SMALL        # 2026-11-11: two stocks, both "at the session"
    assert sd.record_verdict(300, 300, behind=True)["reason"] == sd.KR_BEHIND
    assert sd.record_verdict(504, 504, bench_ok=False)["reason"] == sd.BENCHMARK_NOT_READY
    assert sd.record_verdict(0, 0)["reason"] == sd.NOT_PUBLISHED                         # nothing to score is not a day
    assert all(not sd.record_verdict(300, 300, **{k: v})["ready"] for k, v in (("bench_ok", False), ("behind", True), ("small", True)))
    assert {sd.record_verdict(300, n)["ready"] for n in (270, 300)} == {True} and not sd.record_verdict(300, 269)["ready"]


# ----------------------------------------------------------------------------- every recorder asks here
def test_the_recorders_use_this_module_and_keep_no_rule_of_their_own():
    assert acquisition._reaches is sd.store_reaches and acquisition.STALE_CACHE_SHARE == sd.STORE_REUSE_SHARE
    assert tracking.whole_index is sd.whole_index
    assert pipeline.CALENDAR_ANCHOR == sd.KR_ANCHOR and "session_data.kr_calendar" in inspect.getsource(pipeline._prepare)
    src = inspect.getsource(service.QSF.scan) + inspect.getsource(service.QSF._session_bars) + inspect.getsource(service.QSF._session)
    assert "session_data.record_verdict" in src and "session_data.count_at" in src and "session_data.latest_complete_date" in src
    assert "0.9 *" not in inspect.getsource(service) and "0.8" not in inspect.getsource(acquisition.bars)


def test_the_score_scan_reports_the_module_reason(tmp_path):
    q = service.QSF(tmp_path, now=lambda: MORNING)
    q._download_failures, q._download_chunks = ["EMPTY_REPLY"], 3
    pre = {"A": {"bars": [{"date": "2026-11-12"}], "bench": []}, "B": {"bars": [], "bench": []}}
    out = q._not_ready_reason(pre, "2026-11-13", sd.record_verdict(2, 0, q._download_failures))
    assert out["reason"] == sd.DOWNLOAD_FAILED and out["download"] == {"chunks": 3, "failed": 1, "kinds": {"EMPTY_REPLY": 1}}
    assert out["last_dates"] == {"2026-11-12": 1} and out["no_bars"] == 1
