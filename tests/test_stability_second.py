"""Second batch of the 2026-11-15 stability review (reports/STABILITY_REVIEW_2026_11_15.md): each test pins one finding.
None of them changes a score or a stored record; A2 adds a line to the provenance of a card scored from a stored copy."""
import gzip
import json
from datetime import timedelta

import numpy as np
import pytest

from terminal import automation, model_scan as ms, sources
from terminal.qsf import kr_bars, krx_history, ledger
from terminal.qsf import service as qsf_service
from tests.test_daily_kr_scan import SESSION as KR_DAY, write_run
from tests.test_qsf import NOW, SESSION, FakeSrc, FakeTerm, card
from tests.test_terminal_4 import TUE_NIGHT, WED_NIGHT, clean_env, ledger as lab_ledger, make  # noqa: F401  (clean_env is an autouse fixture)


# ---------------------------------------------------------------------- A2: a stored copy that stood in is named
class Flaky(FakeSrc):
    """Answers once, then every SEC request fails."""
    def __init__(self):
        self.down = False

    def sec_companyfacts(self, cik):
        if self.down:
            raise RuntimeError("SEC HTTP_403")
        return super().sec_companyfacts(cik)

    def sec_submissions(self, cik):
        if self.down:
            raise RuntimeError("SEC HTTP_403")
        return super().sec_submissions(cik)


def test_a_card_scored_from_a_stored_copy_says_which_input_was_old_and_a_fresh_one_says_nothing(tmp_path):
    src, clock = Flaky(), {"now": NOW.timestamp()}
    svc = qsf_service.QSF(tmp_path, src=src, now=lambda: NOW, terminal=FakeTerm())
    svc.cache.clock = lambda: clock["now"]
    fresh = svc.evaluate("AAA")["cards"]["SWING"]
    assert "stale" not in fresh["provenance"]
    src.down, clock["now"] = True, NOW.timestamp() + 3 * 86400          # three days on, SEC refuses: the copies on file are used
    svc._regime_at.clear()
    old = svc.evaluate("AAA")["cards"]["SWING"]
    marks = {x["what"]: x for x in old["provenance"]["stale"]}
    assert set(marks) == {"SEC 재무제표", "SEC 공시 목록"} and marks["SEC 재무제표"]["age_days"] == 3.0 and marks["SEC 재무제표"]["error"] == "RuntimeError"
    assert old["score"] == fresh["score"]                                 # the score is what it was; only the label is new
    assert ledger.snapshot(old)["provenance"]["stale"] == old["provenance"]["stale"]      # and the record carries it
    assert qsf_service._stale("x", {"status": "REAL", "age_s": 5}) == [] and qsf_service._stale("x", None) == []


# ---------------------------------------------------------------------- B5: a run that outlasts its session
def test_a_run_starts_over_when_a_new_session_completes_under_it(tmp_path, monkeypatch):
    clock = {"now": TUE_NIGHT}
    d, calls, sent = make(tmp_path)
    d.now = lambda: clock["now"]
    plain = d.runner

    def runner(name, argv):
        rc = plain(name, argv)
        if name == "QSF" and clock["now"] == TUE_NIGHT:
            clock["now"] = WED_NIGHT                                      # the lid was closed here and opened a day later
        return rc
    d.runner = runner
    res = d.run()
    st = d.state()
    assert res["session"] == "2026-11-04" and st["last_cut"]["session"] == "2026-11-03" and st["last_cut"]["before"] == "QSF_KR"
    assert set(st["sessions"]["2026-11-03"]) == {"LAB", "SCAN", "TRACK", "QSF"}       # what ran before the gap stays under its own session
    assert all(st["sessions"]["2026-11-04"][n]["status"] in (automation.OK, automation.SKIPPED) for n in automation.STEP_NAMES)
    assert calls.count("LAB") == 2 and calls.count("QSF_KR") == 1 and "2026-11-04" in sent[0] and len(sent) == 1
    assert (tmp_path / "bk" / "2026-11-04").is_dir() and not (tmp_path / "bk" / "2026-11-03").exists()


# ---------------------------------------------------------------------- B6: the morning after a Korean holiday
def test_no_newer_korean_session_than_the_recorded_one_is_waiting_not_a_failure(tmp_path):
    d, calls, sent = make(tmp_path, rc={"QSF_KR": 5})
    step = d.run()["steps"]["QSF_KR"]
    assert step["status"] == automation.WAITING and "직전 거래일은 기록되어 있음" in step["detail"]
    assert "❌" not in sent[0] and "실패한 작업" not in sent[0] and calls.count("QSF_KR") == 1
    d2, calls2, _ = make(tmp_path)
    assert d2.run()["steps"]["QSF_KR"]["status"] == automation.OK and calls2[0] == "QSF_KR"      # still asked again at the next firing
    d3, _, sent3 = make(tmp_path / "other", rc={"QSF_KR": 3})
    assert d3.run()["steps"]["QSF_KR"]["status"] == automation.FAILED and "데이터 미준비" in sent3[0]    # a day never recorded stays a failure


def test_the_scan_tells_a_recorded_session_from_one_never_recorded(tmp_path):
    lg = ledger.Ledger(tmp_path)
    assert lg.has_session(SESSION, "US") is False
    lg.append(SESSION, "US", [card()])
    assert lg.has_session(SESSION, "US") is True and lg.has_session(SESSION, "KR") is False and lg.has_session("2026-11-05", "US") is False
    src = open("app.py", encoding="utf-8").read()
    assert 'res.get("reason") == "KR_BEHIND" and res.get("recorded_before")' in src and "return 5" in src


# ---------------------------------------------------------------------- B7: the Korean model scan
def kr_scan(tmp_path, monkeypatch, newest, track=0):
    monkeypatch.setenv("QPP_CAPITAL_KRW", "10000000")
    d, calls, sent = make(tmp_path, rc={"TRACK_KR": track})
    d.kr_newest = lambda: newest
    return d, calls, sent


def test_a_failed_outcome_update_is_a_failure_and_only_the_update_is_tried_again(tmp_path, monkeypatch):
    d, calls, sent = kr_scan(tmp_path, monkeypatch, KR_DAY, track=2)
    plain = d.runner
    d.runner = lambda name, argv: (write_run(tmp_path) if name == "SCAN_KR" else None, plain(name, argv))[1]
    step = d.run()["steps"]["SCAN_KR"]
    assert step["status"] == automation.FAILED and "추적 갱신 실패(코드 2)" in step["detail"] and "❌ 한국 모델 스캔" in sent[0]
    assert calls.count("SCAN_KR") == 1 and calls.count("TRACK_KR") == 2      # the retry at the end found the scan and did not repeat it
    d2, calls2, _ = kr_scan(tmp_path, monkeypatch, KR_DAY)
    assert d2.run()["steps"]["SCAN_KR"]["status"] == automation.OK and calls2 == ["TRACK_KR"]


def test_a_session_already_scanned_is_not_scanned_again_while_the_day_is_awaited(tmp_path, monkeypatch):
    write_run(tmp_path, session="2026-11-02", name="monday")              # Monday was scanned on Tuesday; Tuesday was a holiday
    d, calls, sent = kr_scan(tmp_path, monkeypatch, "2026-11-02")
    step = d.run()["steps"]["SCAN_KR"]
    assert step["status"] == automation.WAITING and "SCAN_KR" not in calls and "이미 스캔한 거래일" in step["detail"] and "2026-11-03 자료 아님" in step["detail"]
    assert "한국 모델 스캔" not in sent[0]                                 # waiting is not put in the daily message
    assert ms.scan_of(tmp_path, "2026-11-02")["latest_session"] == "2026-11-02" and ms.scan_of(tmp_path, KR_DAY) is None
    d2, calls2, _ = kr_scan(tmp_path, monkeypatch, KR_DAY)                # the day's data is out an hour later
    plain = d2.runner
    d2.runner = lambda name, argv: (write_run(tmp_path) if name == "SCAN_KR" else None, plain(name, argv))[1]
    assert d2.run()["steps"]["SCAN_KR"]["status"] == automation.OK and calls2[:2] == ["SCAN_KR", "TRACK_KR"]


def test_a_scan_that_scored_an_older_session_leaves_the_step_waiting(tmp_path, monkeypatch):
    d, calls, _ = kr_scan(tmp_path, monkeypatch, None)                    # the newest session could not be told: the scan runs as before
    plain = d.runner
    d.runner = lambda name, argv: (write_run(tmp_path, session="2026-11-02") if name == "SCAN_KR" else None, plain(name, argv))[1]
    step = d.run()["steps"]["SCAN_KR"]
    assert step["status"] == automation.WAITING and calls.count("SCAN_KR") == 1 and "2026-11-03 자료 아님" in step["detail"]
    assert automation.Daily(tmp_path, runner=lambda n, a: 0).kr_newest() is None       # a stand-in runner asks the provider nothing


# ---------------------------------------------------------------------- D1: the validation report reads a few fields
def test_the_light_reading_gives_the_same_report_as_whole_snapshots(tmp_path):
    lg = ledger.Ledger(tmp_path)
    days = ["2026-10-%02d" % k for k in range(1, 29)]
    for n, day in enumerate(days):
        cards = []
        for k in range(4):
            c = card(ticker=f"T{k}")
            c["data_date"] = day
            for j, f in enumerate(c["factors"]):
                if f.get("normalized") is not None:
                    f["normalized"] = float((n * 7 + k * 3 + j * (1 if j % 2 else -1) * n) % 11)
            cards.append(c)
        lg.append(day, "US", cards)
    whole, small = lg.snapshots(market="US"), lg.snapshots(market="US", keep=ledger.light)
    assert len(whole) == len(small) == 112 and set(small[0]) == set(ledger.LIGHT) | {"norm"}
    a, b = ledger.factor_correlations(whole), ledger.factor_correlations(small)
    assert a == b and a["status"] == "REAL" and a["high_pairs"]           # the same pairs, the same numbers, the same order
    loader = lambda t: []                                                 # noqa: E731
    assert ledger.validate(whole, "US", "SWING", loader, []) == ledger.validate(small, "US", "SWING", loader, [])
    assert lg.snapshots(market="US", keep=lambda s: s["ticker"] if s["ticker"] == "T1" else None) == ["T1"] * 28      # None leaves a snapshot out


# ---------------------------------------------------------------------- D2: the panel is built day by day
def test_the_panel_built_day_by_day_holds_what_the_files_hold(tmp_path):
    root = tmp_path / kr_bars.KRX
    rows = {"2026-11-10": {"KOSPI": [["005930", "70,000"], ["000660", "x"]], "KOSDAQ": [["035720", "50"]]},
            "2026-11-11": {"KOSPI": [["005930", "71000"]], "KOSDAQ": [["035720", "51"], ["035720", "52"], ["900000", "9"]]}}
    width = max(kr_bars.COLS) + 1 if not isinstance(kr_bars.COLS, dict) else max(kr_bars.COLS.values()) + 1
    for day, boards in rows.items():
        for b, items in boards.items():
            (root / b).mkdir(parents=True, exist_ok=True)
            full = [[code] + [price] * (width - 1) for code, price in items]
            with gzip.open(root / b / f"{day}.json.gz", "wt", encoding="utf-8") as fh:
                json.dump(full, fh)
    p = kr_bars.build_panel(root, sorted(rows))
    codes = list(p["codes"])
    assert codes == ["000660", "005930", "035720", "900000"] and p["data"].shape == (6, 2, 4)
    at = lambda day, code: p["data"][kr_bars.CLOSE, sorted(rows).index(day), codes.index(code)]      # noqa: E731
    assert at("2026-11-10", "005930") == 70000.0 and np.isnan(at("2026-11-10", "000660")) and np.isnan(at("2026-11-10", "900000"))
    assert at("2026-11-11", "035720") == 52.0 and np.isnan(at("2026-11-11", "000660"))       # a code listed twice in a day: the later row


# ---------------------------------------------------------------------- E3: earnings dates the provider does not list
class NoDates(FakeSrc):
    def __init__(self):
        self.asked, self.answer = 0, []

    def yahoo_earnings_dates(self, t):
        self.asked += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_no_listed_date_is_remembered_for_a_few_hours_and_a_date_still_ahead_is_kept(tmp_path):
    src, clock = NoDates(), {"now": NOW.timestamp()}
    svc = qsf_service.QSF(tmp_path, src=src, now=lambda: NOW, terminal=FakeTerm())
    svc.cache.clock = lambda: clock["now"]
    first = svc._earnings("AAA", "US", SESSION)
    again = svc._earnings("AAA", "US", SESSION)
    assert src.asked == 1 and first == again                              # the second lookup does not ask
    clock["now"] += qsf_service.EARN_NONE_TTL + 1
    svc._earnings("AAA", "US", SESSION)
    assert src.asked == 2                                                 # the next morning's scan does
    src.answer = ["2026-12-15"]
    clock["now"] += qsf_service.EARN_NONE_TTL + 1
    assert svc._earnings("AAA", "US", SESSION)["date"] == "2026-12-15" and src.asked == 3
    src.answer = []                                                       # the provider drops a date that is still ahead
    clock["now"] += qsf_service.TTL["earn"] + 1
    assert svc._earnings("AAA", "US", SESSION)["date"] == "2026-12-15" and src.asked == 4     # the stored date stays in use, as before
    assert svc._earnings("AAA", "US", SESSION)["date"] == "2026-12-15" and src.asked == 5     # and the provider is asked again


def test_after_a_rate_limit_refusal_earnings_dates_are_not_asked_for_a_while(tmp_path, monkeypatch):
    class YFRateLimitError(Exception):
        pass
    src = NoDates()
    src.answer = YFRateLimitError("too many")
    svc = qsf_service.QSF(tmp_path, src=src, now=lambda: NOW, terminal=FakeTerm())
    t = {"now": 1000.0}
    monkeypatch.setattr(qsf_service.time, "time", lambda: t["now"])
    for ticker in ("AAA", "BBB", "CCC"):
        svc._earnings(ticker, "US", SESSION)
    assert src.asked == 1                                                 # the stocks after the refusal are not asked
    t["now"] += qsf_service.EARN_PAUSE_S + 1
    svc._earnings("DDD", "US", SESSION)
    assert src.asked == 2


# ---------------------------------------------------------------------- E4: one SEC pace for every process, and a pause after a refusal
class Reply:
    def __init__(self, code):
        self.status_code, self.text = code, "{}"

    def json(self):
        return {}


def test_sec_requests_share_one_pace_file_and_stop_after_a_refusal(tmp_path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Research Tool qse-tests@mailbox-test.net")
    pace = tmp_path / "pace.json"
    monkeypatch.setattr(sources, "SEC_PACE_FILE", pace)
    t, naps, sent = {"now": 5000.0}, [], []
    monkeypatch.setattr(sources.time, "time", lambda: t["now"])
    monkeypatch.setattr(sources.time, "sleep", lambda s: (naps.append(round(s, 3)), t.__setitem__("now", t["now"] + s)))
    codes = iter([200, 200, 403])
    monkeypatch.setattr(sources.requests, "get", lambda url, **kw: (sent.append(url), Reply(next(codes)))[1])
    sources._sec_get("https://data.sec.gov/a")
    pace.write_text(json.dumps({"last": t["now"] - 0.05}))                # another process asked 0.05 s ago
    sources._sec_get("https://data.sec.gov/b")
    assert naps == [round(sources.SEC_MIN_INTERVAL - 0.05, 3)]             # this one waits out the rest of the interval
    with pytest.raises(RuntimeError, match="HTTP_403"):
        sources._sec_get("https://data.sec.gov/c")
    assert sources.sec_pause_left() == pytest.approx(sources.SEC_PAUSE_S)
    with pytest.raises(sources.SecPaused):
        sources.sec_text("https://www.sec.gov/d")                         # nothing is sent while the pause lasts
    assert len(sent) == 3 and "mailbox-test" not in pace.read_text()
    t["now"] += sources.SEC_PAUSE_S + 1
    monkeypatch.setattr(sources.requests, "get", lambda url, **kw: (sent.append(url), Reply(200))[1])
    assert sources._sec_get("https://data.sec.gov/e") == {} and len(sent) == 4


def test_a_stand_in_http_never_touches_the_shared_pace_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "Research Tool qse-tests@mailbox-test.net")
    pace = tmp_path / "pace.json"
    monkeypatch.setattr(sources, "SEC_PACE_FILE", pace)

    class Http:
        @staticmethod
        def get(url, **kw):
            return Reply(403)
    with pytest.raises(RuntimeError, match="HTTP_403"):
        sources._sec_get("https://data.sec.gov/a", Http)
    assert not pace.exists() and sources.sec_pause_left() == 0.0


# ---------------------------------------------------------------------- E6: a KRX reply that is not the data
def test_a_krx_page_that_is_not_json_is_a_failed_call_and_the_download_goes_on(tmp_path):
    class Html:
        status_code = 200

        def json(self):
            raise ValueError("Expecting value")

    class Good:
        status_code = 200

        def json(self):
            return {"OutBlock_1": [{f: "1" for f in krx_history.FIELDS}]}
    replies = iter([Html(), Good(), Good(), Good()])
    logs = []
    res = krx_history.download(tmp_path, "k", lambda *a, **k: next(replies), "2026-11-09", "2026-11-10", sleep=lambda s: None, log=logs.append)
    assert any("unreadable reply (ValueError)" in x for x in logs) and len(list(tmp_path.rglob("*.json.gz"))) == 3
    always = krx_history.download(tmp_path / "b", "k", lambda *a, **k: Html(), "2026-10-01", "2026-11-10", sleep=lambda s: None, log=lambda *_: None)
    assert json.dumps(always).count("TOO_MANY_FAILURES") == 1 and not list((tmp_path / "b").rglob("*.json.gz"))
