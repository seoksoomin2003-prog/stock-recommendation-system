"""Forward record status: what counts as matured, missing and ready, and that an unknown calendar never reads as complete.  No network."""
import json

from terminal import record_status as rs
from terminal.qsf import config


def _days(n, start=1):
    return [f"2027-01-{d:02d}" for d in range(start, start + n)]


def test_a_session_matures_only_after_h_more_sessions():
    cal = _days(10)
    assert rs.matured_count(["2027-01-01"], cal, 9) == 1
    assert rs.matured_count(["2027-01-01"], cal, 10) == 0
    assert rs.matured_count(["2027-01-05", "2027-01-08"], cal, 3) == 1


def test_remaining_counts_recording_and_the_final_wait():
    assert rs.remaining_sessions(0, 0, 20) == 240 + 20
    assert rs.remaining_sessions(240, 220, 20) == 20
    assert rs.remaining_sessions(300, 240, 20) == 0


def test_ready_uses_the_ledgers_own_minimum():
    h = 5
    cal = _days(31) + [f"2027-02-{d:02d}" for d in range(1, 29)] + [f"2027-03-{d:02d}" for d in range(1, 11)]
    recorded = cal[:config.MIN_INDEPENDENT * h]
    row = next(r for r in rs.progress_rows(recorded, cal) if r["strategy"] == "SWING" and r["horizon"] == h)
    assert row["ready"] and row["independent"] == config.MIN_INDEPENDENT and row["remaining_sessions"] == 0


def test_one_short_of_the_minimum_is_not_ready():
    h = 5
    cal = _days(31) + [f"2027-02-{d:02d}" for d in range(1, 29)] + [f"2027-03-{d:02d}" for d in range(1, 11)]
    recorded = cal[:config.MIN_INDEPENDENT * h - 1]
    row = next(r for r in rs.progress_rows(recorded, cal) if r["strategy"] == "SWING" and r["horizon"] == h)
    assert not row["ready"] and row["remaining_sessions"] > 0


def test_nothing_is_owed_before_the_first_record():
    cal = _days(5)
    assert rs.missing_sessions(["2027-01-03", "2027-01-05"], cal) == ["2027-01-04"]
    assert rs.missing_sessions([], cal) == []


def _row(session, version=config.MODEL_VERSION, records=10):
    return {"session": session, "model_version": version, "records": records}


def test_an_earlier_version_does_not_count_toward_progress():
    r = rs.market_record([_row("2027-01-01", "QSF-1.1.2"), _row("2027-01-02")], _days(3))
    assert r["sessions"] == 2 and r["current_version_sessions"] == 1 and r["behind_sessions"] == 1
    assert all(p["matured_sessions"] == 0 for p in r["progress"])


def test_an_unknown_calendar_is_reported_not_treated_as_complete():
    r = rs.market_record([_row("2027-01-01")], None)
    assert r["calendar_status"] == "UNAVAILABLE" and r["missing"] is None and r["behind_sessions"] is None
    texts = [a["text"] for a in rs.alerts({"KR": r}, {"status": "REAL", "capital_configured": True}, {"installed": True}, "OK")]
    assert any("확인할 수 없습니다" in t for t in texts)


def test_baseline_counts_only_valid_completed_outcomes_and_distinct_days():
    status = {"run_cohorts": {"20270101T1_x": "VALID_PROSPECTIVE", "20270101T2_y": "VALID_PROSPECTIVE", "20261231T1_z": "PRE_FIX_EXCLUDED", "20270105T1_w": "VALID_PROSPECTIVE"},
              "outcome_states": {"VALID_PROSPECTIVE/COMPLETED_OUTCOME": 4, "VALID_PROSPECTIVE/PENDING_OUTCOME": 6, "PRE_FIX_EXCLUDED/COMPLETED_OUTCOME": 99},
              "by_class_and_cohort": {"PORTFOLIO_TOP5/VALID_PROSPECTIVE": 10}, "latest_update": {"as_of_session": "2027-01-05"}}
    b = rs.baseline_record(True, status)
    assert b["completed"] == 4 and b["pending"] == 6 and b["scan_dates"] == 2 and b["last_scan_date"] == "2027-01-05"


def test_empty_capital_raises_the_top_alert():
    out = rs.alerts({}, {"status": "REAL", "capital_configured": False}, {"installed": True}, "OK")
    assert out[0]["level"] == "bad" and "자본금" in out[0]["text"]


def test_a_failed_step_and_a_gap_are_both_named():
    r = rs.market_record([_row("2027-01-01"), _row("2027-01-03")], _days(3))
    out = rs.alerts({"US": r}, {"status": "REAL", "capital_configured": True}, {"installed": True, "steps": {"QSF": {"status": rs.automation.FAILED}}}, "OK")
    text = json.dumps(out, ensure_ascii=False)
    assert "QSF 기록(미국)" in text and "2027-01-02" in text


def test_nothing_on_the_page_reads_as_a_performance_claim():
    r = rs.market_record([], _days(3))
    assert "mean" not in json.dumps(r) and "return" not in json.dumps(r)


def test_one_session_behind_is_normal_and_two_is_not():
    ok = {"status": "REAL", "capital_configured": True}
    auto = {"installed": True}
    assert rs.alerts({"KR": rs.market_record([_row("2027-01-01")], _days(2))}, ok, auto, "OK") == []
    assert "뒤처져" in rs.alerts({"KR": rs.market_record([_row("2027-01-01")], _days(3))}, ok, auto, "OK")[0]["text"]



def test_the_korean_record_is_watched():
    base = {"status": "REAL", "capital_configured": True}
    auto = {"installed": True, "steps": {}}
    text = lambda f: [a["text"] for a in rs.alerts({}, base, auto, "OK", f)]     # noqa: E731
    assert not text({"integrity": "OK", "sessions": 3, "behind_sessions": 1})
    assert "뒤처져" in text({"integrity": "OK", "sessions": 3, "behind_sessions": 2})[0]
    assert "아직 없습니다" in text({"integrity": "OK", "sessions": 0})[0]
    assert "검증에 실패" in text({"integrity": "BROKEN", "sessions": 3})[0]


def test_a_price_gap_with_krx_is_an_alert():
    base = {"status": "REAL", "capital_configured": True}
    auto = {"installed": True, "steps": {}}
    good = {"integrity": "OK", "sessions": 3, "behind_sessions": 0, "price_check": {"session": "d", "gaps": 0, "stale": 0}}
    assert not rs.alerts({}, base, auto, "OK", good)
    bad = {**good, "price_check": {"session": "d", "gaps": 2, "stale": 0}}
    assert "KRX 종가와 다른 종목 2개" in rs.alerts({}, base, auto, "OK", bad)[0]["text"]


def test_us_challenger_alerts_only_when_something_is_wrong():
    base, auto = {"status": "REAL", "capital_configured": True}, {"installed": True}
    text = lambda c: [a["text"] for a in rs.alerts({}, base, auto, "OK", None, c)]     # noqa: E731
    assert not text({"integrity": "OK", "sessions": 0, "behind_sessions": None, "due_sessions": 0})      # before the first session nothing is owed
    assert not text({"integrity": "OK", "sessions": 5, "behind_sessions": 1, "due_sessions": 6})
    assert "시작되지 않았습니다" in text({"integrity": "OK", "sessions": 0, "behind_sessions": None, "due_sessions": 2})[0]
    assert "2거래일 뒤처져" in text({"integrity": "OK", "sessions": 5, "behind_sessions": 2, "due_sessions": 7})[0]
    assert "검증에 실패" in text({"integrity": "BROKEN", "sessions": 5, "behind_sessions": 0, "due_sessions": 5})[0]


def test_backup_alerts():
    assert rs.backup_alerts({"latest": "2026-11-06", "age_days": 2}) == []
    assert "일 전" in rs.backup_alerts({"latest": "2026-11-01", "age_days": 7})[0]["text"]
    assert rs.backup_alerts({"latest": None, "age_days": None})[0]["level"] == "warn"
