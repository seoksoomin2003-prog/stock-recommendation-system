"""The separate Korean filing-event record: the test's rules, filings before the day only, written once, no early evaluation, no key on disk.  No network."""
import gzip
import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from terminal.qsf import kr_events_forward as ef, kr_forward as kf, krx_history as kh, research_kr as kr, research_kr_events as ke
from tests.test_qsf_kr_forward import STOCKS, at, market, no_calls

KEY = "not-a-real-key-456"
TITLE_FIN, TITLE_BUY = "주요사항보고서(유상증자결정)", "주요사항보고서(자기주식취득결정)"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("kr")
    return base, market(base / kr.DATA, "2025-01-01", "2026-11-06")


def linked(tmp_path, built):
    base, days = built
    run = tmp_path / "run"
    (run / kr.DATA.parent).mkdir(parents=True)
    (run / kr.DATA).symlink_to(base / kr.DATA)
    return run, days


def lists(run, rows):
    root = run / ef.LISTS
    root.mkdir(parents=True, exist_ok=True)
    (root / "corp.json").write_text("{}", encoding="utf-8")
    with gzip.open(root / "2026Q4.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(rows, fh)


def receipt(day, n=1):
    return day.replace("-", "") + f"{n:06d}"


def test_the_quarters_asked_again_are_this_one_and_the_one_before():
    assert ef.recent_quarters(date(2026, 11, 8)) == ["2026Q4", "2026Q3"]
    assert ef.recent_quarters(date(2027, 1, 4)) == ["2027Q1", "2026Q4"]


def test_a_score_uses_only_filings_received_before_its_day(tmp_path, built):
    run, days = linked(tmp_path, built)
    day, before, a, b, c = days[-1], days[-2], STOCKS[0], STOCKS[1], STOCKS[2]
    lists(run, [[receipt(before), "C", a, TITLE_FIN], [receipt(day, 2), "C", b, TITLE_FIN], [receipt(days[-3], 3), "C", c, TITLE_BUY], [receipt(before, 4), "C", STOCKS[3], "[기재정정]" + TITLE_FIN]])
    got = {r["code"]: r for r in ef.score_day(run, day)["rows"]}
    assert (got[a]["score"], got[a]["financing"], got[a]["buyback"]) == (0.0, 1, 0)
    assert (got[b]["score"], got[b]["financing"]) == (50.0, 0)          # received on the day itself
    assert (got[c]["score"], got[c]["buyback"]) == (100.0, 1)
    assert got[STOCKS[3]]["score"] == 50.0                              # an amendment is not a first filing
    assert set(got[a]) == {"code", "name", "board", "score", "financing", "buyback", "cap", "traded"}


def test_a_score_does_not_change_when_later_filings_arrive(tmp_path, built):
    run, days = linked(tmp_path, built)
    day = days[-5]
    lists(run, [[receipt(days[-6]), "C", STOCKS[0], TITLE_FIN]])
    first = ef.score_day(run, day)
    lists(run, [[receipt(days[-6]), "C", STOCKS[0], TITLE_FIN], [receipt(day), "C", STOCKS[1], TITLE_FIN], [receipt(days[-2]), "C", STOCKS[2], TITLE_BUY]])
    assert ef.score_day(run, day) == first


def test_the_window_is_the_252_sessions_of_the_test(tmp_path, built):
    run, days = linked(tmp_path, built)
    day = days[-1]
    px = kr.KrPrices(kr.build_prices(run / kr.DATA, log=lambda m: None, days=days))
    i = px.dates.index(day)
    lists(run, [[receipt(px.dates[i - 252]), "C", STOCKS[0], TITLE_FIN], [receipt(px.dates[i - 253]), "C", STOCKS[1], TITLE_FIN]])
    got = {r["code"]: r["financing"] for r in ef.score_day(run, day)["rows"]}
    assert got[STOCKS[0]] == 1 and got[STOCKS[1]] == 0


class Reply:
    def __init__(self, body=None, content=b""):
        self.body, self.content = body, content

    def json(self):
        return self.body


def corp_reply():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", b"<result></result>")
    return Reply(content=buf.getvalue())


def dart_get(pages, asked=None):
    def get(url, params=None, timeout=None):
        if "corpCode" in url:
            return corp_reply()
        if asked is not None:
            asked.append((params["bgn_de"], params["page_no"]))
        return Reply(pages(params))
    return get


def one_filing(params):
    return {"status": "000", "total_page": 1, "list": [{"rcept_no": params["bgn_de"] + "000001", "corp_code": "C", "stock_code": STOCKS[0], "report_nm": TITLE_FIN}]}


def test_lists_are_their_own_and_only_recent_quarters_are_asked_again(tmp_path):
    asked = []
    ef.refresh_lists(tmp_path, KEY, dart_get(one_filing, asked), date(2026, 11, 8), log=lambda m: None, sleep=lambda s: None)
    assert asked[0][0] == "20240101" and len(asked) == 12 and not (tmp_path / ke.DATA).exists() and (tmp_path / ef.LISTS / "2024Q1.json.gz").exists()
    again = []
    ef.refresh_lists(tmp_path, KEY, dart_get(one_filing, again), date(2026, 11, 9), log=lambda m: None, sleep=lambda s: None)
    assert [a[0] for a in again] == ["20260701", "20261001"]


def test_an_odd_empty_answer_does_not_erase_a_stored_quarter(tmp_path):
    ef.refresh_lists(tmp_path, KEY, dart_get(one_filing), date(2026, 11, 8), log=lambda m: None, sleep=lambda s: None)
    res = ef.refresh_lists(tmp_path, KEY, dart_get(lambda p: {"status": "013"}), date(2026, 11, 9), log=lambda m: None, sleep=lambda s: None)
    assert res["stopped"] == "LIST_SHRANK"
    with gzip.open(tmp_path / ef.LISTS / "2026Q3.json.gz", "rt", encoding="utf-8") as fh:
        assert len(json.load(fh)) == 1


def run_record(run, days, get=None, when="2026-11-07", first=None):
    return kf.record(run, key="K", get=no_calls, now=lambda: at(when), first=first or days[-2], dart_key=KEY, events_get=get or dart_get(one_filing))


def test_the_record_is_separate_chained_and_written_once(tmp_path, built, monkeypatch):
    run, days = linked(tmp_path, built)
    monkeypatch.setattr(ef.time, "sleep", lambda s: None)
    res = run_record(run, days)
    assert res["status"] == "OK" and res["events"] == {"status": "OK", "written": days[-2:]} and res["fund"] == {"status": "SKIPPED"}
    idx = kf.read_index(run, ef.FOLDER)
    assert [r["late"] for r in idx] == [True, False] and kf.verify(run, ef.FOLDER)["status"] == "OK"
    assert len(kf.read_index(run)) == 2 and kf.read_index(run, kf.FUND_FOLDER) == []
    doc = kf._read_day(run / ef.FOLDER, days[-1])
    assert doc["protocol"] == ef.PROTOCOL and doc["before_next_open"] is True
    assert run_record(run, days, when="2026-11-08")["events"]["written"] == []
    for f in (run / ef.FOLDER).iterdir():
        data = gzip.open(f, "rb").read() if f.suffix == ".gz" else f.read_bytes()
        assert KEY.encode() not in data


def test_an_edited_record_fails_verification(tmp_path, built, monkeypatch):
    run, days = linked(tmp_path, built)
    monkeypatch.setattr(ef.time, "sleep", lambda s: None)
    run_record(run, days, first=days[-1])
    with gzip.open(run / ef.FOLDER / f"{days[-1]}.json.gz", "wt", encoding="utf-8") as fh:
        json.dump({"rows": []}, fh)
    assert kf.verify(run, ef.FOLDER)["status"] == "BROKEN"


def test_a_limit_keeps_the_price_record_and_writes_nothing_here(tmp_path, built, monkeypatch):
    run, days = linked(tmp_path, built)
    monkeypatch.setattr(ef.time, "sleep", lambda s: None)
    res = run_record(run, days, dart_get(lambda p: {"status": "020"}), first=days[-1])
    assert res["status"] == "FAILED" and res["events"]["reason"] == "DART_020" and res["written"] == [days[-1]] and kf.read_index(run, ef.FOLDER) == []


def test_an_error_message_cannot_carry_the_key(tmp_path, built, monkeypatch):
    run, days = linked(tmp_path, built)

    def boom(*a, **k):
        raise ConnectionError(f"failed crtfc_key={KEY}")
    monkeypatch.setattr(ef, "refresh_lists", boom)
    res = run_record(run, days, first=days[-1])
    assert res["events"]["reason"] == "ConnectionError" and KEY not in json.dumps(res)


def test_a_missing_key_is_reported_and_a_price_only_caller_touches_nothing(tmp_path, built):
    run, days = linked(tmp_path, built)
    assert ef.record(run, [days[-1]], at("2026-11-07"), None, no_calls, first=days[-1]) == {"status": "FAILED", "reason": "NO_DART_KEY", "written": []}
    assert kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=days[-1])["events"] == {"status": "SKIPPED"}


def test_status_counts_dates_and_never_a_return(tmp_path, built, monkeypatch):
    run, days = linked(tmp_path, built)
    monkeypatch.setattr(ef.time, "sleep", lambda s: None)
    run_record(run, days)
    got = ef.status(run, days)
    assert got["sessions"] == 2 and got["last"] == days[-1] and got["integrity"] == "OK" and got["ready"] is False
    assert not {"ic", "t", "top_excess", "spread_net", "return", "excess"} & set(got)


def test_evaluation_is_refused_early_and_a_second_time(tmp_path, built, monkeypatch):
    run, days = linked(tmp_path, built)
    monkeypatch.setattr(ef.time, "sleep", lambda s: None)
    run_record(run, days)
    with pytest.raises(RuntimeError, match="아직"):
        ef.evaluate_once(run, log=lambda m: None)
    assert not (run / ef.REPORT).exists()
    (run / ef.REPORT).parent.mkdir(parents=True)
    (run / ef.REPORT).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="이미"):
        ef.evaluate_once(run, log=lambda m: None)
    assert (run / ef.REPORT).read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize("verdict,b1,b2,want", [("WEAK_POSITIVE_EVIDENCE", True, True, "A_AND_B1"), ("WEAK_POSITIVE_EVIDENCE", False, True, "A_AND_B2"), ("WEAK_POSITIVE_EVIDENCE", False, False, "A_ONLY"), ("NO_EVIDENCE", True, True, "NO_EVIDENCE")])
def test_the_reading_matches_the_test(verdict, b1, b2, want):
    assert ef.reading(verdict, {"b1_buyback_beats_market": b1, "b2_avoiding_financing_helps": b2}) == want


def test_a_full_evaluation_runs_once_with_fixed_sets(tmp_path, monkeypatch):
    days = market(tmp_path / kr.DATA, "2025-01-01", "2026-11-06", seed=3)
    start = days[-262]

    def quick(base, day):       # records only need valid rows here; real scoring is tested above
        rows = []
        for n, c in enumerate(STOCKS):
            fin, buy = int(n < 10), int(n >= 40)
            rows.append({"code": c, "name": c, "board": "KOSPI", "score": float((1 - fin + buy) * 50), "financing": fin, "buyback": buy, "cap": 1.0, "traded": 1.0})
        return {"session": day, "protocol": ef.PROTOCOL, "rows": rows}
    monkeypatch.setattr(ef, "score_day", quick)
    monkeypatch.setattr(ef, "refresh_lists", lambda *a, **k: {"status": "DONE"})
    res = ef.record(tmp_path, kf.available(tmp_path / kr.DATA, start, days[-1]), at("2026-11-07"), KEY, no_calls, first=start)
    assert len(res["written"]) == 262
    out = ef.evaluate_once(tmp_path, log=lambda m: None)
    assert out["status"] == "EVALUATED" and out["dates"] == 49 and out["reading"] in ("A_AND_B1", "A_AND_B2", "A_ONLY", "NO_EVIDENCE")
    assert out["sets"]["periods"] == 13 and out["sets"]["mean_holdings"] == {"all_equal": 50.0, "no_financing": 40.0, "financing": 10.0, "buyback_clean": 10.0}
    assert "supports_avoiding" in out["low_tier"] and out["late_share"] > 0.9
    with pytest.raises(RuntimeError, match="이미"):
        ef.evaluate_once(tmp_path, log=lambda m: None)


def test_the_record_is_backed_up():
    from terminal import automation
    assert "research_data/krx_forward_events/index.jsonl" in automation.BACKUP_GLOBS
