"""Review of 2026-11-17 (reports/CODE_REVIEW_2026_11_17.md): what would have gone wrong unattended, years from now."""
import gzip
import json

import pytest

from terminal.qsf import ledger as lg, price_archive as pa
from utils import durable


def bars(days, close=10.0, adj=None, open_=None):
    return [{"date": d, "open": open_ if open_ is not None else close, "close": close, "adj_close": adj if adj is not None else close} for d in days]


OLD_DAYS = ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]


# ---------------------------------------------------------------------- one price basis in the archive
def test_days_that_left_the_download_window_follow_a_split():
    old = bars(OLD_DAYS, close=100.0)
    new = bars(OLD_DAYS[2:] + ["2026-10-12"], close=10.0)                 # a 10:1 split since: the whole new series is on the new basis
    out = pa.merge(old, new)
    assert [b["date"] for b in out] == OLD_DAYS + ["2026-10-12"]
    assert all(b["close"] == pytest.approx(10.0) and b["open"] == pytest.approx(10.0) and b["adj_close"] == pytest.approx(10.0) for b in out)


def test_a_dividend_moves_only_the_adjusted_close_of_the_kept_days():
    old = bars(OLD_DAYS, close=100.0, adj=100.0)
    new = bars(OLD_DAYS[2:] + ["2026-10-12"], close=100.0, adj=98.0)
    out = pa.merge(old, new)
    assert out[0]["close"] == 100.0 and out[0]["open"] == 100.0 and out[0]["adj_close"] == pytest.approx(98.0)


def test_rounding_noise_and_a_gap_leave_the_kept_days_untouched():
    old = bars(OLD_DAYS, close=100.0)
    out = pa.merge(old, bars(OLD_DAYS[2:], close=100.000001))
    assert out[:2] == old[:2]                                             # the very same numbers, not multiplied by 1.00000001 each day
    out = pa.merge(old[:2], bars(["2026-10-12", "2026-10-13"], close=10.0))
    assert out[:2] == old[:2]                                             # no shared day: nothing to compare, nothing changed


def test_one_bad_bar_cannot_set_the_ratio():
    old = bars(OLD_DAYS, close=100.0)
    new = bars(OLD_DAYS[2:], close=100.0)
    new[0] = {**new[0], "close": 50.0, "adj_close": 50.0}                 # one wrong bar on the first shared day
    assert pa.merge(old, new)[0]["close"] == 100.0


def test_a_flat_stock_stays_flat_across_the_boundary_after_a_split():
    """The reviewer's case: without one basis, a record entered on a kept day and left on a new one showed -90%."""
    old = bars(OLD_DAYS, close=100.0)
    path = pa.merge(old, bars(OLD_DAYS[3:] + ["2026-10-12", "2026-10-13"], close=10.0))
    o = lg.outcome(path, [], "2026-10-01", 8, 0.0, "2026-10-02")
    assert o is not None and o["entry_date"] == "2026-10-02" and o["gross"] == pytest.approx(0.0)


# ---------------------------------------------------------------------- an unreadable archive is not an empty one
def _archive(tmp_path, market="KR"):
    p = pa.path_of(tmp_path, market)
    p.parent.mkdir(parents=True)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump({"tickers": {"A": {"bars": bars(OLD_DAYS), "via": "YAHOO"}}}, fh)
    return p


@pytest.mark.parametrize("damage", ["cut", "empty", "garbage"])
def test_an_unreadable_archive_is_never_written_over(tmp_path, damage):
    p = _archive(tmp_path)
    whole = p.read_bytes()
    p.write_bytes({"cut": whole[:len(whole) // 2], "empty": b"", "garbage": b"not a gzip file"}[damage])
    left = p.read_bytes()
    with pytest.raises(pa.Unreadable):
        pa.update(tmp_path, "KR", lambda t: [], lambda syms: {}, lambda t: [t])
    assert p.read_bytes() == left                                         # still there for a person to look at; the backup has a dated copy
    assert pa.read(tmp_path, "KR") == {}                                  # a screen shows nothing rather than failing
    assert pa.loader(tmp_path, "KR", lambda t: bars(OLD_DAYS[-2:]))("A") == bars(OLD_DAYS[-2:])
    with pytest.raises(pa.Unreadable):                                    # a long reading does not go ahead on the scan's stocks alone
        pa.loader(tmp_path, "KR", lambda t: [], longest=True)


def test_no_archive_yet_is_an_empty_one(tmp_path):
    assert pa.read(tmp_path, "US", strict=True) == {}


# ---------------------------------------------------------------------- an outcome never starts at the first bar of a late series
def test_a_series_that_starts_after_the_entry_gives_no_outcome():
    late = bars(["2027-01-04", "2027-01-05", "2027-01-06", "2027-01-07"])
    late[-1] = {**late[-1], "close": 20.0, "adj_close": 20.0}
    days = [b["date"] for b in late]
    assert lg.outcome(late, [], "2026-11-09", 4, 0.0, "2026-11-10") is None
    assert lg.outcome(late, [], "2026-11-09", 4, 0.0, "2026-11-10", days) is None
    assert lg.outcome(late, [], "2026-11-09", 4, 0.0) is None             # the historical form, without a recorded entry session
    assert lg.outcome([], [], "2026-11-09", 4, 0.0, "2026-11-10") is None


def test_a_series_that_starts_on_the_entry_day_still_gives_one():
    path = bars(["2026-11-10", "2026-11-11", "2026-11-12"])
    for form in (None, [b["date"] for b in path]):
        o = lg.outcome(path, [], "2026-11-09", 3, 0.0, "2026-11-10", form)
        assert o["entry_date"] == "2026-11-10" and o["exit_date"] == "2026-11-12"


# ---------------------------------------------------------------------- whole or not at all
def test_durable_write_replaces_only_with_a_complete_file(tmp_path):
    target = tmp_path / "x.json"
    durable.write_text(target, "one")
    durable.write_text(target, "둘")
    assert target.read_text(encoding="utf-8") == "둘" and not list(tmp_path.glob("*.tmp"))


# ====================================================================== the daily job says what stopped
import os                                                   # noqa: E402
import shutil                                               # noqa: E402
from datetime import date, datetime, timedelta, timezone    # noqa: E402
from pathlib import Path                                    # noqa: E402

from terminal import automation, record_status, store_watch  # noqa: E402
from terminal.automation import Daily                       # noqa: E402
from terminal.qsf import krx_history as kh, rank_book as rb, readings as rd, turnover_book as tb  # noqa: E402
from utils import nyse_calendar                             # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2027, 3, 2, 0, 0, tzinfo=timezone.utc)


def index(base, store, days, cut=False):
    folder = base / "research_data" / store
    folder.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps({"session": d}) + "\n" for d in days) + ('{"session": "20' if cut else "")
    (folder / "index.jsonl").write_text(body, encoding="utf-8")


def days_from(n, start=date(2027, 2, 1)):
    return [(start + timedelta(days=k)).isoformat() for k in range(n)]


def job(tmp_path, tg="SENT"):
    sent, shown, calls = [], [], []

    def telegram(text):
        sent.append(text)
        return {"status": tg} if tg != "FAILED" else {"status": "FAILED", "error": "HTTP 401"}

    def macos(title, body):
        shown.append((title, body))
        return {"status": "SENT"}

    def runner(name, argv):
        calls.append((name, list(argv)))
        return 1
    return Daily(tmp_path, now=lambda: NOW, runner=runner, telegram=telegram, macos=macos, backup_dir=tmp_path / "bk"), sent, shown, calls


def test_a_record_that_stopped_is_named_and_the_others_are_not(tmp_path):
    d = days_from(10)
    index(tmp_path, "krx_forward", d)
    index(tmp_path, "paper_book_kr", d[:7])                 # three sessions behind the market's newest record: stopped
    index(tmp_path, "forecast_kr", d[:8])                   # two behind: a lag, not a stop
    index(tmp_path, "kr_method", d, cut=True)               # its index ends in a cut line
    index(tmp_path, "us_challenger", d[:4])                 # the other market is judged on its own
    index(tmp_path, "paper_book_us", d[:4])
    index(tmp_path, "turnover_book_kr", d[:2])              # ended by design: its reading was made
    got = store_watch.look(tmp_path, automation.FORWARD_STORES, finished=["turnover_book_kr"])
    assert [(g["store"], g["problem"]) for g in got] == [("kr_method", "INDEX_TORN"), ("paper_book_kr", "BEHIND")]
    assert got[1]["last"] == d[6] and got[1]["behind"] == 3
    line = store_watch.text(got)
    assert "기록이 멈춘 곳 2개" in line and "모의 장부(한국)(마지막 " + d[6] in line and "한국 독자 매매법(색인 파일 손상)" in line
    assert store_watch.text([]) is None and store_watch.look(tmp_path / "empty", automation.FORWARD_STORES) == []


def test_a_price_archive_that_is_no_longer_written_is_named(tmp_path):
    p = tmp_path / store_watch.ARCHIVE / "US.json.gz"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    assert store_watch.look(tmp_path, [], now=p.stat().st_mtime + 5 * 86400) == []
    got = store_watch.look(tmp_path, [], now=p.stat().st_mtime + 8 * 86400)
    assert got == [{"store": "price_archive_us", "label": "가격 보관 파일(미국)", "problem": "STALE", "days": 8}] and "8일째 갱신 없음" in store_watch.text(got)


def test_the_days_message_and_the_screen_carry_the_notes(tmp_path):
    d = days_from(10)
    index(tmp_path, "krx_forward", d)
    index(tmp_path, "score_split_kr", d[:5])
    daily, _, _, _ = job(tmp_path)
    st = {"cache_prune": {"error": "OSError"}, "readings": {"us_challenger": {"error": "KeyError"}, "kr_method": {"delivered": True}}, "rank_reading": {"KR": {"error": "JSONDecodeError"}}}
    assert daily._store_watch(st)["items"][0]["store"] == "score_split_kr"
    notes = Daily._notes(st)
    assert len(notes) == 2 and "점수 분리 비교(한국)" in notes[0] and "캐시 정리(OSError)" in notes[1] and "판정 읽기(KeyError)" in notes[1] and "순위 규칙 판정 확인(JSONDecodeError)" in notes[1]
    alerts = {"status": "OK", "items": []}
    text = Daily.compose("2027-02-26", {}, alerts, [], [], None, None, notes)
    assert "⚠️ 기록이 멈춘 곳 1개" in text and "⚠️ 마무리 점검 중 실패한 것" in text
    assert "⚠️" not in Daily.compose("2027-02-26", {}, alerts, [], []) and Daily._notes({}) == []
    daily._save({"sessions": {}, **st})
    assert automation.status(tmp_path)["notes"] == notes
    job_text = (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")
    assert job_text.index("self._rank_reading(st)\n") < job_text.index("self._store_watch(st)\n") < job_text.index("alerts = self._alerts()")


def test_the_screen_says_when_telegram_stopped_delivering():
    base = {"US": {"calendar_status": "REAL", "sessions": 3, "behind_sessions": 0, "missing": [], "last": "2027-02-26"}}
    auto = {"installed": True, "steps": {}, "last_run": {"telegram": {"status": "FAILED", "error": "HTTP 401"}}, "notes": ["기록이 멈춘 곳 1개: x"]}
    got = record_status.alerts(base, {"capital_configured": True, "status": "REAL"}, auto, "OK")
    assert any(a["level"] == "bad" and "텔레그램 전달 실패(HTTP 401)" in a["text"] for a in got) and any(a["text"] == "기록이 멈춘 곳 1개: x" for a in got)
    fine = record_status.alerts(base, {"capital_configured": True, "status": "REAL"}, {"installed": True, "steps": {}, "last_run": {"telegram": {"status": "SENT"}}}, "OK")
    assert not any("텔레그램" in a["text"] for a in fine)


# ---------------------------------------------------------------------- a damaged verdict file
def verdict_file(base, book, market, body):
    p = base / book.REPORTS[market]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


@pytest.mark.parametrize("book", [tb, rb])
@pytest.mark.parametrize("body", ["", "{}", '{"decision": "ADO', "[]"])
def test_a_damaged_verdict_file_is_neither_unread_nor_a_verdict(tmp_path, book, body):
    verdict_file(tmp_path, book, "US", body)
    rep = book.report(tmp_path, "US")
    assert rep["status"] == "DAMAGED" and book.REPORTS["US"].name in rep["reason"] and book.active_rules(tmp_path, "US") is None
    assert book.read_when_due(tmp_path, "US") == rep                # the reading is not asked: it would refuse, the file exists
    seen = book.status(tmp_path, "US")
    assert seen["status"] == "DAMAGED" and seen["damaged"] == rep["reason"] and "decision" not in seen
    assert book.report(tmp_path, "KR") is None and book.status(tmp_path, "KR")["damaged"] is None


@pytest.mark.parametrize("book,key,run", [(tb, "turnover_reading", "_turnover_reading"), (rb, "rank_reading", "_rank_reading")])
def test_damage_after_the_verdict_was_told_is_told_once_and_clears_when_restored(tmp_path, book, key, run):
    whole = json.dumps({"status": "REAL", "decision": "ADOPT", "market": "US", "first": "a", "last": "b", "difference": {"days": 240}, "why": ["x"], "consequence": "c"})
    p = verdict_file(tmp_path, book, "US", whole)
    daily, sent, _, _ = job(tmp_path)
    st = {}
    in_force = False                         # both readings report and switch nothing on (user decisions 2026-11-22): the button on the screen does
    assert getattr(daily, run)(st)["US"]["delivered"] is True and len(sent) == 1 and (book.active_rules(tmp_path, "US") is not None) is in_force
    getattr(daily, run)(st)
    assert len(sent) == 1                                           # told once
    p.write_text(whole[:40], encoding="utf-8")
    got = getattr(daily, run)(st)["US"]
    assert got["delivered"] is True and got["warned"] is True and got["decision"] == "ADOPT" and len(sent) == 2 and "읽을 수 없습니다" in sent[1]
    assert getattr(daily, run)(st)["US"]["warned"] is True and len(sent) == 2      # the damage is told once too
    p.write_text(whole, encoding="utf-8")
    assert getattr(daily, run)(st)["US"]["warned"] is False and len(sent) == 2 and (book.active_rules(tmp_path, "US") is not None) is in_force


def test_the_switch_takes_the_words_people_type_and_names_the_ones_it_does_not(monkeypatch, tmp_path):
    for typed, mode in (("", "auto"), ("auto", "auto"), (" ON ", "on"), ("true", "on"), ("1", "on"), ("yes", "on"), ("off", "off"), ("false", "off"), ("0", "off"), ("No", "off"),
                        ("off  # 2027-12 끔", "off"), ('"off"', "off")):
        monkeypatch.setenv(tb.ENV, typed)
        monkeypatch.setenv(rb.ENV, typed)
        assert (tb.mode(), rb.mode(), tb.switch_of(tb.ENV)["unknown"]) == (mode, mode, None), typed
    monkeypatch.setenv(rb.ENV, "sometimes")
    assert rb.mode() == "auto" and rb.status(tmp_path, "KR")["switch_unknown"] == "sometimes" and tb.status(tmp_path, "KR")["switch_unknown"] is None
    js = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert js.count("qsfBookWarn(") == 3 and "b.switch_unknown" in js and "b.damaged" in js


def test_a_registry_report_that_is_not_a_report_is_said_at_once_and_not_asked_again(tmp_path):
    e = rd.REGISTRY[0]
    p = rd.report_path(tmp_path, e)
    p.parent.mkdir(parents=True)
    p.write_text("", encoding="utf-8")
    daily, sent, _, calls = job(tmp_path)
    st = {}
    daily._readings(st)
    daily._readings(st)
    assert len(sent) == 1 and e["report"] in sent[0] and "손상" in sent[0] and not calls and st["readings"][e["key"]]["damaged"] is True


def test_the_comparison_books_wait_when_the_paper_book_failed():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    guard, first = app.index('if res.get("status") == "FAILED":'), app.index('res["turnover_book"] = _turnover_book_record(market, q, info, bench)')
    assert app.index("res = paper_book.record(PROJECT_ROOT, market, q._loader(market)") < guard < first and 'f"PAPER_BOOK_{res.get(\'reason\')}"' in app


# ---------------------------------------------------------------------- files that are trusted without a guard
def test_an_unreadable_recent_krx_day_file_is_set_aside_and_asked_again(tmp_path):
    day = "2026-11-13"
    for board in kh.BOARDS:
        p = kh.path_of(tmp_path, board, day)
        p.parent.mkdir(parents=True)
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            json.dump([["A"] * len(kh.FIELDS)], fh)
    bad = kh.path_of(tmp_path, "KOSDAQ", day)
    bad.write_bytes(bad.read_bytes()[:20])
    asked = []

    class Reply:
        status_code = 200

        def json(self):
            return {"OutBlock_1": [{f: "1" for f in kh.FIELDS}]}

    def get(url, params, headers, timeout):
        asked.append((url.rsplit("/", 1)[-1], params["basDd"]))
        return Reply()
    out = kh.download(tmp_path, "key", get, day, day, sleep=lambda s: None, log=lambda *a: None)
    assert asked == [(kh.BOARDS["KOSDAQ"], "20261113")] and out["stored"] == 1          # only the cut file is asked again
    assert bad.with_suffix(".bad").exists() and isinstance(json.load(gzip.open(bad, "rt", encoding="utf-8")), list)
    assert kh.set_aside_unreadable(tmp_path, [day], log=lambda *a: None) == 0


def test_a_backup_copy_cut_short_does_not_keep_its_name(tmp_path, monkeypatch):
    src = tmp_path / "research_data" / "paper_book_kr" / "2027-02-01.json.gz"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"0123456789" * 100)
    report = tmp_path / "reports" / "qsf" / "QSF_SCORE_SPLIT_KR.json"
    report.parent.mkdir(parents=True)
    report.write_text("{}", encoding="utf-8")
    real = shutil.copy2
    monkeypatch.setattr(automation.shutil, "copy2", lambda s, d: Path(d).write_bytes(Path(s).read_bytes()[:7]))
    with pytest.raises(OSError):
        automation.backup(tmp_path, "2027-02-02", tmp_path / "bk")
    assert not (tmp_path / "bk" / "paper_book_kr" / src.name).exists() and not list((tmp_path / "bk").rglob("*.part"))
    monkeypatch.setattr(automation.shutil, "copy2", real)
    automation.backup(tmp_path, "2027-02-02", tmp_path / "bk")
    assert (tmp_path / "bk" / "paper_book_kr" / src.name).read_bytes() == src.read_bytes()
    assert (tmp_path / "bk" / "reports_qsf" / report.name).read_text(encoding="utf-8") == "{}"       # the one-time verdict reports are mirrored too


def test_a_full_disk_at_the_first_write_still_reaches_the_crash_notice(tmp_path, monkeypatch):
    daily, sent, shown, _ = job(tmp_path)

    def full(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(daily, "_mark", full)
    monkeypatch.setattr(daily, "_attempt", lambda res: None)
    with pytest.raises(OSError):
        daily.run()
    assert len(sent) == 1 and "OSError" in sent[0] and shown


def test_extra_nyse_closures_come_from_the_env_and_nothing_changes_without_it(monkeypatch):
    day = date(2028, 3, 6)                                          # a Monday
    monkeypatch.delenv("NYSE_EXTRA_CLOSURES", raising=False)
    assert nyse_calendar.is_session(day) and nyse_calendar.extra_closures() == frozenset()
    monkeypatch.setenv("NYSE_EXTRA_CLOSURES", "2028-03-06, not-a-date ;2028-03-07")
    assert not nyse_calendar.is_session(day) and not nyse_calendar.is_session(date(2028, 3, 7)) and nyse_calendar.is_session(date(2028, 3, 8))
    assert day.isoformat() not in [d.isoformat() for d in nyse_calendar.sessions_between(date(2028, 3, 1), date(2028, 3, 10))]
    monkeypatch.delenv("NYSE_EXTRA_CLOSURES")
    assert nyse_calendar.is_session(day)


def test_a_scan_that_was_ok_on_degraded_inputs_is_said(tmp_path):
    folder = tmp_path / store_watch.LATEST
    folder.mkdir(parents=True)
    fine = {"status": "REAL", "session": "2027-02-26", "tickers": 300, "scored": 600, "errors": {}, "price_source": {"by_source": {"KRX+YAHOO": 298, "YAHOO": 2}}}
    (folder / "latest_KR.json").write_text(json.dumps(fine), encoding="utf-8")
    (folder / "latest_US.json").write_text(json.dumps({"session": "2027-02-26", "tickers": 500, "errors": {"A": "KeyError"}, "stale_inputs": {"stocks": 12, "oldest_days": 3}}), encoding="utf-8")
    assert store_watch.quality(tmp_path) == []
    (folder / "latest_KR.json").write_text(json.dumps({**fine, "errors": {str(k): "KeyError" for k in range(40)}, "price_source": {"by_source": {"YAHOO": 300}}}), encoding="utf-8")
    (folder / "latest_US.json").write_text(json.dumps({"session": "2027-02-26", "tickers": 500, "errors": {}, "stale_inputs": {"stocks": 480, "oldest_days": 21}}), encoding="utf-8")
    got = store_watch.quality(tmp_path)
    assert len(got) == 3 and "300종목 중 40종목이 오류로 빠졌습니다(KeyError)" in got[0] and "300종목 중 300종목을 KRX 자료 없이" in got[1] and "500종목 중 480종목을 저장해 둔 재무 사본" in got[2] and "21일" in got[2]
    daily, _, _, _ = job(tmp_path)
    st = {}
    daily._store_watch(st)
    assert Daily._notes(st) == got
