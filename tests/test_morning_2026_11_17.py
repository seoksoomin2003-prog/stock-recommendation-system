"""What the first morning on the faster run showed (2026-11-17): the Korean forward record reached KRX before it had published and
was written after the open, and a news feed that refused was asked again seconds later.  No network."""
from datetime import timedelta
from pathlib import Path

from terminal import automation
from terminal.automation import Daily
from tests.test_terminal_1 import _loopback_only  # noqa: F401  (autouse: these tests may reach 127.0.0.1 only)
from tests.test_terminal_4 import TUE_NIGHT, FakeTerminal, clean_env, ledger  # noqa: F401  (clean_env is an autouse fixture)

ROOT = Path(__file__).resolve().parents[1]


def job(tmp_path, codes, minutes=5):
    """A daily job on a clock that moves ``minutes`` with every step.  ``codes``: step -> the exit codes of its tries, in order."""
    clock, calls, left = {"now": TUE_NIGHT}, [], {k: list(v) for k, v in codes.items()}

    def runner(name, argv):
        calls.append(name)
        clock["now"] += timedelta(minutes=minutes)
        code = left[name].pop(0) if left.get(name) else 0
        if name == "LAB" and code == 0:
            ledger(tmp_path, d.now().date().isoformat())
        return code
    d = Daily(tmp_path, now=lambda: clock["now"], runner=runner, telegram=lambda text: {"status": "SENT"}, macos=lambda t, b: {"status": "SENT"},
              terminal=FakeTerminal(), backup_dir=tmp_path / "bk")
    return d, calls


def test_a_korean_record_that_waited_for_krx_is_asked_once_more_before_the_backup(tmp_path):
    d, calls = job(tmp_path, {"KR_FORWARD": [3, 0]})
    res = d.run()
    step = res["steps"]["KR_FORWARD"]
    assert calls.count("KR_FORWARD") == 2 and step["status"] == automation.OK and step["retried"] is True
    second = len(calls) - 1 - calls[::-1].index("KR_FORWARD")
    assert calls.index("KR_FORWARD") < calls.index("US_CHALLENGER") < second                               # after the rest of the chain
    assert res["steps"]["BACKUP"]["status"] == automation.OK and res["steps"]["BACKUP"]["at"] >= step["at"]  # and what it wrote is in today's backup


def test_a_day_krx_has_not_published_by_then_keeps_waiting_and_is_not_asked_a_third_time(tmp_path):
    d, calls = job(tmp_path, {"KR_FORWARD": [3, 3, 0]})
    res = d.run()
    assert calls.count("KR_FORWARD") == 2 and res["steps"]["KR_FORWARD"]["status"] == automation.WAITING and res["steps"]["KR_FORWARD"]["retried"] is True
    again, calls2 = job(tmp_path, {"KR_FORWARD": [0]})                                                    # the next hourly run asks as before
    again.now = lambda: TUE_NIGHT + timedelta(hours=2)
    assert again.run()["steps"]["KR_FORWARD"]["status"] == automation.OK and calls2.count("KR_FORWARD") == 1


def test_a_run_that_came_only_for_the_waiting_step_does_not_ask_twice_in_a_row(tmp_path):
    d, calls = job(tmp_path, {"KR_FORWARD": [3, 3]}, minutes=1)        # eleven steps, a minute each: the first try is not ten minutes old
    d.run()
    first = calls.count("KR_FORWARD")
    d2, calls2 = job(tmp_path, {"KR_FORWARD": [3, 3]}, minutes=1)
    d2.now = lambda: TUE_NIGHT + timedelta(hours=1)                    # a fixed clock, as when the step itself takes seconds
    d2.run()
    assert first == 1 and calls2 == ["KR_FORWARD"]
    assert automation.WAIT_RETRY_S == 600


def test_a_feed_that_refused_is_not_asked_again_in_the_same_run_and_a_quick_failure_still_is(tmp_path):
    d, calls = job(tmp_path, {"NEWS_KR": [6, 0], "NEWS": [1, 0]}, minutes=1)
    res = d.run()
    kr, us = res["steps"]["NEWS_KR"], res["steps"]["NEWS"]
    assert calls.count("NEWS_KR") == 1 and kr["status"] == automation.FAILED and "거절" in kr["detail"] and kr["no_quick_retry"] is True and "retried" not in kr
    assert calls.count("NEWS") == 2 and us["status"] == automation.OK and us["retried"] is True      # a failure that was not a refusal: one more try, as before
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'if str(res.get("stopped") or "").startswith("REFUSED"):\n            return 6' in app
