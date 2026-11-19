"""Every one-time reading is made by the daily job itself (terminal/qsf/readings.py).  All offline."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from terminal.automation import Daily
from terminal.qsf import kr_avoid_marks, kr_cap_universe, kr_events_forward, kr_forward, kr_method, kr_swing_challenger, kr_swing_prior, kr_traded_universe, live_forward
from terminal.qsf import readings as rd, regime_weights, score_split, us_challenger

ROOT = Path(__file__).resolve().parents[1]
BY = {e["key"]: e for e in rd.REGISTRY}
DAY = datetime(2027, 11, 20, 0, 0, tzinfo=timezone.utc)


def job(tmp_path, now=DAY, tg="SENT", writes=None):
    """A daily job whose runner stands in for ``python app.py ...``: it notes the call and writes a report when ``writes`` names one."""
    calls, sent, shown = [], [], []

    def runner(name, argv):
        calls.append((name, list(argv)))
        for e in rd.REGISTRY:
            if e["argv"] == list(argv) and writes and e["key"] in writes:
                p = rd.report_path(tmp_path, e)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(writes[e["key"]]), encoding="utf-8")
                return 0
        return 1

    def telegram(text):
        sent.append(text)
        return {"status": tg}

    def macos(title, body):
        shown.append((title, body))
        return {"status": "SENT"}
    return Daily(tmp_path, now=lambda: now, runner=runner, telegram=telegram, macos=macos, backup_dir=tmp_path / "bk"), calls, sent, shown


def fill(tmp_path, store, n):
    folder = tmp_path / rd.STORES / store
    folder.mkdir(parents=True, exist_ok=True)
    start = date(2026, 11, 2)
    (folder / "index.jsonl").write_text("".join(json.dumps({"session": (start + timedelta(days=k)).isoformat()}) + "\n" for k in range(n)), encoding="utf-8")


# ---------------------------------------------------------------------- the list itself
def test_the_list_names_real_commands_reports_stores_and_protocols():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert len(rd.REGISTRY) == 22 and len(BY) == 22 and len({e["report"] for e in rd.REGISTRY}) == 22
    for e in rd.REGISTRY:
        assert f'"{e["argv"][-1]}"' in app and e["argv"][-2] == "qsf" and (ROOT / e["protocol"]).exists(), e["key"]
        assert e["argv"][:2] == ["--market", e["key"][-2:].upper()] or len(e["argv"]) == 2, e["key"]
    name = lambda p: Path(p).name                                   # noqa: E731
    folder = lambda p: Path(p).name                                 # noqa: E731
    assert BY["kr_forward"]["report"] == name(kr_forward.REPORT) and BY["kr_forward"]["store"] == folder(kr_forward.FOLDER)
    assert BY["kr_forward_fund"]["report"] == name(kr_forward.FUND_REPORT) and BY["kr_forward_fund"]["store"] == folder(kr_forward.FUND_FOLDER)
    assert BY["kr_forward_events"]["report"] == name(kr_events_forward.REPORT) and BY["kr_forward_events"]["store"] == folder(kr_events_forward.FOLDER)
    assert BY["kr_cap_universe"]["report"] == name(kr_cap_universe.REPORT) and BY["kr_cap_universe"]["store"] == folder(kr_cap_universe.FOLDER) and BY["kr_cap_universe"]["need"] == kr_cap_universe.NEED
    assert BY["kr_traded_universe"]["report"] == name(kr_traded_universe.REPORT) and BY["kr_traded_universe"]["store"] == folder(kr_traded_universe.FOLDER)
    assert BY["kr_swing_challenger"]["report"] == name(kr_swing_challenger.REPORT) and BY["kr_swing_challenger"]["store"] == folder(kr_swing_challenger.FOLDER)
    assert BY["kr_swing_prior"]["report"] == name(kr_swing_prior.REPORT) and BY["kr_swing_prior"]["store"] == folder(kr_swing_prior.FOLDER)
    assert BY["kr_avoid_marks"]["report"] == name(kr_avoid_marks.REPORT) and BY["kr_avoid_marks"]["need"] == kr_avoid_marks.NEED
    for n in kr_method.READ_AT:
        assert BY[f"kr_method_{n}"]["report"] == name(kr_method.forward_report(ROOT, n)) and BY[f"kr_method_{n}"]["need"] == n and BY[f"kr_method_{n}"]["horizon"] == kr_method.HOLD
    assert BY["kr_method_120"]["store"] == folder(kr_method.FOLDER)
    for m in ("KR", "US"):
        assert BY[f"score_split_{m.lower()}"]["report"] == name(score_split.REPORTS[m]) and BY[f"score_split_{m.lower()}"]["store"] == folder(score_split.FOLDERS[m])
        assert BY[f"regime_weights_{m.lower()}"]["report"] == name(regime_weights.FORWARD_REPORTS[m]) and BY[f"regime_weights_{m.lower()}"]["store"] == folder(regime_weights.FOLDERS[m])
        for key, strategy in (("live_swing", "SWING"), ("live_long", "LONG_TERM")):
            e = BY[f"{key}_{m.lower()}"]
            assert e["report"] == name(live_forward.report_path(ROOT, m, strategy)) and e["need"] == live_forward.NEED[strategy] and e["horizon"] == live_forward.PRIMARY[strategy] and e["ledger"] == m
    assert BY["score_split_kr"]["need"] == score_split.READ_AT and BY["regime_weights_us"]["need"] == regime_weights.READ_AT and rd.LEDGER_FIRST == live_forward.FIRST
    for key, strategy in (("us_challenger_swing", "SWING"), ("us_challenger_long", "LONG_TERM")):
        assert BY[key]["report"] == name(us_challenger.REPORTS[strategy]) and BY[key]["store"] == folder(us_challenger.FOLDER) and BY[key]["horizon"] == us_challenger.HORIZONS[strategy]
        assert BY[key]["need"] == 12 * us_challenger.HORIZONS[strategy]


def test_a_record_is_long_enough_at_need_plus_horizon(tmp_path):
    e = BY["kr_cap_universe"]
    assert rd.records(tmp_path, e) == 0 and not rd.due(tmp_path, e) and rd.wanted(e) == 260
    fill(tmp_path, e["store"], 259)
    assert rd.records(tmp_path, e) == 259 and not rd.due(tmp_path, e)
    fill(tmp_path, e["store"], 260)
    assert rd.due(tmp_path, e) and rd.wanted(BY["kr_method_120"]) == 130 and rd.wanted(BY["live_long_us"]) == 819


def test_the_verdict_is_found_where_each_report_keeps_it_and_put_in_plain_words():
    assert rd.verdict(BY["live_swing_kr"], {"verdict": "RANK_ONLY"}) == "RANK_ONLY" and "순위 근거만" in rd.meaning("RANK_ONLY")
    assert rd.verdict(BY["kr_cap_universe"], {"universe": {"reading": "UNIVERSE_BETTER"}, "swing": {"verdict": "NO_EVIDENCE"}}) == "UNIVERSE_BETTER"
    assert rd.verdict(BY["us_challenger_swing"], {"supports_challenger": False}) == "False" and "지지되지 않았습니다" in rd.meaning("False")
    assert rd.verdict(BY["regime_weights_kr"], {"reading": "FIGURES_ONLY"}) == "FIGURES_ONLY"
    both = rd.verdict(BY["kr_method_240"], {"verdict": {"M2": "NOT_DISTINGUISHED", "M1": "METHOD_SUPPORTED"}})
    assert both == "M1: METHOD_SUPPORTED, M2: NOT_DISTINGUISHED" and rd.meaning(both).startswith("M1: 매매법이 지지됐습니다; M2: 구분되지 않았습니다")
    assert rd.verdict(BY["kr_method_240"], {"verdict": "NO_PRIMARY"}) == "NO_PRIMARY" and rd.verdict(BY["kr_forward"], {}) == "?" and rd.meaning("SOMETHING_NEW") == "뜻은 규칙 문서에 있습니다"
    text = rd.text(BY["kr_traded_universe"], {"universe": {"reading": "FORMER_BETTER"}})
    assert "[판정 · 한국 이전 스캔 대상(거래대금)] FORMER_BETTER" in text and "이전 스캔 대상 쪽이 나았습니다." in text and "자동으로 되돌리지 않습니다" in text and "QSF_KR_TRADED_UNIVERSE.json" in text


# ---------------------------------------------------------------------- the daily job
def test_nothing_is_run_before_a_record_is_long_enough(tmp_path):
    d, calls, sent, _ = job(tmp_path)
    fill(tmp_path, "kr_cap_universe", 259)
    assert d._readings({}) == {} or all(not v for v in d._readings({}).values())
    assert calls == [] and sent == []


def test_a_due_reading_is_asked_once_a_day_and_told_once(tmp_path):
    fill(tmp_path, "kr_cap_universe", 260)
    d, calls, sent, _ = job(tmp_path)                                # the command refuses: no report appears
    st = {}
    got = d._readings(st)
    assert calls == [("READING", ["qsf", "kr-cap-universe-evaluate"])] and got["kr_cap_universe"] == {"tried": "2027-11-20", "rc": 1, "failed": 1} and sent == []
    d._readings(st)
    assert len(calls) == 1                                           # not twice on one day
    nxt, calls2, sent2, _ = job(tmp_path, DAY + timedelta(days=1), writes={"kr_cap_universe": {"universe": {"reading": "SAME_DIRECTION_NOT_SIGNIFICANT"}}})
    got = nxt._readings(st)
    assert len(calls2) == 1 and len(sent2) == 1 and "SAME_DIRECTION_NOT_SIGNIFICANT" in sent2[0] and "통계로 구분되지 않았습니다" in sent2[0]
    assert got["kr_cap_universe"]["delivered"] is True and got["kr_cap_universe"]["verdict"] == "SAME_DIRECTION_NOT_SIGNIFICANT" and st["readings"] == got
    later, calls3, sent3, _ = job(tmp_path, DAY + timedelta(days=2))
    later._readings(st)
    assert calls3 == [] and sent3 == []                              # read and told: never again


def test_an_undelivered_verdict_is_told_again_without_reading_again_and_a_typed_reading_is_told_too(tmp_path):
    fill(tmp_path, "kr_swing_prior", 300)
    st = {}
    d, calls, sent, _ = job(tmp_path, tg="FAILED", writes={"kr_swing_prior": {"verdict": "DECISION_SUPPORTED"}})
    assert d._readings(st)["kr_swing_prior"]["delivered"] is False and len(calls) == 1 and len(sent) == 1
    d2, calls2, sent2, _ = job(tmp_path, DAY + timedelta(days=1))
    assert d2._readings(st)["kr_swing_prior"]["delivered"] is True and calls2 == [] and len(sent2) == 1 and "2026-11-11에 공식을 바꾼 결정이 지지됐습니다" in sent2[0]
    p = rd.report_path(tmp_path, BY["kr_forward"])                    # someone typed the command: the report is there although the record count is not
    p.write_text(json.dumps({"verdict": "NO_EVIDENCE"}), encoding="utf-8")
    d3, calls3, sent3, _ = job(tmp_path, DAY + timedelta(days=2))
    assert d3._readings(st)["kr_forward"]["delivered"] is True and calls3 == [] and len(sent3) == 1 and "확인되지 않았다는 뜻" in sent3[0]
    quiet, _, _, shown = job(tmp_path, tg="NOT_CONFIGURED")
    assert quiet._readings({})["kr_forward"]["delivered"] is True and shown[0] == ("판정", "한국 가격 점수: NO_EVIDENCE")


def test_a_reading_that_keeps_refusing_is_told_once_and_then_asked_weekly(tmp_path):
    fill(tmp_path, "us_challenger", 900)
    st, runs, told = {}, 0, []
    for k in range(rd.GIVE_UP + 20):
        d, calls, sent, _ = job(tmp_path, DAY + timedelta(days=k))
        d._readings(st)
        runs += sum(1 for c in calls if c[1] == ["qsf", "us-challenger-evaluate-swing"])
        told += [s for s in sent if "미국 도전자 점수 · 스윙" in s]
    m = st["readings"]["us_challenger_swing"]
    assert len(told) == 1 and f"{rd.GIVE_UP}번 읽지 못했습니다" in told[0] and "data/automation/logs/" in told[0] and m["warned"] is True
    assert runs == rd.GIVE_UP + 2 and m["failed"] == runs                 # daily for GIVE_UP days (0..14), then a week apart: days 21 and 28
    assert st["readings"]["us_challenger_long"]["failed"] == runs         # each reading on its own count


def test_one_reading_failing_does_not_stop_the_others(tmp_path, monkeypatch):
    fill(tmp_path, "kr_cap_universe", 260)
    fill(tmp_path, "kr_swing_prior", 260)
    real = rd.due
    monkeypatch.setattr(rd, "due", lambda base, e: (_ for _ in ()).throw(OSError("disk")) if e["key"] == "kr_cap_universe" else real(base, e))
    d, calls, sent, _ = job(tmp_path, writes={"kr_swing_prior": {"verdict": "PRIOR_BETTER"}})
    got = d._readings({})
    assert got["kr_cap_universe"] == {"error": "OSError"} and got["kr_swing_prior"]["delivered"] is True and len(sent) == 1


# ---------------------------------------------------------------------- the screen
def test_the_schedule_lists_every_reading_with_its_progress_and_its_verdict(tmp_path):
    fill(tmp_path, "kr_method", 130)
    fill(tmp_path, "kr_cap_universe", 100)
    p = rd.report_path(tmp_path, BY["kr_swing_challenger"])
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"verdict": "CHALLENGER_BETTER"}), encoding="utf-8")
    got = rd.status(tmp_path, date(2026, 11, 16), {"kr_method_120": {"failed": 2}})
    rows = {r["key"]: r for r in got["readings"]}
    assert got["total"] == 26 and got["read"] == 1 and got["guide"] == "reports/RUNBOOK.md" and "사람이 할 일은 없습니다" in got["note"]
    assert rows["kr_method_120"]["state"] == "DUE" and rows["kr_method_120"]["attempts"] == 2 and rows["kr_method_240"]["state"] == "WAITING" and rows["kr_method_240"]["left"] == 120
    assert rows["kr_cap_universe"]["left"] == 160 and rows["kr_cap_universe"]["expected"] == "2027-06" and rows["kr_cap_universe"]["applies_itself"] is False
    assert rows["kr_swing_challenger"]["state"] == "READ" and rows["kr_swing_challenger"]["verdict"] == "CHALLENGER_BETTER" and "도전자 공식이 지금 공식보다 나았습니다" in rows["kr_swing_challenger"]["meaning"]
    assert rows["TO-1_KR"]["applies_itself"] is True and rows["RK-1_US"]["wanted"] == 240 and rows["TO-1_US"]["state"] == "WAITING" and rows["RK-1_KR"]["left"] == 240


def test_the_readings_are_wired_into_the_daily_job_the_server_and_the_screen():
    job_src = (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")
    assert job_src.index('st["last_run"] = ') < job_src.index("self._readings(st)                  # after the day's summary went out") < job_src.index("# What reaches Telegram, as chosen by the user")
    assert '("GET", "/api/qsf/readings")' in (ROOT / "terminal" / "server.py").read_text(encoding="utf-8")
    js = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert 'api("/api/qsf/readings")' in js and '<div id="qsfreadings"></div>' in js and "qsfReadings(); qsfTop3();" in js and "판정 일정" in js
    assert (ROOT / rd.GUIDE).exists()
