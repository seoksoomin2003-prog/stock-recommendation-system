"""Screener: filters narrow as they say, a missing value is never 0, bad input is refused, nothing is written."""
import copy

import pytest

from terminal.qsf import screen as sc


def row(t, score=60.0, action="WATCH", strategy="SWING", tech=50.0, fund=50.0, risk=50.0, events=50.0, actionability="ACTIONABLE", entry="ENTRY_NOW", conf="HIGH", name=None, **extra):
    return {"ticker": t, "name": name or f"{t} Inc", "strategy": strategy, "score": score, "action": action, "actionability": actionability, "entry_status": entry, "confidence": conf, "price": 10.0, "coverage": 0.9,
            "domains": {"TECHNICAL": tech, "FUNDAMENTAL": fund, "RISK": risk, "EVENTS": events, "REGIME": 30.0}, "gates": [], **extra}


def latest(*rows):
    return {"status": "REAL", "market": "KR", "session": "2026-11-06", "model_version": "QSF-1.1.7", "generated_at": "2026-11-07T00:00:00", "rows": list(rows)}


def tickers(out):
    return [r["ticker"] for r in out["rows"]]


def test_only_the_asked_strategy_counts_and_score_sorts_by_default():
    out = sc.screen(latest(row("A", 50), row("B", 80), row("C", 90, strategy="LONG_TERM")), {})
    assert tickers(out) == ["B", "A"] and out["total"] == 2 and out["matched"] == 2 and out["strategy"] == "SWING"
    assert tickers(sc.screen(latest(row("A", 50), row("C", 90, strategy="LONG_TERM")), {"strategy": "LONG_TERM"})) == ["C"]


def test_filters_narrow():
    data = latest(row("BUY1", 80, "BUY"), row("WAT", 60, "WATCH"), row("BLK", 85, "BUY", actionability="BLOCKED"), row("WAIT", 75, "BUY", entry="WAIT_FOR_PULLBACK"), row("LOWC", 72, "BUY", conf="LOW"))
    assert tickers(sc.screen(data, {"action": "BUY"})) == ["BLK", "BUY1", "WAIT", "LOWC"]
    assert tickers(sc.screen(data, {"action": "BUY,WATCH", "actionable": "1", "entry": "ENTRY_NOW"})) == ["BUY1", "LOWC", "WAT"]
    assert tickers(sc.screen(data, {"confidence": "HIGH", "min_score": "70", "entry": "ENTRY_NOW"})) == ["BLK", "BUY1"]


def test_text_matches_code_or_name_without_case():
    data = latest(row("005930", name="삼성전자"), row("AAPL", name="Apple Inc"))
    assert tickers(sc.screen(data, {"q": "삼성"})) == ["005930"] and tickers(sc.screen(data, {"q": "apple"})) == ["AAPL"] and tickers(sc.screen(data, {"q": "0059"})) == ["005930"]


def test_a_missing_value_is_left_out_and_counted_never_zero():
    data = latest(row("HAS", fund=70.0), row("LOW", fund=10.0), row("NONE", fund=None))
    out = sc.screen(data, {"min_fundamental": "50"})
    assert tickers(out) == ["HAS"] and out["missing_value"] == 1 and out["matched"] == 1
    assert sc.screen(data, {"min_fundamental": "0"})["missing_value"] == 1 and "NONE" not in tickers(sc.screen(data, {"min_fundamental": "0"}))


def test_sorting_keeps_a_missing_value_at_the_bottom_both_ways():
    data = latest(row("A", fund=70.0), row("B", fund=None), row("C", fund=20.0))
    assert tickers(sc.screen(data, {"sort": "fundamental"})) == ["A", "C", "B"]
    assert tickers(sc.screen(data, {"sort": "fundamental", "order": "asc"})) == ["C", "A", "B"]


def test_ties_do_not_depend_on_file_order():
    assert tickers(sc.screen(latest(row("B", 60), row("A", 60)), {"order": "asc"})) == ["A", "B"]


def test_filing_and_risk_marks_filter():
    data = latest(row("FIN", filing_events={"financing": True, "buyback": False}), row("BUY", filing_events={"financing": False, "buyback": True}), row("RISK", high_risk={"session": "x"}), row("PLAIN"))
    assert set(tickers(sc.screen(data, {"no_financing": "1"}))) == {"BUY", "RISK", "PLAIN"}
    assert tickers(sc.screen(data, {"buyback": "1"})) == ["BUY"]
    assert set(tickers(sc.screen(data, {"no_high_risk": "1"}))) == {"FIN", "BUY", "PLAIN"}


def test_a_stock_not_on_the_filing_record_is_unknown_not_clean():
    data = latest(row("CLEAN"), row("NEW", filing_unknown=True))
    out = sc.screen(data, {"no_financing": "1"})
    assert tickers(out) == ["CLEAN"] and out["missing_value"] == 1
    assert sc.screen(data, {"buyback": "1"})["missing_value"] == 1
    assert set(tickers(sc.screen(data, {}))) == {"CLEAN", "NEW"}


def test_unknown_risk_is_missing_not_low():
    data = latest(row("LOW"), row("HIGH", high_risk={"session": "x"}), row("UNK", high_risk_unknown=True))
    out = sc.screen(data, {"no_high_risk": "1"})
    assert tickers(out) == ["LOW"] and out["missing_value"] == 1
    assert set(tickers(sc.screen(data, {}))) == {"LOW", "HIGH", "UNK"}


def test_a_known_no_buyback_is_a_plain_no_even_without_a_sector():
    data = latest(row("NOSEC", filing_events={"financing": False, "buyback": False}), row("UNK", filing_unknown=True), row("YES", sector="Tech", filing_events={"financing": False, "buyback": True}))
    out = sc.screen(data, {"sector": "Tech", "buyback": "1"})
    assert tickers(out) == ["YES"] and out["missing_value"] == 1      # only UNK is unknown; NOSEC is known to have none


def test_sector_filter_counts_and_missing():
    data = latest(row("T1", sector="Technology"), row("T2", sector="Technology"), row("F1", 90, sector="Energy"), row("N"))
    all_ = sc.screen(data, {})
    assert all_["sectors"] == {"Technology": 2, "Energy": 1} and all_["matched_sectors"] == all_["sectors"]
    out = sc.screen(data, {"sector": "Technology"})
    assert set(tickers(out)) == {"T1", "T2"} and out["missing_value"] == 1 and out["sectors"]["Energy"] == 1 and out["matched_sectors"] == {"Technology": 2}
    assert sc.screen(data, {"sector": "Nothing"})["matched"] == 0


def test_sectors_come_from_what_is_stored_and_never_the_network(tmp_path):
    import json

    from terminal.cache import FileCache
    from terminal.qsf.service import QSF
    svc = QSF.__new__(QSF)
    svc.base, svc.dir, svc.cache, svc._sector_memo = tmp_path, tmp_path, FileCache(tmp_path / "cache"), {}
    svc.cache.write("info:005930.KS", {"sector": "Technology"})
    svc.cache.write("info:035720.KQ", {"sector": "Communication Services"})
    svc.cache.write("info:000000.KS", {"longName": "x"})
    (tmp_path / "latest_KR.json").write_text(json.dumps({"status": "REAL", "generated_at": "a", "rows": [{"ticker": "005930"}, {"ticker": "035720"}, {"ticker": "000000"}, {"ticker": "111111"}]}), encoding="utf-8")
    before = (tmp_path / "latest_KR.json").read_bytes()
    svc._high_risk = lambda m: {"session": None, "codes": set()}
    svc._filing_marks = lambda m: {"session": None, "financing": set(), "buyback": set(), "known": set()}
    assert [r["sector"] for r in svc.screen_rows("KR")["rows"]] == ["Technology", "Communication Services", None, None]
    assert (tmp_path / "latest_KR.json").read_bytes() == before


def test_with_no_filing_or_risk_record_every_stock_is_unknown(tmp_path):
    import json

    from terminal.cache import FileCache
    from terminal.qsf.service import QSF
    svc = QSF.__new__(QSF)
    svc.base, svc.dir, svc.cache = tmp_path, tmp_path, FileCache(tmp_path / "cache")
    (tmp_path / "latest_KR.json").write_text(json.dumps({"status": "REAL", "rows": [{"ticker": "A", "strategy": "SWING", "score": 60.0}, {"ticker": "B", "strategy": "SWING", "score": 50.0}]}), encoding="utf-8")
    svc._high_risk = lambda m: {"session": None, "codes": set(), "ranked": set()}
    svc._filing_marks = lambda m: {"session": None, "financing": set(), "buyback": set(), "known": set()}
    got = svc.latest("KR")
    for flag in ("no_financing", "buyback", "no_high_risk"):
        out = sc.screen(got, {flag: "1"})
        assert out["matched"] == 0 and out["missing_value"] == 2, flag
    svc._high_risk = lambda m: {"session": "d", "codes": {"B"}, "ranked": {"A", "B"}}
    svc._filing_marks = lambda m: {"session": "d", "financing": {"B"}, "buyback": set(), "known": {"A", "B"}}
    got = svc.latest("KR")
    assert tickers(sc.screen(got, {"no_high_risk": "1"})) == ["A"] and tickers(sc.screen(got, {"no_financing": "1"})) == ["A"]


def test_paging():
    data = latest(*[row(f"S{i:02d}", 90 - i) for i in range(30)])
    out = sc.screen(data, {"limit": "10", "offset": "25"})
    assert tickers(out) == [f"S{i:02d}" for i in range(25, 30)] and out["matched"] == 30


@pytest.mark.parametrize("bad", [{"strategy": "DAY"}, {"action": "BUY,NOPE"}, {"entry": "X"}, {"confidence": "SURE"}, {"sort": "__class__"}, {"order": "up"}, {"min_score": "101"}, {"min_technical": "abc"}, {"min_risk": "nan"}, {"limit": "0"}, {"limit": "99999"}, {"offset": "-1"}, {"actionable": "yes"}, {"no_financing": "2"}])
def test_bad_input_is_refused(bad):
    with pytest.raises(ValueError):
        sc.screen(latest(row("A")), bad)


def test_no_scan_is_not_an_empty_success():
    out = sc.screen({"status": "UNAVAILABLE", "rows": [], "reason": "아직 스캔 기록이 없습니다."}, {})
    assert out["status"] == "UNAVAILABLE" and out["rows"] == [] and out["reason"]


def test_a_broken_number_is_treated_as_missing():
    data = latest(row("OK", 60.0), row("NAN", float("nan")), row("TXT", "x"), row("TRUE", True))
    out = sc.screen(data, {"min_score": "10"})
    assert tickers(out) == ["OK"] and out["missing_value"] == 3


def test_the_scan_given_is_left_as_it_was():
    data = latest(row("A", 50), row("B", 80))
    before = copy.deepcopy(data)
    sc.screen(data, {"min_score": "60", "sort": "technical", "order": "asc"})
    assert data == before


def test_the_route_serves_the_scan_and_passes_bad_input_up_as_a_refusal():
    from terminal.server import routes

    class Qsf:
        def screen_rows(self, market):
            assert market == "KR"
            return latest(row("A", 80), row("B", 40))

    class T:
        qsf = Qsf()
    fn = routes(T())[("GET", "/api/qsf/screen")]
    assert tickers(fn({"market": "KR", "min_score": "50"}, {})) == ["A"]
    with pytest.raises(ValueError):      # the server turns this into a 400
        fn({"market": "KR", "sort": "nope"}, {})


def test_korea_uses_the_exchange_industry_when_a_master_is_stored(tmp_path):
    import json

    import pandas as pd

    from terminal.cache import FileCache
    from terminal.qsf.service import QSF
    svc = QSF.__new__(QSF)
    svc.base, svc.dir, svc.cache, svc._sector_memo = tmp_path, tmp_path, FileCache(tmp_path / "cache"), {}
    sdir = tmp_path / "data" / "kr" / "security_master"
    sdir.mkdir(parents=True)
    pd.DataFrame({"canonical_ticker": ["005930", "035720", "000000"], "industry": ["반도체 제조업", "자료처리업", None]}).to_csv(sdir / "m.csv.gz", index=False, compression="gzip")
    (sdir / "LATEST.json").write_text(json.dumps({"file": "m.csv.gz", "retrieved_at": "2020-01-01T00:00:00+00:00"}), encoding="utf-8")
    svc.cache.write("info:000000.KS", {"sector": "Technology"})          # a Yahoo sector is never mixed in
    (tmp_path / "latest_KR.json").write_text(json.dumps({"status": "REAL", "generated_at": "a", "rows": [{"ticker": "005930"}, {"ticker": "035720"}, {"ticker": "000000"}]}), encoding="utf-8")
    svc._high_risk = lambda m: {"session": None, "codes": set()}
    svc._filing_marks = lambda m: {"session": None, "financing": set(), "buyback": set(), "known": set()}
    assert [r["sector"] for r in svc.screen_rows("KR")["rows"]] == ["반도체 제조업", "자료처리업", None]
    assert sorted(p.name for p in sdir.iterdir()) == ["LATEST.json", "m.csv.gz"]       # an old snapshot is read, not refetched
