"""The Korean model scan as a step of the daily job (user decision 2026-11-12, moved to the evening 2026-11-13): once per Korean
weekday from 18:00 Seoul time, never in the morning, never beside or after a scan started from the screen for the same session."""
import json
import os
from datetime import datetime, timezone

from terminal import automation, model_scan as ms
from tests.test_terminal_4 import TUE_NIGHT, make
from tests.test_terminal_4 import clean_env  # noqa: F401  (autouse: no capital or Telegram setting leaks in)

EVENING = datetime(2026, 11, 4, 9, 10, tzinfo=timezone.utc)          # Wednesday 18:10 in Seoul, the same US session as TUE_NIGHT
LATER = datetime(2026, 11, 4, 10, 10, tzinfo=timezone.utc)           # 19:10
NEXT_MORNING = datetime(2026, 11, 4, 22, 10, tzinfo=timezone.utc)    # Thursday 07:10
SATURDAY = datetime(2026, 11, 7, 10, 10, tzinfo=timezone.utc)        # Saturday 19:10


def write_run(base, session="2026-11-04", status="REAL RECOMMENDATION", at=EVENING, name="evening"):
    d = base / ms.RUNS / f"20261104T091000Z_kr_market_scan_{name}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "validation_result.json").write_text(json.dumps({"run_id": d.name, "mode": "kr_market_scan", "executed_at": at.isoformat(), "recommendation_status": status,
                                                           "latest_session": session, "validation_scope": "full"}), encoding="utf-8")


def evening(tmp_path, monkeypatch, now=EVENING, rc=0, writes="2026-11-04", status="REAL RECOMMENDATION", capital=True):
    """The morning run has done the day's other steps; this is a later slot of the same day."""
    if not (tmp_path / "data" / "automation" / "state.json").exists():
        make(tmp_path)[0].run()
    if capital:
        monkeypatch.setenv("QPP_CAPITAL_KRW", "10000000")
    d, calls, sent = make(tmp_path, now=now, rc={"SCAN_KR": rc})
    plain = d.runner

    def runner(name, argv):
        if name == "SCAN_KR":
            assert argv == ["--market", "KR", "scan"]
            if writes:
                write_run(tmp_path, writes, status, now)
        if name == "TRACK_KR":
            assert argv == ["--market", "KR", "tracking", "update"]
        return plain(name, argv)
    d.runner = runner
    return d, calls, sent


def test_the_morning_run_never_scans_and_the_first_evening_slot_does_once(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL_KRW", "10000000")
    d, calls, _ = make(tmp_path)                                        # Wednesday 07:xx in Seoul
    res = d.run()
    assert "SCAN_KR" not in calls and "SCAN_KR" not in res["steps"] and d._scan_kr_day() is None
    d2, calls2, sent2 = evening(tmp_path, monkeypatch)
    res2 = d2.run()
    assert calls2 == ["SCAN_KR", "TRACK_KR"] and d2._scan_kr_day() == "2026-11-04"
    assert res2["steps"]["SCAN_KR"]["status"] == automation.OK and res2["steps"]["SCAN_KR"]["detail"] == "REAL RECOMMENDATION" and sent2 == []      # no second daily message
    assert d2.state()["scan_kr"]["day"] == "2026-11-04" and list(automation.STEP_NAMES)[-2:] == ["SCAN_KR", "BACKUP"] and "SCAN_KR" not in automation.KR_STEPS
    d3, calls3, _ = evening(tmp_path, monkeypatch, now=LATER)
    assert d3.run()["status"] == "UP_TO_DATE" and calls3 == []
    d4, calls4, _ = make(tmp_path, now=NEXT_MORNING)                    # the next morning does its own steps, not the scan
    d4.run()
    assert "SCAN_KR" not in calls4 and automation.STEP_TIMEOUTS["SCAN_KR"] == 90 * 60 and automation.SCAN_KR_FROM_HOUR == 18


def test_no_scan_on_a_weekend_evening(tmp_path, monkeypatch):
    d, calls, _ = evening(tmp_path, monkeypatch, now=SATURDAY)
    d.run()
    assert "SCAN_KR" not in calls and d._scan_kr_day() is None


def test_a_scan_that_wrote_no_run_fails_and_is_asked_again_in_the_next_slot(tmp_path, monkeypatch):
    d, calls, sent = evening(tmp_path, monkeypatch, rc=1, writes=None)
    res = d.run()
    assert res["steps"]["SCAN_KR"] == {"status": automation.FAILED, "at": EVENING.isoformat(), "detail": "코드 1"} and "TRACK_KR" not in calls
    assert "❌ 한국 모델 스캔(KR-EXP): 코드 1" in sent[0] and "scan_kr" not in d.state()
    d2, calls2, _ = evening(tmp_path, monkeypatch, now=LATER, rc=1, status="NO VALID RECOMMENDATION")       # exit 1 with a run written is a result
    res2 = d2.run()
    assert calls2[:2] == ["SCAN_KR", "TRACK_KR"] and res2["steps"]["SCAN_KR"]["status"] == automation.OK and res2["steps"]["SCAN_KR"]["detail"] == "NO VALID RECOMMENDATION"


def test_a_session_the_button_already_scanned_is_not_scanned_twice(tmp_path, monkeypatch):
    make(tmp_path)[0].run()
    write_run(tmp_path, "2026-11-04", name="button")
    d, calls, _ = evening(tmp_path, monkeypatch)
    res = d.run()
    assert calls == ["TRACK_KR"] and res["steps"]["SCAN_KR"]["status"] == automation.OK and "화면에서 이미 스캔함" in res["steps"]["SCAN_KR"]["detail"]
    assert ms.scanned_session(tmp_path, "2026-11-04")["run_id"].endswith("_button") and ms.scanned_session(tmp_path, "2026-11-05") is None
    write_run(tmp_path, "2026-11-05", status="NO VALID RECOMMENDATION", name="empty")
    assert ms.scanned_session(tmp_path, "2026-11-05") is None           # a scan that scored nothing has not scanned the session


def test_a_scan_whose_data_is_not_todays_says_so_and_is_not_repeated(tmp_path, monkeypatch):
    d, calls, _ = evening(tmp_path, monkeypatch, writes="2026-11-03")
    step = d.run()["steps"]["SCAN_KR"]
    assert step["status"] == automation.OK and "기준 거래일 2026-11-03(오늘 자료 아님" in step["detail"]
    d2, calls2, _ = evening(tmp_path, monkeypatch, now=LATER, writes="2026-11-03")
    assert d2.run()["status"] == "UP_TO_DATE" and calls2 == []


def test_without_capital_the_evening_scan_is_skipped_for_the_day(tmp_path, monkeypatch):
    d, calls, sent = evening(tmp_path, monkeypatch, capital=False)
    res = d.run()
    assert res["steps"]["SCAN_KR"]["status"] == automation.SKIPPED and "SCAN_KR" not in calls and sent == []
    d2, calls2, _ = evening(tmp_path, monkeypatch, now=LATER, capital=False)
    assert d2.run()["status"] == "UP_TO_DATE"


def test_the_job_waits_for_a_scan_started_from_the_screen_and_the_button_waits_for_the_job(tmp_path, monkeypatch):
    make(tmp_path)[0].run()
    (tmp_path / ms.MARKER).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / ms.MARKER).write_text(json.dumps({"pid": os.getpid(), "started_at": EVENING.isoformat()}), encoding="utf-8")
    d, calls, _ = evening(tmp_path, monkeypatch)
    res = d.run()
    assert res["steps"]["SCAN_KR"]["status"] == automation.WAITING and "SCAN_KR" not in calls and "scan_kr" not in d.state()
    (tmp_path / ms.MARKER).unlink()
    d2, calls2, _ = evening(tmp_path, monkeypatch, now=LATER)
    assert d2.run()["steps"]["SCAN_KR"]["status"] == automation.OK and calls2[:2] == ["SCAN_KR", "TRACK_KR"]      # a waiting step is asked again
    monkeypatch.setattr(automation, "running", lambda base: {"started_at": "2026-11-04T09:10:00+00:00", "step": "SCAN_KR", "done": 0, "total": 2})
    started = []
    got = ms.start(tmp_path, popen=lambda *a, **k: started.append(a))
    assert got == {"status": "ALREADY_RUNNING", "started_at": "2026-11-04T09:10:00+00:00", "by": "DAILY_JOB"} and started == []
    assert ms.status(tmp_path) == {"status": "RUNNING", "started_at": "2026-11-04T09:10:00+00:00", "by": "DAILY_JOB"}
    monkeypatch.setattr(automation, "running", lambda base: {"started_at": "x", "step": "QSF_KR", "done": 4, "total": 10})
    assert ms.status(tmp_path)["status"] != "RUNNING"                   # another step of the job does not block the button


def test_a_failed_outcome_update_does_not_undo_a_scan_that_was_written(tmp_path, monkeypatch):
    d, calls, _ = evening(tmp_path, monkeypatch)
    plain = d.runner
    d.runner = lambda name, argv: 2 if name == "TRACK_KR" else plain(name, argv)
    step = d.run()["steps"]["SCAN_KR"]
    assert step["status"] == automation.OK and step["detail"] == "REAL RECOMMENDATION · 추적 갱신 실패(코드 2)"
