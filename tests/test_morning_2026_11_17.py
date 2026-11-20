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
    assert calls.count("NEWS_KR") == 1 and kr["status"] == automation.FAILED and "거절" in kr["detail"] and "내일 다시 시도" in kr["detail"] and kr["no_quick_retry"] is True and "retried" not in kr
    assert calls.count("NEWS") == 2 and us["status"] == automation.OK and us["retried"] is True      # a failure that was not a refusal: one more try, as before
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'if str(res.get("stopped") or "").startswith("REFUSED"):\n            return 6' in app


# ---------------------------------------------------------------------- the news feeds (user decision of the same day)
import json  # noqa: E402

from terminal import news  # noqa: E402


def test_google_news_is_asked_at_its_former_pace_and_yahoo_as_before(tmp_path, monkeypatch):
    for market, rows in (("KR", [{"ticker": "005930", "name": "삼성전자"}, {"ticker": "000660", "name": "SK하이닉스"}, {"ticker": "035420", "name": "NAVER"}]), ("US", [{"ticker": t} for t in "ABC"])):
        folder = tmp_path / "data" / "qsf"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"latest_{market}.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")

    class Reply:
        status_code, content = 200, b"<rss><channel></channel></rss>"

        def raise_for_status(self):
            pass

    class Client:
        def get(self, url, **kw):
            return Reply()

        def close(self):
            pass
    monkeypatch.setattr(news, "_one_connection", Client)
    kr, us = [], []
    assert news.record(tmp_path, "KR", Client(), sleep=kr.append)["ok"] == 3 and news.record(tmp_path, "US", sleep=us.append)["ok"] == 3
    assert kr == [1.5, 1.5] and us == [0.6, 0.6] and news.pause_of("KR") == 1.5 and news.pause_of("US") == news.PAUSE_S
    quick = []
    news.record(tmp_path, "KR", Client(), sleep=quick.append, pause=0.0)         # a caller's own pause is still taken
    assert quick == [0.0, 0.0]


def test_the_users_switch_turns_a_markets_news_record_off(tmp_path, monkeypatch):
    monkeypatch.delenv(news.OFF_ENV, raising=False)
    assert not news.switched_off("KR") and not news.switched_off("US")
    for typed, off in (("KR", {"KR"}), ("kr, us", {"KR", "US"}), ("US;KR", {"KR", "US"}), ("KR  # 2027-03 Google이 막음", {"KR"}), ("", set()), ("yes", set())):
        monkeypatch.setenv(news.OFF_ENV, typed)
        assert {m for m in ("KR", "US") if news.switched_off(m)} == off, typed
    monkeypatch.setenv(news.OFF_ENV, "KR")
    d, calls = job(tmp_path, {})
    res = d.run()
    assert "NEWS_KR" not in calls and "NEWS" in calls
    assert res["steps"]["NEWS_KR"]["status"] == automation.SKIPPED and news.OFF_ENV in res["steps"]["NEWS_KR"]["detail"] and res["steps"]["NEWS"]["status"] == automation.OK
    runbook = (ROOT / "reports" / "RUNBOOK.md").read_text(encoding="utf-8")
    assert runbook.count("QPP_NEWS_OFF") >= 2 and "막히면 끄는 것이 답이다" in runbook


def test_google_is_asked_on_a_connection_of_its_own_and_yahoo_on_a_shared_one(monkeypatch):
    made = []
    monkeypatch.setattr(news, "_one_connection", lambda: made.append(1) or "shared")
    assert news._client(news.requests, "KR") == (news.requests, False) and not made      # as it was while it worked: nothing kept between requests
    assert news._client(news.requests, "US") == ("shared", True) and made == [1]
    stand_in = object()
    assert news._client(stand_in, "US") == (stand_in, False) and news._client(stand_in, "KR") == (stand_in, False)
    assert news.SEPARATE_CONNECTIONS == ("KR",)


def test_a_feed_that_refused_is_left_alone_for_the_rest_of_the_day_and_asked_once_the_next(tmp_path):
    d, calls = job(tmp_path, {"NEWS_KR": [6]}, minutes=1)
    assert d.run()["steps"]["NEWS_KR"]["status"] == automation.FAILED and calls.count("NEWS_KR") == 1
    hour, calls2 = job(tmp_path, {"NEWS_KR": [0]})
    hour.now = lambda: TUE_NIGHT + timedelta(hours=2)                  # the same Korean day, two hourly firings later
    assert hour.run()["status"] == "UP_TO_DATE" and calls2 == []       # nothing else is pending, and the feed is not asked
    assert hour.state()["sessions"]["2026-11-03"]["NEWS_KR"]["status"] == automation.FAILED      # still shown as failed, not hidden
    nxt, calls3 = job(tmp_path, {"NEWS_KR": [0]})
    nxt.now = lambda: TUE_NIGHT + timedelta(hours=16)                  # 2026-11-04 15:00 UTC is the next day in Korea; the US session is the same
    res = nxt.run()
    assert calls3.count("NEWS_KR") == 1 and res["steps"]["NEWS_KR"]["status"] == automation.OK     # with the day's other Korean steps, once
    other, calls4 = job(tmp_path / "b", {"TRACK": [1, 1]}, minutes=1)
    other.run()
    again, calls5 = job(tmp_path / "b", {"TRACK": [0]})
    again.now = lambda: TUE_NIGHT + timedelta(hours=2)
    again.run()
    assert "TRACK" in calls5                                           # an ordinary failure is still asked again every hour
