"""Price-history check: Korean bars against KRX daily snapshots, US bars against the NYSE calendar.  Read only."""
import gzip
import json
from datetime import date, datetime, timedelta, timezone

from terminal.qsf import price_audit as pa

NOW = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)
DAYS = ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-11-02"]


def krx_row(code, close, rate, value=1_000_000):
    return [code, "이름", "", str(close), str(close), str(close), str(close), f"{rate:.2f}", "100", str(value), "0", "0"]


def write_krx(base, by_day):
    for day, rows in by_day.items():
        for board in pa.BOARDS:
            p = base / pa.KRX / board / f"{day}.json.gz"
            p.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(p, "wt", encoding="utf-8") as fh:
                json.dump(rows if board == "KOSDAQ" else [], fh)


def bar(day, close, **kw):
    return {"date": day, "open": kw.get("open", close), "high": kw.get("high", close), "low": kw.get("low", close), "close": close, "adj_close": close, "volume": kw.get("volume", 1000.0)}


def krx_series(code, closes, start=0):
    out, prev = {}, None
    for day, c in zip(DAYS[start:], closes):
        out[day] = krx_row(code, c, 0.0 if prev is None else (c / prev - 1) * 100)
        prev = c
    return out


def build_case(tmp_path):
    closes = [1000, 1010, 1030, 1020, 1050, 1100]
    series = {
        "000001": krx_series("000001", closes),                       # clean
        "000002": krx_series("000002", closes),                       # Yahoo repeats 10-28 then catches up on 10-29
        "000003": krx_series("000003", closes),                       # Yahoo has no 10-29
        "000004": krx_series("000004", closes[2:], start=2),          # listed on 10-28; Yahoo has two earlier days
    }
    by_day = {d: [series[c][d] for c in series if d in series[c]] for d in DAYS}
    write_krx(tmp_path, by_day)
    clean = [bar(d, c) for d, c in zip(DAYS, closes)]
    stale = [bar(d, c) for d, c in zip(DAYS, [1000, 1010, 1010, 1020, 1050, 1100])]
    missing = [b for b in clean if b["date"] != "2026-10-29"]
    pre = [bar("2026-10-26", 400), bar("2026-10-27", 420)] + [bar(d, c) for d, c in zip(DAYS[2:], closes[2:])]
    bars = {"000001": clean, "000002": stale, "000003": missing, "000004": pre}
    (tmp_path / pa.FOLDER).mkdir(parents=True, exist_ok=True)
    with gzip.open(tmp_path / pa.FOLDER / "bars_KR.json.gz", "wt", encoding="utf-8") as fh:
        json.dump(bars, fh)


def test_korean_history_kinds(tmp_path):
    build_case(tmp_path)
    res = pa.audit_kr(tmp_path, NOW)
    s = res["stocks"]
    assert s["000001"]["level"] == "ok" and s["000001"]["counts"] == {}
    assert s["000002"]["counts"] == {"stale": 1, "wrong": 1} and s["000002"]["examples"][0] == {"kind": "stale", "date": "2026-10-28", "krx_pct": 1.98}
    assert s["000003"]["counts"] == {"missing": 1} and s["000003"]["level"] == "warn"          # the two-day step itself is not called wrong
    assert s["000004"]["counts"] == {"pre_listing": 2} and s["000004"]["level"] == "bad"
    assert res["checked"] == 4 and res["flagged"] == 3 and res["bad"] == 1 and res["session"] == "2026-11-02"


def test_a_big_one_day_difference_is_serious(tmp_path):
    krx = {d: {"000009": krx_row("000009", 100, 0.0)} for d in DAYS[:2]}
    krx[DAYS[1]]["000009"] = krx_row("000009", 100, 0.0)
    got = pa.audit_kr_stock([bar(DAYS[0], 100), bar(DAYS[1], 160)], "000009", krx, DAYS[:2])
    assert got["counts"] == {"wrong": 1} and got["level"] == "bad" and got["largest_gap_pct"] == 60.0


def test_half_day_of_krx_files_is_not_a_day(tmp_path):
    build_case(tmp_path)
    (tmp_path / pa.KRX / "KOSPI" / "2026-11-02.json.gz").unlink()
    assert "2026-11-02" not in pa.krx_days(tmp_path / pa.KRX, "2026-10-01")


def test_us_internal_checks_and_provisional_last_bar():
    sessions = ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"]
    rows = [bar("2026-10-26", 10), bar("2026-10-27", 11, high=10.5),           # high below the close
            bar("2026-10-28", 11, high=10.5), bar("2026-10-30", 12, open=11.5, low=11.8, volume=0)]
    got = pa.audit_us_stock(rows, sessions)
    assert got["counts"] == {"bad_range": 2, "repeated": 1, "missing_session": 1, "zero_volume": 1}      # 10-28 repeats a bar that was already bad
    assert got["level"] == "bad" and got["last_bar_provisional"] is True              # the last bar's range is reported apart
    assert pa.audit_us_stock([bar(d, 10 + i) for i, d in enumerate(sessions)], sessions)["level"] == "ok"


def test_save_writes_latest_and_one_log_line_per_session(tmp_path):
    build_case(tmp_path)
    res = pa.audit_kr(tmp_path, NOW)
    pa.save(tmp_path, res)
    pa.save(tmp_path, res)
    log = (tmp_path / pa.FOLDER / "price_audit_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1 and json.loads(log[0])["flagged"] == 3 and "stocks" not in json.loads(log[0])
    one = pa.for_stock(tmp_path, "KR", "000002")
    assert one["level"] == "warn" and "전날 종가가 그대로" in one["text"] and one["session"] == "2026-11-02"
    assert pa.for_stock(tmp_path, "KR", "000001")["text"].endswith("문제를 찾지 못했습니다.")
    assert pa.for_stock(tmp_path, "KR", "999999") is None and pa.for_stock(tmp_path, "US", "AAPL") is None
    assert "stocks" not in pa.summary_view(tmp_path)["KR"] and pa.summary_view(tmp_path)["US"] == {"status": "UNAVAILABLE"}


def test_run_without_inputs_reports_unavailable(tmp_path):
    def sessions_between(a, b):
        return [a + timedelta(days=i) for i in range((b - a).days + 1)]
    got = pa.run(tmp_path, sessions_between, NOW)
    assert got["US"]["status"] == "UNAVAILABLE" and got["KR"]["status"] == "UNAVAILABLE"
    assert not (tmp_path / pa.FOLDER / "price_audit_log.jsonl").exists()


def test_us_audit_reads_the_newest_scan_session(tmp_path):
    root = tmp_path / pa.FOLDER / "cache"
    root.mkdir(parents=True)
    old = {"data": {"AAA": [bar("2026-10-29", 9)]}}
    new = {"data": {"AAA": [bar("2026-10-29", 10), bar("2026-10-30", 11)]}}
    (root / "scanbars_2026-10-29_0123456789abcdef_0123456789.json").write_text(json.dumps(old))
    (root / "scanbars_2026-10-30_0123456789abcdef_0123456789.json").write_text(json.dumps(new))
    got = pa.audit_us(tmp_path, lambda a, b: [date(2026, 10, 29), date(2026, 10, 30)], NOW)
    assert got["session"] == "2026-10-30" and got["stocks"]["AAA"]["level"] == "ok"


def test_ranking_rows_flag_only_a_check_of_the_same_scan(tmp_path):
    from terminal.qsf.service import QSF as QsfService
    build_case(tmp_path)
    pa.save(tmp_path, pa.audit_kr(tmp_path, NOW))
    rows = [{"ticker": "000002", "strategy": "SWING"}, {"ticker": "000001", "strategy": "SWING"}]
    (tmp_path / pa.FOLDER / "latest_KR.json").write_text(json.dumps({"status": "REAL", "session": "2026-11-02", "rows": rows}))
    svc = QsfService.__new__(QsfService)
    svc.base, svc.dir = tmp_path, tmp_path / pa.FOLDER
    svc._high_risk = lambda m: {"codes": set(), "ranked": set()}
    svc._filing_marks = lambda m: {"session": None, "known": set()}
    svc._filing_mark = lambda f, t: None
    got = svc.latest("KR")["rows"]
    assert got[0]["price_audit"]["level"] == "warn" and "price_audit" not in got[1]
    (tmp_path / pa.FOLDER / "latest_KR.json").write_text(json.dumps({"status": "REAL", "session": "2026-11-03", "rows": rows}))
    assert all("price_audit" not in r for r in svc.latest("KR")["rows"])


def test_record_alert_words():
    from terminal import record_status
    audits = {"US": {"status": "REAL", "flagged": 0}, "KR": {"status": "REAL", "session": "2026-11-06", "checked": 300, "flagged": 102, "bad": 14,
                                                               "by_kind": {"stale": 42}, "kind_text": {"stale": pa.KIND_TEXT["stale"]}}}
    got = record_status.audit_alerts(audits)
    assert len(got) == 1 and got[0]["level"] == "bad" and "300종목 중 102종목" in got[0]["text"] and "고치지 않았습니다" in got[0]["text"]
