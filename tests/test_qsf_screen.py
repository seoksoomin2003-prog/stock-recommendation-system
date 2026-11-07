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
        def latest(self, market):
            assert market == "KR"
            return latest(row("A", 80), row("B", 40))

    class T:
        qsf = Qsf()
    fn = routes(T())[("GET", "/api/qsf/screen")]
    assert tickers(fn({"market": "KR", "min_score": "50"}, {})) == ["A"]
    with pytest.raises(ValueError):      # the server turns this into a 400
        fn({"market": "KR", "sort": "nope"}, {})
