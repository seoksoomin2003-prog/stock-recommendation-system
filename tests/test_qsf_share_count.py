"""Share counts behind market value: all classes in the US, KRX listed shares in Korea.  No network."""
import gzip
import json

import pytest

from terminal.qsf import fundamentals as f, krx_history as kh


def annual(val):
    return {"shares_avg": [{"end": "2025-12-31", "val": val}]}


def test_a_multi_class_company_uses_the_total_when_sec_agrees():
    info = {"sharesOutstanding": 5.0e9, "marketCap": 3.5e12}
    assert f.us_total_shares(info, 300.0, annual(12.0e9)) == pytest.approx(3.5e12 / 300)


def test_a_single_class_company_keeps_yahoos_count():
    info = {"sharesOutstanding": 5.0e9, "marketCap": 1.5e12}
    assert f.us_total_shares(info, 300.0, annual(5.0e9)) == 5.0e9


def test_a_stale_market_value_alone_does_not_trigger_it():
    info = {"sharesOutstanding": 1.0e8, "marketCap": 4.9e10}       # ROK: Yahoo and SEC agree, price fell after the value was stored
    assert f.us_total_shares(info, 370.0, annual(1.1e8)) == 1.0e8


def test_without_sec_figures_yahoos_own_price_is_needed():
    info = {"sharesOutstanding": 1.0e9, "marketCap": 1.5e12}
    assert f.us_total_shares(info, 1000.0, {}) == 1.0e9
    assert f.us_total_shares({**info, "currentPrice": 1000.0}, 900.0, {}) == pytest.approx(1.5e9)


def test_yahoos_own_price_is_preferred_for_the_total():
    info = {"sharesOutstanding": 5.0e9, "marketCap": 3.5e12, "currentPrice": 350.0}
    assert f.us_total_shares(info, 300.0, annual(12.0e9)) == pytest.approx(1.0e10)


def test_missing_values_change_nothing():
    assert f.us_total_shares({}, 10.0) is None
    assert f.us_total_shares({"sharesOutstanding": 7.0}, 10.0) == 7.0
    assert f.us_total_shares({"sharesOutstanding": 7.0, "marketCap": 100.0}, None) == 7.0


def _facts(shares, eps=5.0, ni=5.0e9):
    def rows(vals):
        return [{"end": f"{2025 - len(vals) + 1 + i}-12-31", "filed": f"{2026 - len(vals) + 1 + i}-02-15", "val": v} for i, v in enumerate(vals)]
    return {"shares_avg": rows(shares), "eps": rows([eps] * len(shares)), "net_income": rows([ni] * len(shares))}


def test_a_share_count_in_millions_is_not_used_for_market_value():
    m = f.metrics(_facts([1.0e9, 1000.0]), 50.0, "2026-06-01")
    assert m["market_cap"] is None and m["share_scale_error"] is True


def test_a_changed_scale_gives_no_share_change_instead_of_an_extreme_one():
    m = f.metrics(_facts([1.0e9, 1000.0]), 50.0, "2026-06-01")
    assert m["share_change"] is None
    up = f.metrics(_facts([1000.0, 1.0e9]), 50.0, "2026-06-01")
    assert up["share_change"] is None and up["share_scale_error"] is True


def test_a_series_all_in_millions_keeps_its_change_but_not_its_market_value():
    m = f.metrics(_facts([1020.0, 1000.0]), 50.0, "2026-06-01")      # MCD: consistent units, so the ratio is still right
    assert m["share_change"] == pytest.approx(1000 / 1020 - 1)
    assert m["market_cap"] is None and m["share_scale_error"] is True


def test_yahoos_count_still_gives_market_value_with_a_wrong_sec_scale():
    m = f.metrics(_facts([1020.0, 1000.0]), 50.0, "2026-06-01", shares=1.0e9)
    assert m["market_cap"] == pytest.approx(5.0e10)


def test_real_changes_pass():
    split = f.metrics(_facts([1.0e8, 5.0e9]), 50.0, "2026-06-01")     # a 50-for-1 split left unrestated
    assert split["share_change"] == pytest.approx(49.0) and split["share_scale_error"] is False
    m = f.metrics(_facts([0.9e9, 1.0e9]), 50.0, "2026-06-01")
    assert m["market_cap"] == pytest.approx(5.0e10) and m["share_change"] == pytest.approx(1 / 0.9 - 1)


def test_a_tiny_eps_is_not_used_as_the_check():
    m = f.metrics(_facts([1.0e9, 1.0e9], eps=0.01, ni=1.0e5), 50.0, "2026-06-01")
    assert m["market_cap"] == pytest.approx(5.0e10) and m["share_scale_error"] is False


def test_a_wrong_sec_scale_does_not_block_or_trigger_the_multi_class_total():
    info = {"sharesOutstanding": 5.0e9, "marketCap": 3.5e12, "currentPrice": 350.0}
    assert f.us_total_shares(info, 300.0, annual(12000.0)) == pytest.approx(1.0e10)    # treated as no SEC figure
    assert f.us_total_shares({**info, "currentPrice": None}, 300.0, annual(12000.0)) == 5.0e9


def _flow(values):
    return [{"end": e, "filed": e[:4] + "-12-31", "val": v} for e, v in values]


def test_free_cash_flow_needs_cash_flow_and_capex_of_the_same_year():
    base = {"revenue": _flow([("2025-12-31", 100.0)]), "net_income": _flow([("2025-12-31", 10.0)])}
    same = f.metrics({**base, "ocf": _flow([("2025-12-31", 30.0)]), "capex": _flow([("2025-12-31", 10.0)])}, 10.0, "2026-06-01", shares=100.0)
    assert same["fcf"] == 20.0 and same["fcf_yield"] == pytest.approx(0.02) and same["fcf_years_positive"] == 1.0
    stopped = f.metrics({**base, "ocf": _flow([("2024-12-31", 25.0), ("2025-12-31", 30.0)]), "capex": _flow([("2024-12-31", 10.0)])}, 10.0, "2026-06-01", shares=100.0)
    assert stopped["fcf"] is None and stopped["fcf_yield"] is None and stopped["fcf_margin"] is None and stopped["fcf_years_positive"] is None


def _kr_row(value, end="2025-12-31"):
    return {"status": "REAL", "value": value, "period_end": end, "receipt_date": "2026-03-20", "basis": "CONSOLIDATED"}


def test_korean_capex_is_positive_whichever_sign_the_filer_used():
    for raw in (500.0, -500.0):
        out = f.extract_kr({2025: {"capex": _kr_row(raw), "operating_cash_flow": _kr_row(800.0), "revenue": _kr_row(1000.0)}})
        assert out["capex"][0]["val"] == 500.0
    m = f.metrics(out, 10.0, "2026-06-01", shares=100.0)
    assert m["fcf"] == 300.0


def test_korean_capex_comes_from_the_standard_account_only():
    from markets.kr import dart
    from markets.kr.account_mapping import REGISTRY
    assert REGISTRY["capex"]["account_ids"] == ["ifrs-full_PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"]
    base = {"basis": "CONSOLIDATED", "statement": "CF", "amount_type": "FY", "value": 7.0, "account_name": "유형자산의 취득", "period_start": "2025-01-01",
            "period_end": "2025-12-31", "fiscal_year": 2025, "fiscal_period": "FY", "rcept_no": "1", "receipt_date": "2026-03-20", "currency": "KRW", "unit": "KRW", "mapping_version": "x"}
    assert dart.extract_concepts([{**base, "account_id": "-표준계정코드 미사용-"}], "NON_FINANCIAL")["capex"]["status"] == "UNAVAILABLE"
    assert dart.extract_concepts([{**base, "account_id": REGISTRY["capex"]["account_ids"][0]}], "NON_FINANCIAL")["capex"]["value"] == 7.0


def _day(root, day, kospi, kosdaq):
    for board, rows in (("KOSPI", kospi), ("KOSDAQ", kosdaq)):
        p = kh.path_of(root, board, day)
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            json.dump(rows, fh)


def row(code, shares):
    return [code] + [None] * 10 + [shares]


def test_listed_shares_come_from_the_newest_full_day(tmp_path):
    _day(tmp_path, "2026-11-05", [row("000010", "1,000")], [row("000020", "2000")])
    _day(tmp_path, "2026-11-06", [row("000010", "1,500")], [])              # not published in full
    assert kh.listed_shares(tmp_path, "2026-11-06") == {"000010": 1000.0, "000020": 2000.0}


def test_a_later_day_is_never_read_and_an_old_snapshot_is_not_used(tmp_path):
    _day(tmp_path, "2026-11-10", [row("000010", "9")], [row("000020", "9")])
    assert kh.listed_shares(tmp_path, "2026-11-09") == {}
    assert kh.listed_shares(tmp_path, "2026-11-25") == {}
    assert kh.listed_shares(tmp_path, "2026-11-11") == {"000010": 9.0, "000020": 9.0}
