"""The Korean model scan as a step of the daily job (user decision 2026-11-12): the last step of the morning run before the backup,
skipped without capital, never beside a scan started from the screen, not repeated for a session already scanned, and read as done
from the run it wrote.  Morning and not evening: Yahoo has a day's Korean bars for only a part of the stocks until the next morning."""
import json
import os

from terminal import automation, model_scan as ms
from tests.test_terminal_4 import TUE_NIGHT, make
from tests.test_terminal_4 import clean_env  # noqa: F401  (autouse: no capital or Telegram setting leaks in)

SESSION = "2026-11-03"          # TUE_NIGHT is Wednesday morning in Seoul: the session to score is Tuesday's


def write_run(base, session=SESSION, status="REAL RECOMMENDATION", at=TUE_NIGHT, name="test"):
    d = base / ms.RUNS / f"20261104T000000Z_kr_market_scan_{name}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "validation_result.json").write_text(json.dumps({"run_id": d.name, "mode": "kr_market_scan", "executed_at": at.isoformat(), "recommendation_status": status,
                                                           "latest_session": session, "validation_scope": "full"}), encoding="utf-8")


def scanning(tmp_path, monkeypatch, rc=0, writes=SESSION, status="REAL RECOMMENDATION"):
    monkeypatch.setenv("QPP_CAPITAL_KRW", "10000000")
    d, calls, sent = make(tmp_path, rc={"SCAN_KR": rc})
    plain = d.runner

    def runner(name, argv):
        if name == "SCAN_KR":
            assert argv == ["--market", "KR", "scan"]
            if writes:
                write_run(tmp_path, writes, status)
        if name == "TRACK_KR":
            assert argv == ["--market", "KR", "tracking", "update"]
        return plain(name, argv)
    d.runner = runner
    return d, calls, sent


def test_the_scan_runs_after_every_record_and_before_the_backup_then_updates_its_outcomes(tmp_path, monkeypatch):
    d, calls, sent = scanning(tmp_path, monkeypatch)
    res = d.run()
    assert calls[-4:-1] == ["US_CHALLENGER", "SCAN_KR", "TRACK_KR"] and calls.index("KR_FORWARD") < calls.index("SCAN_KR")
    step = res["steps"]["SCAN_KR"]
    assert step["status"] == automation.OK and step["detail"] == "REAL RECOMMENDATION" and "한국 모델 스캔" not in sent[0]       # on track: not in the daily message
    assert list(automation.STEP_NAMES)[-2:] == ["SCAN_KR", "BACKUP"] and "SCAN_KR" in automation.KR_STEPS and automation.STEP_TIMEOUTS["SCAN_KR"] == 90 * 60
    d2, calls2, _ = make(tmp_path)
    assert d2.run()["status"] == "UP_TO_DATE" and calls2 == []                      # done once for the day


def test_no_run_written_is_a_failure_and_is_tried_again_while_no_valid_recommendation_is_a_result(tmp_path, monkeypatch):
    d, calls, sent = scanning(tmp_path, monkeypatch, rc=1, writes=None)
    res = d.run()
    # it failed at once, so the run tried it once more before giving up (2026-11-15)
    assert res["steps"]["SCAN_KR"] == {"status": automation.FAILED, "at": TUE_NIGHT.isoformat(), "detail": "코드 1", "seconds": 0, "retried": True} and "TRACK_KR" not in calls
    assert calls.count("SCAN_KR") == 2
    assert "❌ 한국 모델 스캔(KR-EXP): 코드 1" in sent[0]
    d2, calls2, _ = scanning(tmp_path, monkeypatch, rc=1, status="NO VALID RECOMMENDATION")
    res2 = d2.run()
    assert calls2 == ["SCAN_KR", "TRACK_KR"] and res2["steps"]["SCAN_KR"]["status"] == automation.OK and res2["steps"]["SCAN_KR"]["detail"] == "NO VALID RECOMMENDATION"


def test_a_session_already_scanned_is_not_scanned_twice(tmp_path, monkeypatch):
    write_run(tmp_path, SESSION, name="button")
    d, calls, _ = scanning(tmp_path, monkeypatch)
    res = d.run()
    assert "SCAN_KR" not in calls and "TRACK_KR" in calls and res["steps"]["SCAN_KR"]["status"] == automation.OK and "화면에서 이미 스캔함" in res["steps"]["SCAN_KR"]["detail"]
    assert ms.scanned_session(tmp_path, SESSION)["run_id"].endswith("_button") and ms.scanned_session(tmp_path, "2026-11-04") is None
    write_run(tmp_path, "2026-11-04", status="NO VALID RECOMMENDATION", name="empty")
    assert ms.scanned_session(tmp_path, "2026-11-04") is None           # a scan that scored nothing has not scanned the session


def test_a_scan_whose_data_is_not_the_days_says_so(tmp_path, monkeypatch):
    d, calls, _ = scanning(tmp_path, monkeypatch, writes="2026-11-02")
    step = d.run()["steps"]["SCAN_KR"]
    assert step["status"] == automation.OK and f"기준 거래일 2026-11-02({SESSION} 자료 아님" in step["detail"]


def test_without_capital_the_scan_is_skipped_and_runs_once_capital_is_saved(tmp_path, monkeypatch):
    d, calls, sent = make(tmp_path)
    res = d.run()
    assert res["steps"]["SCAN_KR"]["status"] == automation.SKIPPED and "SCAN_KR" not in calls
    d2, calls2, _ = scanning(tmp_path, monkeypatch)
    assert d2.run()["steps"]["SCAN_KR"]["status"] == automation.OK and calls2 == ["SCAN_KR", "TRACK_KR"]


def test_the_job_waits_for_a_scan_started_from_the_screen_and_the_button_waits_for_the_job(tmp_path, monkeypatch):
    (tmp_path / ms.MARKER).parent.mkdir(parents=True)
    (tmp_path / ms.MARKER).write_text(json.dumps({"pid": os.getpid(), "started_at": TUE_NIGHT.isoformat()}), encoding="utf-8")
    d, calls, sent = scanning(tmp_path, monkeypatch)
    res = d.run()
    assert res["steps"]["SCAN_KR"]["status"] == automation.WAITING and "SCAN_KR" not in calls and "화면에서 시작한 스캔 실행 중" in res["steps"]["SCAN_KR"]["detail"]
    (tmp_path / ms.MARKER).unlink()
    d2, calls2, _ = scanning(tmp_path, monkeypatch)
    assert d2.run()["steps"]["SCAN_KR"]["status"] == automation.OK and calls2[:2] == ["SCAN_KR", "TRACK_KR"]      # a waiting step is asked again
    monkeypatch.setattr(automation, "running", lambda base: {"started_at": "2026-11-04T22:10:00+00:00", "step": "SCAN_KR", "done": 9, "total": 11})
    started = []
    got = ms.start(tmp_path, popen=lambda *a, **k: started.append(a))
    assert got == {"status": "ALREADY_RUNNING", "started_at": "2026-11-04T22:10:00+00:00", "by": "DAILY_JOB"} and started == []
    assert ms.status(tmp_path) == {"status": "RUNNING", "started_at": "2026-11-04T22:10:00+00:00", "by": "DAILY_JOB"}
    monkeypatch.setattr(automation, "running", lambda base: {"started_at": "x", "step": "QSF_KR", "done": 4, "total": 11})
    assert ms.status(tmp_path)["status"] != "RUNNING"                               # another step of the job does not block the button


def test_a_failed_outcome_update_does_not_undo_a_scan_that_was_written(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL_KRW", "10000000")
    d, calls, _ = make(tmp_path, rc={"TRACK_KR": 2})
    plain = d.runner
    d.runner = lambda name, argv: (write_run(tmp_path) if name == "SCAN_KR" else None, plain(name, argv))[1]
    step = d.run()["steps"]["SCAN_KR"]
    assert step["status"] == automation.OK and step["detail"] == "REAL RECOMMENDATION · 추적 갱신 실패(코드 2)"
