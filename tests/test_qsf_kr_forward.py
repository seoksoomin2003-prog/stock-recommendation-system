"""The separate Korean record: written once, no look-ahead, no early evaluation, no key on disk.  No network."""
import gzip
import json
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from terminal.qsf import krx_history as kh, kr_forward as kf, research_kr as kr

STOCKS = [f"{n:05d}0" for n in range(10, 60)]


def _rows(rng, level, day_index):
    out = []
    for code in STOCKS:
        chg = float(rng.normal(0, 2))
        level[code] *= 1 + chg / 100
        c = level[code]
        out.append([code, f"회사{code}", "중견기업부", str(c), str(c * 1.01), str(c * 0.99), str(c), str(chg), "1000", "5000000000", "100000000000", "100"])
    return out


def _write(root, board, day, rows):
    p = kh.path_of(root, board, day)
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump(rows, fh)


def market(root, first, last, seed=1):
    rng = np.random.default_rng(seed)
    level = {c: 1000.0 for c in STOCKS}
    days = list(kh.weekdays(first, last))
    for n, day in enumerate(days):
        rows = _rows(rng, level, n)
        _write(root, "KOSPI", day, rows[:25])
        _write(root, "KOSDAQ", day, rows[25:])
    return days


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    base = tmp_path_factory.mktemp("kr")
    days = market(base / kr.DATA, "2025-06-02", "2026-11-06")
    return base, days


class Resp:
    def __init__(self, code=200, rows=None):
        self.status_code, self._rows = code, rows

    def json(self):
        return {"OutBlock_1": self._rows or []}


def no_calls(*a, **k):
    raise AssertionError("no request expected")


def at(day, hour=12):
    return datetime(*date.fromisoformat(day).timetuple()[:3], hour, tzinfo=kf.KST)


def test_a_score_reads_nothing_after_its_day(tmp_path, built):
    base, days = built
    day = days[-5]
    before = kf.score_day(base / kr.DATA, day)
    trimmed = tmp_path / "krx"
    for d in days:
        if d <= day:
            for b in kh.BOARDS:
                t = kh.path_of(trimmed, b, d)
                t.parent.mkdir(parents=True, exist_ok=True)
                t.write_bytes(kh.path_of(base / kr.DATA, b, d).read_bytes())
    assert kf.score_day(trimmed, day)["rows"] == before["rows"]
    assert len(before["rows"]) == 50 and all(r["score"] is not None for r in before["rows"])


def test_windowed_prices_score_like_the_full_history(built):
    base, days = built
    z = kr.build_prices(base / kr.DATA, log=lambda m: None)
    i = len(z["dates"]) - 1
    ok = kr.eligible(z, i)
    f = kf.rs.price_features(z, i, list(z["symbols"]).index(kr.MARKET))
    t = np.full((1, len(z["symbols"]), len(kr.SIGNALS)), np.nan, dtype=np.float32)
    for k, s in enumerate(kr.SIGNALS):
        t[0, ok, k] = f[s][ok]
    full = kf.en.combine(kr.theme_ranks(t), kf.GROUPS)[0]
    got = {r["code"]: r["score"] for r in kf.score_day(base / kr.DATA, days[-1])["rows"]}
    assert len(got) == ok.sum()
    assert all(abs(got[str(z["symbols"][j])] - float(full[j])) < 0.01 for j in np.flatnonzero(ok))


def test_a_record_is_written_once_and_chained(tmp_path, built):
    base, days = built
    run = tmp_path / "run"
    (run / kr.DATA.parent).mkdir(parents=True)
    (run / kr.DATA).symlink_to(base / kr.DATA)
    now = lambda: at("2026-11-07")     # noqa: E731
    res = kf.record(run, key="SECRET", get=no_calls, now=now, first=days[-2])
    assert res["status"] == "OK" and res["written"] == days[-2:] and res["last"] == days[-1]
    idx = kf.read_index(run)
    assert [r["late"] for r in idx] == [True, False]       # the first already had a later session beside it
    assert idx[0]["chain"] != idx[1]["chain"]
    first_bytes = (run / kf.FOLDER / f"{days[-1]}.json.gz").read_bytes()
    again = kf.record(run, key="SECRET", get=no_calls, now=lambda: at("2026-11-08"), first=days[-2])
    assert again["written"] == [] and (run / kf.FOLDER / f"{days[-1]}.json.gz").read_bytes() == first_bytes
    assert kf.verify(run)["status"] == "OK"
    assert all(b"SECRET" not in p.read_bytes() for p in (run / kf.FOLDER).iterdir())


def test_an_edited_record_fails_verification(tmp_path, built):
    base, days = built
    run = tmp_path / "run"
    (run / kr.DATA.parent).mkdir(parents=True)
    (run / kr.DATA).symlink_to(base / kr.DATA)
    kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=days[-1])
    p = run / kf.FOLDER / f"{days[-1]}.json.gz"
    p.write_bytes(p.read_bytes() + b"x")
    assert kf.verify(run) == {"status": "BROKEN", "sessions": 1, "bad": [days[-1]]}


def test_a_crash_before_the_index_line_is_recovered_without_rewriting(tmp_path, built):
    base, days = built
    run = tmp_path / "run"
    (run / kr.DATA.parent).mkdir(parents=True)
    (run / kr.DATA).symlink_to(base / kr.DATA)
    kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=days[-1])
    p = run / kf.FOLDER / f"{days[-1]}.json.gz"
    (run / kf.FOLDER / "index.jsonl").unlink()
    before = p.read_bytes()
    assert kf.write_record(run, days[-1], at("2026-11-09"), True)
    assert p.read_bytes() == before and kf.read_index(run)[0]["recorded_at"] == at("2026-11-07").isoformat()


def test_an_unpublished_day_is_not_stored_as_a_holiday(tmp_path):
    res = kf.record(tmp_path, key="K", get=lambda *a, **k: Resp(200, []), now=lambda: at("2026-11-07"), first="2026-11-05", sleep=lambda s: None)
    assert res["status"] == "WAITING" and res["last"] is None
    assert not kh.path_of(tmp_path / kr.DATA, "KOSPI", "2026-11-06").exists()


def test_an_old_empty_day_is_still_stored_so_it_is_not_asked_forever(tmp_path):
    kf.record(tmp_path, key="K", get=lambda *a, **k: Resp(200, []), now=lambda: at("2026-11-20"), first="2026-11-05", sleep=lambda s: None)
    assert kh.path_of(tmp_path / kr.DATA, "KOSPI", "2026-11-05").exists()
    assert not kh.path_of(tmp_path / kr.DATA, "KOSPI", "2026-11-19").exists()


def test_half_a_day_is_not_a_day(tmp_path):
    _write(tmp_path, "KOSPI", "2026-11-06", [["000010"]])
    assert kf.available(tmp_path, "2026-11-06", "2026-11-06") == []
    _write(tmp_path, "KOSDAQ", "2026-11-06", [])
    assert kf.available(tmp_path, "2026-11-06", "2026-11-06") == []


def test_a_refusal_and_a_missing_key_are_reported(tmp_path, monkeypatch):
    res = kf.record(tmp_path, key="K", get=lambda *a, **k: Resp(403), now=lambda: at("2026-11-07"), first="2026-11-06")
    assert res["status"] == "FAILED" and res["stopped"] == "REFUSED_403"
    monkeypatch.delenv("KRX_API_KEY", raising=False)
    assert kf.record(tmp_path, get=no_calls, now=lambda: at("2026-11-07"))["status"] == "NO_KEY"


def test_the_next_open_flag():
    assert kf.next_open("2026-11-06") == at("2026-11-09", 9)     # Friday to Monday
    assert at("2026-11-09", 8) < kf.next_open("2026-11-06") <= at("2026-11-09", 9)


def test_status_counts_dates_and_never_a_return(tmp_path, built):
    base, days = built
    run = tmp_path / "run"
    (run / kr.DATA.parent).mkdir(parents=True)
    (run / kr.DATA).symlink_to(base / kr.DATA)
    kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=days[-1])
    s = kf.status(run, days[-30:])
    assert s["sessions"] == 1 and s["behind_sessions"] == 0 and s["matured"] == 0 and not s["ready"] and s["integrity"] == "OK"
    assert s["remaining_sessions"] == 239 + 20
    assert not any("return" in k or "ic" == k for k in s)
    assert kf.status(run, None)["behind_sessions"] is None
    empty = kf.status(tmp_path, None)
    assert empty["sessions"] == 0 and empty["last"] is None


def test_evaluation_is_refused_early(tmp_path, built):
    base, days = built
    run = tmp_path / "run"
    (run / kr.DATA.parent).mkdir(parents=True)
    (run / kr.DATA).symlink_to(base / kr.DATA)
    kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=days[-1])
    with pytest.raises(RuntimeError, match="아직"):
        kf.evaluate_once(run, log=lambda m: None)
    assert not (run / kf.REPORT).exists()


def test_evaluation_refuses_a_broken_record_and_a_second_run(tmp_path, built):
    base, days = built
    with pytest.raises(RuntimeError):
        kf.evaluate_once(tmp_path, log=lambda m: None)
    p = tmp_path / kf.REPORT
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    with pytest.raises(RuntimeError, match="이미"):
        kf.evaluate_once(tmp_path, log=lambda m: None)


def test_a_full_evaluation_runs_once_on_enough_sessions(tmp_path, monkeypatch):
    days = market(tmp_path / kr.DATA, "2025-01-01", "2026-11-06", seed=3)
    start = days[-262]
    original = kf.score_day

    def quick(root, day):       # records only need valid rows here; real scoring is tested above
        rng = np.random.default_rng(int(day.replace("-", "")))
        return {"session": day, "protocol": kf.PROTOCOL, "groups": kf.GROUPS, "rows": [{"code": c, "name": c, "board": "KOSPI", "score": float(rng.random() * 100), "momentum": 1.0, "reversal": 1.0, "low_risk": float(rng.random() * 100), "cap": 1.0, "value": 1.0} for c in STOCKS]}
    monkeypatch.setattr(kf, "score_day", quick)
    res = kf.record(tmp_path, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=start)
    assert len(res["written"]) == 262
    out = kf.evaluate_once(tmp_path, log=lambda m: None)
    assert out["status"] == "EVALUATED" and out["dates"] == 49 and out["verdict"] in ("NO_EVIDENCE", "WEAK_POSITIVE_EVIDENCE")
    assert out["top_vs_market"]["periods"] == 13 and "supports_exclusion" in out["low_risk_bottom_fifth"]
    assert out["late_share"] > 0.9
    with pytest.raises(RuntimeError, match="이미"):
        kf.evaluate_once(tmp_path, log=lambda m: None)
    assert original is not quick


def _live(base, day, rows):
    p = base / "data" / "qsf" / "latest_KR.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"session": day, "rows": rows}), encoding="utf-8")


def test_live_prices_are_compared_with_the_krx_close_once_a_session(tmp_path):
    day = "2026-11-06"
    row = ["000010", "회사", "", "100", "100", "100", "1,000", "0", "1", "1", "1", "1"]
    _write(tmp_path / kr.DATA, "KOSPI", day, [row, ["000020"] + row[1:6] + ["2000"] + row[7:]])
    _write(tmp_path / kr.DATA, "KOSDAQ", day, [["000030"] + row[1:]])
    assert kf.cross_check(tmp_path) is None                    # no live scan yet
    _live(tmp_path, day, [{"ticker": "000010", "price": 1000.0, "data_date": day}, {"ticker": "000010", "price": 1000.0, "data_date": day}, {"ticker": "000020", "price": 2200.0, "data_date": day},
                          {"ticker": "000030", "price": 1000.0, "data_date": "2026-11-05"}, {"ticker": "999990", "price": 5.0, "data_date": day}])
    out = kf.cross_check(tmp_path)
    assert (out["checked"], out["gaps"], out["stale"], out["absent"]) == (4, 1, 1, 1) and out["examples"][0]["ticker"] == "000020"
    assert kf.cross_check(tmp_path) is None and kf.last_check(tmp_path)["session"] == day


def test_a_scan_from_a_day_without_krx_data_is_not_checked(tmp_path):
    _live(tmp_path, "2026-11-06", [{"ticker": "000010", "price": 1.0, "data_date": "2026-11-06"}])
    assert kf.cross_check(tmp_path) is None and kf.last_check(tmp_path) is None


def _fund_run(tmp_path, built, monkeypatch):
    base, days = built
    run = tmp_path / "run"
    (run / kr.DATA.parent).mkdir(parents=True)
    (run / kr.DATA).symlink_to(base / kr.DATA)
    def scored(b, day):
        return {"session": day, "protocol": kf.PROTOCOL, "groups": kf.FUND_GROUPS, "rows": [{"code": c, "score": 50.0} for c in STOCKS]}
    monkeypatch.setattr(kf, "score_fund_day", scored)
    monkeypatch.setattr(kf, "refresh_dart", lambda *a, **k: {"status": "DONE", "stopped": None})
    return run, days


def test_the_financial_record_is_separate_and_written_once(tmp_path, built, monkeypatch):
    run, days = _fund_run(tmp_path, built, monkeypatch)
    res = kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=days[-2], dart_key="D", dart_get=no_calls)
    assert res["status"] == "OK" and res["fund"] == {"status": "OK", "written": days[-2:]}
    idx = kf.read_index(run, kf.FUND_FOLDER)
    assert [r["late"] for r in idx] == [True, False] and kf.verify(run, kf.FUND_FOLDER)["status"] == "OK"
    assert len(kf.read_index(run)) == 2                 # the price record has its own chain
    assert kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-08"), first=days[-2], dart_key="D", dart_get=no_calls)["fund"]["written"] == []


def test_a_dart_failure_keeps_the_price_record_and_is_reported(tmp_path, built, monkeypatch):
    run, days = _fund_run(tmp_path, built, monkeypatch)
    monkeypatch.setattr(kf, "refresh_dart", lambda *a, **k: {"status": "STOPPED", "stopped": "DART_020"})
    res = kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=days[-1], dart_key="D", dart_get=no_calls)
    assert res["status"] == "FAILED" and res["fund"]["reason"] == "DART_020" and res["written"] == [days[-1]]
    assert kf.read_index(run, kf.FUND_FOLDER) == []


def test_an_error_message_cannot_carry_the_dart_key(tmp_path, built, monkeypatch):
    run, days = _fund_run(tmp_path, built, monkeypatch)
    def boom(*a, **k):
        raise ConnectionError("failed crtfc_key=SECRET")
    monkeypatch.setattr(kf, "refresh_dart", boom)
    res = kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=days[-1], dart_key="SECRET", dart_get=no_calls)
    assert res["fund"]["reason"] == "ConnectionError" and "SECRET" not in json.dumps(res)


def test_a_price_only_caller_does_not_touch_dart(tmp_path, built):
    base, days = built
    run = tmp_path / "run"
    (run / kr.DATA.parent).mkdir(parents=True)
    (run / kr.DATA).symlink_to(base / kr.DATA)
    assert kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=days[-1])["fund"] == {"status": "SKIPPED"}


def test_the_riskiest_fifth_is_marked_and_nothing_without_a_record(tmp_path, built):
    assert kf.high_risk(tmp_path) == {"session": None, "codes": []}
    base, days = built
    run = tmp_path / "run"
    (run / kr.DATA.parent).mkdir(parents=True)
    (run / kr.DATA).symlink_to(base / kr.DATA)
    kf.record(run, key="K", get=no_calls, now=lambda: at("2026-11-07"), first=days[-1])
    found = kf.high_risk(run)
    assert found["session"] == days[-1] and len(found["codes"]) == 10
    doc = kf._read_day(run / kf.FOLDER, days[-1])["rows"]
    low = {r["code"]: r["low_risk"] for r in doc}
    assert max(low[c] for c in found["codes"]) <= min(v for c, v in low.items() if c not in found["codes"])


def test_the_real_financial_score_reads_only_receipts_before_the_day(tmp_path, built):
    base, days = built
    run = tmp_path / "run"
    (run / kr.DATA.parent).mkdir(parents=True)
    (run / kr.DATA).symlink_to(base / kr.DATA)
    day = days[-1]
    def put(year, report, receipt, stock_rows):
        p = run / kf.DART_FORWARD / f"{year}_{report}" / "000.json.gz"
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            json.dump(stock_rows, fh, ensure_ascii=False)
    def rows(receipt, scale):
        out = []
        for n, code in enumerate(STOCKS):
            for acct, v in (("자산총계", 1000 + n), ("부채총계", 400), ("자본총계", 600 + n), ("유동자산", 300), ("유동부채", 100), ("매출액", (500 + n) * scale), ("영업이익", (50 + n) * scale), ("당기순이익(손실)", (30 + n) * scale)):
                out.append([receipt, "C" + code, code, "CFS", "BS", acct, "", str(v), ""])
        return out
    put(2024, "FY", "x", rows("20250320000001", 1))
    put(2025, "FY", "x", rows("20260320000001", 2))
    first = kf.score_fund_day(run, day)
    assert sum(r["score"] is not None for r in first["rows"]) == 50
    put(2026, "FY", "x", rows(day.replace("-", "") + "000001", 50))       # received on the day itself
    assert kf.score_fund_day(run, day)["rows"] == first["rows"]
