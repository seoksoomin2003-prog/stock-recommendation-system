"""TERMINAL-4 offline tests: daily job idempotence and retries, alert de-duplication, backup, secret safety."""
import gzip
import json
import plistlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from terminal import automation, notify
from terminal.automation import Daily

TUE_NIGHT = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)      # after the Tuesday 2026-11-03 session
WED_NIGHT = datetime(2026, 11, 4, 23, 0, tzinfo=timezone.utc)
SAT = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)
TOKEN = "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class FakeTerminal:
    def __init__(self, alerts=None, holdings=None, integrity="OK"):
        self.alerts, self.holdings, self.integrity = alerts or [], holdings or [], integrity

    def portfolio(self, market="US"):
        if market == "KR":
            return {"integrity": {"status": "OK"}, "alerts": [], "holdings": []}
        return {"integrity": {"status": self.integrity}, "alerts": self.alerts, "holdings": self.holdings}


def ledger(tmp_path, *sessions):
    from terminal.lab.service import GENESIS, _hash
    (tmp_path / "data" / "lab").mkdir(parents=True, exist_ok=True)
    prev, lines = GENESIS, []
    for k, s in enumerate(sessions, 1):
        r = {"type": "SIGNAL", "model": "BASE_SPY", "signal_session": s, "seq": k, "prev_hash": prev}
        r["hash"] = _hash(r)
        prev = r["hash"]
        lines.append(json.dumps(r, sort_keys=True))
    (tmp_path / "data" / "lab" / "ledger.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def make(tmp_path, now=TUE_NIGHT, rc=None, terminal=None, tg="SENT", record=True):
    calls, sent = [], []

    def runner(name, argv):
        calls.append(name)
        code = (rc or {}).get(name, 0)
        if name == "LAB" and code == 0 and record:
            ledger(tmp_path, d.now().date().isoformat())
        return code

    def telegram(text):
        sent.append(text)
        return {"status": tg}
    d = Daily(tmp_path, now=lambda: now, runner=runner, telegram=telegram, macos=lambda t, b: {"status": "SENT"},
              terminal=terminal or FakeTerminal(), backup_dir=tmp_path / "bk")
    return d, calls, sent


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("QPP_CAPITAL", "QPP_CAPITAL_KRW", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "QPP_BACKUP_DIR"):
        monkeypatch.delenv(k, raising=False)


def test_runs_each_step_once_per_session(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL", "1000")
    d, calls, sent = make(tmp_path)
    assert d.run()["status"] == "DONE"
    assert calls == ["LAB", "SCAN", "TRACK", "QSF", "QSF_KR", "NEWS", "NEWS_KR", "KR_FORWARD", "US_CHALLENGER", "KR_HOLDINGS"] and len(sent) == 1
    assert d.run()["status"] == "UP_TO_DATE"              # the next firing the same day does nothing
    assert calls == ["LAB", "SCAN", "TRACK", "QSF", "QSF_KR", "NEWS", "NEWS_KR", "KR_FORWARD", "US_CHALLENGER", "KR_HOLDINGS"] and len(sent) == 1


def test_failed_step_retries_alone_and_others_still_run(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL", "1000")
    d, calls, sent = make(tmp_path, rc={"SCAN": 2})
    d.run()
    # the scan failed at once, so it gets one more try after the chain (2026-11-15); the others are not run again
    assert calls == ["LAB", "SCAN", "TRACK", "QSF", "QSF_KR", "NEWS", "NEWS_KR", "KR_FORWARD", "US_CHALLENGER", "SCAN", "KR_HOLDINGS"] and "❌ P6-11B 스캔" in sent[0]
    d2, calls2, sent2 = make(tmp_path)
    d2.run()
    assert calls2 == ["SCAN"] and "✅ P6-11B 스캔" in sent2[0]


def test_a_korean_day_not_published_yet_waits_quietly_and_retries(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL", "1000")
    d, calls, sent = make(tmp_path, rc={"KR_FORWARD": 3})
    res = d.run()
    assert res["steps"]["KR_FORWARD"]["status"] == automation.WAITING and "한국 결합 점수" not in sent[0] and len(sent) == 1
    d2, calls2, sent2 = make(tmp_path)
    assert d2.run()["steps"]["KR_FORWARD"]["status"] == automation.OK
    assert calls2 == ["KR_FORWARD"] and sent2 == []               # the same message is not sent twice
    assert d2.run()["status"] == "UP_TO_DATE"


def test_the_us_challenger_waits_quietly_and_a_failure_is_told(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL", "1000")
    d, _, sent = make(tmp_path, rc={"US_CHALLENGER": 3})
    res = d.run()
    assert res["steps"]["US_CHALLENGER"]["status"] == automation.WAITING and "미국 도전자" not in sent[0]
    d2, calls2, _ = make(tmp_path)
    assert d2.run()["steps"]["US_CHALLENGER"]["status"] == automation.OK and calls2 == ["US_CHALLENGER"]
    (tmp_path / "other").mkdir()
    d3, _, sent3 = make(tmp_path / "other", rc={"US_CHALLENGER": 1})
    d3.run()
    assert "❌ 미국 도전자 점수 기록" in sent3[0]


def test_a_failed_korean_record_is_told_and_a_missing_key_is_named(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL", "1000")
    d, _, sent = make(tmp_path, rc={"KR_FORWARD": 4})
    d.run()
    assert "❌ 한국 결합 점수 기록: KRX 키 없음" in sent[0]


def test_lab_exit_zero_without_todays_record_is_a_failure(tmp_path):
    d, _, sent = make(tmp_path, record=False)
    res = d.run()
    assert res["steps"]["LAB"]["status"] == "FAILED" and "❌ 도전자 기록" in sent[0]


def test_unchanged_failure_is_not_resent(tmp_path):
    d, calls, sent = make(tmp_path, rc={"TRACK": 1})
    d.run()
    d.run()
    assert calls.count("TRACK") == 4 and len(sent) == 1           # two runs, each with its one extra try; the notice goes out once


def test_scan_skipped_without_capital_then_runs_when_configured(tmp_path, monkeypatch):
    d, calls, sent = make(tmp_path)
    res = d.run()
    assert "SCAN" not in calls and res["steps"]["SCAN"]["status"] == "SKIPPED"
    assert "QPP_CAPITAL" in sent[0]
    monkeypatch.setenv("QPP_CAPITAL", "1000")
    d2, calls2, _ = make(tmp_path)
    d2.run()
    assert calls2 == ["SCAN"]


def test_weekend_does_nothing_new(tmp_path):
    d, _, _ = make(tmp_path, now=datetime(2026, 11, 6, 23, 0, tzinfo=timezone.utc))
    d.run()
    d2, calls, sent = make(tmp_path, now=SAT)
    assert d2.run()["status"] == "UP_TO_DATE" and not calls and not sent


def test_alert_is_new_once_then_continuing(tmp_path):
    a = {"level": "bad", "code": "STOP_HIT", "ticker": "AAPL", "text": "AAPL: 손절가 이하"}
    d, _, sent = make(tmp_path, terminal=FakeTerminal([a]))
    d.run()
    assert "🚨 AAPL" in sent[0]
    ledger(tmp_path, "2026-11-03")
    d2, _, sent2 = make(tmp_path, now=WED_NIGHT, terminal=FakeTerminal([a]))
    d2.run()
    assert "🚨 AAPL" not in sent2[0] and "계속되는 경고" in sent2[0]


def test_alert_stays_new_until_delivered(tmp_path):
    a = {"level": "bad", "code": "STOP_HIT", "ticker": "AAPL", "text": "AAPL: 손절가 이하"}
    d, _, _ = make(tmp_path, terminal=FakeTerminal([a]), tg="FAILED")
    d.run()
    d2, _, sent2 = make(tmp_path, terminal=FakeTerminal([a]))
    d2.run()
    assert "🚨 AAPL" in sent2[0]


def test_integrity_and_stale_are_never_hidden(tmp_path):
    d, _, sent = make(tmp_path, terminal=FakeTerminal(integrity="BROKEN"))
    d.run()
    assert "무결성 오류" in sent[0]
    t = FakeTerminal(holdings=[{"ticker": "MSFT", "status": "STALE", "date": "2026-10-20"}])
    d2, _, sent2 = make(tmp_path / "x", terminal=t)
    (tmp_path / "x").mkdir(exist_ok=True)
    d2.run()
    assert "MSFT (2026-10-20)" in sent2[0]


def test_missing_sessions_are_reported(tmp_path):
    ledger(tmp_path, "2026-11-02", "2026-11-04")
    d = Daily(tmp_path, now=lambda: WED_NIGHT)
    assert d.missing_sessions("2026-11-04") == ["2026-11-03"]
    text = Daily.compose("2026-11-04", {}, {"status": "OK", "items": []}, [], ["2026-11-03"])
    assert "빠진 거래일 1일" in text and "소급" in text


def test_second_process_does_not_run_concurrently(tmp_path):
    d, calls, _ = make(tmp_path)
    other, _, _ = make(tmp_path)
    with other._exclusive() as got:
        assert got
        assert d.run()["status"] == "ALREADY_RUNNING"
    assert not calls


def test_backup_copies_records_outside_project_and_prunes_only_dates(tmp_path):
    base, root = tmp_path / "p", tmp_path / "bk"
    (base / "data" / "terminal" / "cache").mkdir(parents=True)
    (base / "data" / "terminal" / "journal.jsonl").write_text("x\n")
    (base / "data" / "terminal" / "cache" / "big.json").write_text("cache")
    (base / "tracking" / "ledger").mkdir(parents=True)
    (base / "tracking" / "ledger" / "observations.jsonl").write_text("y\n")
    (root / "내 문서").mkdir(parents=True)
    for k in range(1, automation.KEEP_BACKUPS + 3):
        (root / f"2020-01-{k:02d}" if k < 29 else root / f"2020-02-{k - 28:02d}").mkdir(parents=True)
    res = automation.backup(base, "2026-11-03", root)
    day = root / "2026-11-03"
    assert res["files"] == 2 and (day / "data" / "terminal" / "journal.jsonl").read_text() == "x\n"
    assert not (day / "data" / "terminal" / "cache").exists()
    assert (root / "내 문서").exists() and not (root / ".2026-11-03.partial").exists()
    assert len([p for p in root.iterdir() if automation._is_date_name(p.name)]) <= automation.KEEP_BACKUPS


def test_telegram_not_configured_and_invalid(monkeypatch):
    assert notify.send_telegram("x")["status"] == "NOT_CONFIGURED"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bad")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    assert notify.send_telegram("x")["status"] == "INVALID"


def test_telegram_errors_never_contain_the_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    def boom(method, url, **kw):
        raise RuntimeError(f"connection failed for {url}")
    res = notify.send_telegram("x", http=boom)
    assert res == {"status": "FAILED", "error": "RuntimeError"} and TOKEN not in json.dumps(res)
    res = notify.send_telegram("x", http=lambda m, u, **k: SimpleNamespace(status_code=401))
    assert res == {"status": "FAILED", "error": "HTTP 401"}
    assert TOKEN not in json.dumps(notify.find_chats(http=boom))


def test_long_message_is_split_without_losing_lines():
    text = "\n".join(f"line {k}" for k in range(3000))
    parts = notify.split_text(text)
    assert len(parts) > 1 and all(len(p) <= notify.MAX_LEN for p in parts)
    assert "\n".join(parts) == text
    assert all(len(p) <= 50 for p in notify.split_text("x" * 120, 50))


def test_find_chats_lists_ids(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    body = {"result": [{"message": {"chat": {"id": 777, "type": "private", "first_name": "A"}}}, {"edited": {}}]}
    res = notify.find_chats(http=lambda m, u, **k: SimpleNamespace(status_code=200, json=lambda: body))
    assert res["chats"] == [{"id": 777, "type": "private", "name": "A"}]


def test_macos_text_goes_through_argv():
    seen = {}

    def run(argv, **kw):
        seen["argv"] = argv
        return SimpleNamespace(returncode=0)
    evil = '" & do shell script "rm -rf ~'
    assert notify.send_macos("t", evil, run=run, platform="darwin")["status"] == "SENT"
    assert seen["argv"][-1] == evil and not any(evil in a for a in seen["argv"][:-1])
    assert notify.send_macos("t", "b", platform="linux")["status"] == "NOT_AVAILABLE"


def test_plist_schedules_and_holds_no_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    raw = automation.plist_bytes(tmp_path / "with space")
    pl = plistlib.loads(raw)
    slots = pl["StartCalendarInterval"]
    assert pl["RunAtLoad"] is True and slots[0] == {"Hour": 7, "Minute": 10} and slots[-1] == {"Hour": 23, "Minute": 10} and len(slots) == 17      # hourly, never before the US session is complete
    assert "caffeinate -i" in pl["ProgramArguments"][2] or not automation.Path(automation.CAFFEINATE).exists()
    assert "'" in pl["ProgramArguments"][2] and "automation run" in pl["ProgramArguments"][2]
    assert TOKEN.encode() not in raw and "EnvironmentVariables" not in pl


def test_status_reports_words_only(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setattr(automation, "is_installed", lambda: False)
    st = automation.status(tmp_path)
    assert st["telegram"] == "CONFIGURED" and TOKEN not in json.dumps(st) and "12345" not in json.dumps(st)


def test_korean_steps_run_on_a_day_only_the_us_is_closed(tmp_path):
    d, calls, _ = make(tmp_path, now=datetime(2026, 11, 25, 23, 0, tzinfo=timezone.utc))     # Thursday morning in Seoul, after the US Wednesday
    d.run()
    assert {"QSF", "QSF_KR", "KR_FORWARD"} <= set(calls)
    first_backup = d.state()["sessions"]["2026-11-25"]["BACKUP"]["at"]
    d2, calls2, _ = make(tmp_path, now=datetime(2026, 11, 26, 23, 0, tzinfo=timezone.utc))   # Friday morning: Thanksgiving gave no US session, Korea traded Thursday
    res = d2.run()
    assert res["status"] == "DONE" and calls2 == ["QSF_KR", "NEWS_KR", "KR_FORWARD"]
    assert d2.state()["sessions"]["2026-11-25"]["BACKUP"]["at"] > first_backup
    d3, calls3, _ = make(tmp_path, now=datetime(2026, 11, 26, 23, 30, tzinfo=timezone.utc))  # the next slot that morning
    assert d3.run()["status"] == "UP_TO_DATE" and not calls3


def test_a_retried_step_is_followed_by_a_backup(tmp_path):
    d, calls, _ = make(tmp_path)
    d.run()
    st = d.state()
    session = sorted(st["sessions"])[-1]
    st["sessions"][session]["KR_FORWARD"] = {"status": "WAITING"}
    d._save(st)
    later = TUE_NIGHT + timedelta(minutes=1)
    d2, calls2, _ = make(tmp_path, now=later)
    d2.run()
    assert calls2 == ["KR_FORWARD"] and d2.state()["sessions"][session]["BACKUP"]["at"] == later.isoformat()


def test_backup_holds_every_record_and_a_restored_copy_verifies(tmp_path):
    from terminal.qsf import kr_forward as kf
    base, root = tmp_path / "p", tmp_path / "bk"
    day = datetime(2026, 11, 7, tzinfo=timezone.utc)
    for name in automation.FORWARD_STORES:
        folder = base / "research_data" / name
        folder.mkdir(parents=True)
        with gzip.open(folder / "2026-11-06.json.gz", "wt", encoding="utf-8") as fh:
            json.dump({"session": "2026-11-06", "rows": []}, fh)
        kf._append_index(folder, "2026-11-06", day.isoformat(), False, True, 0)
    (base / "tracking" / "kr" / "ledger").mkdir(parents=True)
    (base / "tracking" / "kr" / "ledger" / "observations.jsonl").write_text("")
    automation.backup(base, "2026-11-06", root)
    assert (root / "2026-11-06" / "tracking" / "kr" / "ledger" / "observations.jsonl").exists()
    for name in automation.FORWARD_STORES:
        assert (root / name / "2026-11-06.json.gz").exists() and (root / "2026-11-06" / "research_data" / name / "index.jsonl").exists()
    got = automation.check_backup(root)
    assert got["status"] == "OK" and got["latest"] == "2026-11-06" and got["checks"]["us_challenger"]["sessions"] == 1
    with gzip.open(root / "krx_forward" / "2026-11-06.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"edited": True}, fh)
    broken = automation.check_backup(root)
    assert broken["status"] == "BROKEN" and broken["checks"]["krx_forward"]["bad"] == ["2026-11-06"]


def test_backup_age_and_no_backup(tmp_path):
    from datetime import date
    assert automation.backup_status(tmp_path / "none") == {"latest": None, "age_days": None, "copies": 0}
    assert automation.check_backup(tmp_path / "none")["status"] == "NO_BACKUP"
    (tmp_path / "2026-11-01").mkdir()
    (tmp_path / "notes").mkdir()
    got = automation.backup_status(tmp_path, date(2026, 11, 8))
    assert got == {"latest": "2026-11-01", "age_days": 7, "copies": 1}


def test_kodex_holdings_tried_weekly_only_while_missing_or_old(tmp_path, monkeypatch):
    from terminal import kr_etf_holdings as kh
    monkeypatch.delenv("QPP_CAPITAL", raising=False)
    d, calls, _ = make(tmp_path, rc={"KR_HOLDINGS": 2})            # the site refused
    st = {"sessions": {}}
    assert d._kr_holdings(st)["result"] == "NOT_SAVED" and calls == ["KR_HOLDINGS"]
    assert d._kr_holdings(st) is None and calls == ["KR_HOLDINGS"]                 # not again within a week
    st["kr_holdings"]["day"] = "2026-10-01"
    assert d._kr_holdings(st)["result"] == "NOT_SAVED" and calls.count("KR_HOLDINGS") == 2
    monkeypatch.setattr(kh, "status", lambda base, today=None: {"status": "OK", "age_days": 10})
    st.pop("kr_holdings")
    assert d._kr_holdings(st) is None and calls.count("KR_HOLDINGS") == 2          # a recent snapshot needs nothing


def test_cache_cleanup_once_per_session_keeps_newest_five_and_records(tmp_path):
    from terminal import storage
    d, _, _ = make(tmp_path)
    root = tmp_path / storage.CACHE
    root.mkdir(parents=True, exist_ok=True)
    days = [f"2026-10-{n:02d}" for n in range(20, 27)]
    for day in days:
        (root / f"scanbars_{day}_{0:016x}_{1:010x}.json").write_bytes(b"x" * 2048)
    (root / "annual_0000320193_ab12cd34ef.json").write_text("{}")
    (root / "annual3_0000320193_ab12cd34ef.json").write_text("{}")
    ledger = tmp_path / "data" / "qsf" / "ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    (ledger / "scanbars_2026-10-20_0_1.json").write_text("{}")        # same name pattern outside the cache stays
    st = {"sessions": {}}
    got = d._cache_prune(st, "2026-10-26")
    left = sorted(p.name for p in root.iterdir())
    assert got["removed"] == 3 and "error" not in got
    assert [n for n in left if n.startswith("scanbars_")] == [f"scanbars_{x}_{0:016x}_{1:010x}.json" for x in days[2:]]
    assert "annual3_0000320193_ab12cd34ef.json" in left and (ledger / "scanbars_2026-10-20_0_1.json").exists()
    assert d._cache_prune(st, "2026-10-26") is None                     # once per session
    assert d._cache_prune(st, "2026-10-27")["removed"] == 0


def test_daily_run_records_cache_cleanup(tmp_path):
    d, _, _ = make(tmp_path)
    d.run()
    assert d.state()["cache_prune"]["removed"] == 0


def test_price_audit_runs_in_the_daily_job_and_never_stops_it(tmp_path, monkeypatch):
    from terminal.qsf import price_audit
    d, _, _ = make(tmp_path)
    d.run()
    got = d.state()["price_audit"]
    assert got["US"]["status"] == "UNAVAILABLE" and got["KR"]["status"] == "UNAVAILABLE"      # no scan bars in a fresh folder
    monkeypatch.setattr(price_audit, "run", lambda *a, **k: 1 / 0)
    st = {"sessions": {}}
    assert d._price_audit(st)["error"] == "ZeroDivisionError"


def test_a_cut_download_and_a_sleeping_mac_are_named(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL", "1000")
    d, _, _ = make(tmp_path, rc={"QSF": 4, "QSF_KR": 3})
    ticks = {"wall": 0.0, "mono": 0.0}

    def wall():
        ticks["wall"] += 700.0
        return ticks["wall"]

    def mono():
        ticks["mono"] += 100.0
        return ticks["mono"]
    d.clocks = (wall, mono)                                    # each step: 600 s more on the wall clock than awake
    steps = d.run()["steps"]
    assert steps["QSF"]["status"] == automation.FAILED and steps["QSF"]["detail"] == "다운로드 끊김 · 실행 중 맥이 약 10분 잠듦"
    assert steps["QSF_KR"]["detail"] == "데이터 미준비 · 실행 중 맥이 약 10분 잠듦" and steps["QSF"]["slept_minutes"] == 10
    assert steps["TRACK"]["status"] == automation.OK and steps["TRACK"]["detail"] is None and steps["TRACK"]["slept_minutes"] == 10
    (tmp_path / "awake").mkdir()
    d2, _, _ = make(tmp_path / "awake", rc={"QSF": 3})
    got = d2.run()["steps"]["QSF"]
    assert got["detail"] == "데이터 미준비" and "slept_minutes" not in got


def test_a_run_leaves_its_marker_only_while_it_runs_and_its_outcome_after(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL", "1000")
    monkeypatch.setattr(automation, "is_installed", lambda: False)
    seen = []
    d, calls, _ = make(tmp_path)
    plain = d.runner

    def runner(name, argv):
        seen.append(automation.status(tmp_path)["running"])
        return plain(name, argv)
    d.runner = runner
    assert automation.status(tmp_path)["running"] is None
    assert d.run()["status"] == "DONE"
    assert seen[0]["step"] == "LAB" and seen[0]["done"] == 0 and seen[0]["total"] == 11           # nine processes, the Korean model scan (skipped without capital) and the backup
    assert seen[-1]["step"] == "WRAP_UP" and seen[-1]["done"] == 11                                # the weekly holdings fetch runs after the steps
    assert [s["step"] for s in seen[:3]] == ["LAB", "SCAN", "TRACK"] and seen[2]["done"] == 2
    st = automation.status(tmp_path)
    assert st["running"] is None and st["last_attempt"]["status"] == "DONE" and st["last_attempt"]["session"] == "2026-11-03"
    assert st["step_names"]["QSF"] == "QSF 점수 기록(미국)" and not (tmp_path / "data" / "automation" / automation.RUNNING_FILE).exists()
    assert d.run()["status"] == "UP_TO_DATE" and automation.status(tmp_path)["last_attempt"]["status"] == "UP_TO_DATE"


def test_a_marker_left_by_a_dead_process_does_not_count(tmp_path):
    folder = tmp_path / "data" / "automation"
    folder.mkdir(parents=True)
    (folder / automation.RUNNING_FILE).write_text(json.dumps({"pid": 2 ** 22 + 12345, "started_at": "x", "step": "QSF", "done": 1, "total": 3}))
    assert automation.running(tmp_path) is None
    (folder / automation.RUNNING_FILE).write_text("not json")
    assert automation.running(tmp_path) is None


def test_a_failed_run_still_clears_its_marker_and_says_so(tmp_path, monkeypatch):
    d, _, _ = make(tmp_path)
    monkeypatch.setattr(d, "_run", lambda resend: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        d.run()
    assert automation.running(tmp_path) is None and d.state()["last_attempt"]["status"] == "ERROR" and d.state()["last_attempt"]["type"] == "RuntimeError"


def test_start_now_spawns_the_same_job_detached_and_never_twice(tmp_path, monkeypatch):
    import os
    spawned = []

    def popen(cmd, **kw):
        spawned.append((cmd, kw))
    monkeypatch.setattr(automation, "CAFFEINATE", str(tmp_path / "no-such-tool"))
    res = automation.start_now(tmp_path, popen=popen, now=lambda: TUE_NIGHT)
    cmd, kw = spawned[0]
    assert res == {"status": "STARTED", "at": TUE_NIGHT.isoformat()} and cmd[1:] == [str(tmp_path / "app.py"), "automation", "run"]
    assert kw["start_new_session"] is True and kw["cwd"] == tmp_path and (tmp_path / "data" / "automation" / "manual_run.log").exists()
    tool = tmp_path / "caffeinate"
    tool.write_text("")
    monkeypatch.setattr(automation, "CAFFEINATE", str(tool))
    automation.start_now(tmp_path, popen=popen)
    assert spawned[1][0][:2] == [str(tool), "-i"] and spawned[1][0][-2:] == ["automation", "run"]          # held awake against idle sleep
    marker = tmp_path / "data" / "automation" / automation.RUNNING_FILE
    marker.write_text(json.dumps({"pid": os.getpid(), "started_at": "2026-11-03T23:00:00+00:00", "step": "QSF", "done": 3, "total": 9}))
    again = automation.start_now(tmp_path, popen=popen)
    assert again["status"] == "ALREADY_RUNNING" and again["running"]["step"] == "QSF" and len(spawned) == 2
