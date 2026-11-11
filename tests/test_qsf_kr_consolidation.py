"""Consolidated figures meet consolidated figures, and two groups with a financial business have no cash flow figure.  No network."""
import pytest

from terminal.qsf import config, factors, fundamentals as f

END, FILED = "2025-12-31", "2026-03-20"


def row(val, end=END, basis="CONSOLIDATED"):
    return {"end": end, "val": val, "filed": FILED, "basis": basis}


def group(equity=25.0, equity_all=100.0, ni=10.0, ni_all=40.0, ocf=80.0, capex=30.0):
    d = {"revenue": [row(500.0)], "net_income": [row(ni)], "equity": [row(equity)], "assets": [row(400.0)], "liabilities": [row(300.0)], "ocf": [row(ocf)], "capex": [row(capex)], "eps": [row(1.0)]}
    if equity_all is not None:
        d["equity_all"] = [row(equity_all)]
    if ni_all is not None:
        d["net_income_all"] = [row(ni_all)]
    return d


def metrics(d, shares=10.0, close=10.0):
    return f.metrics(d, close, "2026-06-01", shares=shares, source="OpenDART")


def test_group_figures_meet_group_equity_and_profit():
    m = metrics(group())
    assert m["debt_equity"] == pytest.approx(3.0) and m["equity_assets"] == pytest.approx(0.25)
    assert m["ocf_to_ni"] == pytest.approx(2.0) and m["parent_share"] == pytest.approx(0.25)


def test_market_value_meets_the_parents_share_of_cash():
    m = metrics(group())
    assert m["fcf"] == 50.0 and m["fcf_yield"] == pytest.approx(50.0 * 0.25 / 100.0)
    assert m["fcf_margin"] == pytest.approx(0.1)       # both are the whole group, so nothing is cut


def test_per_share_figures_stay_the_parents():
    m = metrics(group())
    assert m["roe"] == pytest.approx(0.4) and m["pb"] == pytest.approx(4.0) and m["eps"] == 1.0


def test_a_group_loss_gives_no_ratio_rather_than_a_parent_one():
    assert metrics(group(ni_all=-5.0))["ocf_to_ni"] is None


def test_a_company_without_group_equity_is_unchanged():
    """The US reports no such series, so its figures must not move."""
    m = metrics(group(equity_all=None, ni_all=None))
    assert m["debt_equity"] == pytest.approx(12.0) and m["equity_assets"] == pytest.approx(25.0 / 400.0)
    assert m["ocf_to_ni"] == pytest.approx(8.0) and m["fcf_yield"] == pytest.approx(0.5) and m["parent_share"] is None


def test_group_equity_of_another_year_is_not_used():
    d = group()
    d["equity_all"] = [row(100.0, "2024-12-31")]
    assert metrics(d)["debt_equity"] == pytest.approx(12.0) and metrics(d)["parent_share"] is None


@pytest.mark.parametrize("equity,equity_all", [(120.0, 100.0), (-5.0, 100.0), (25.0, -10.0)])
def test_impossible_shares_change_nothing(equity, equity_all):
    m = metrics(group(equity=equity, equity_all=equity_all))
    assert m["parent_share"] is None and m["fcf_yield"] == pytest.approx(0.5)


def test_group_profit_of_another_year_keeps_the_parent_ratio():
    d = group()
    d["net_income_all"] = [row(40.0, "2024-12-31")]
    assert metrics(d)["ocf_to_ni"] == pytest.approx(8.0)


def test_the_listed_groups_have_no_cash_flow_figure_and_keep_the_rest():
    m = f.blank_mixed_cash_flow(metrics(group()), "005380")
    for k in ("fcf", "fcf_yield", "fcf_margin", "fcf_years_positive", "ocf_to_ni"):
        assert m[k] is None
    assert m["debt_equity"] == pytest.approx(3.0) and m["is_financial"] is False and "금융" in m["cash_flow_note"]
    assert set(f.FINANCE_MIXED) == {"005380", "000880"}


def test_other_companies_and_an_unavailable_fund_pass_through():
    m = metrics(group())
    assert f.blank_mixed_cash_flow(m, "021240") is m
    gone = {"status": "UNAVAILABLE", "reason": "x"}
    assert f.blank_mixed_cash_flow(gone, "005380") is gone


def test_factors_are_missing_with_the_reason_never_zero():
    fund = f.blank_mixed_cash_flow(metrics(group()), "000880")
    c = {"fund": fund}
    for factor in (factors.free_cash_flow, factors.cash_flow_quality):
        out = factor(c)
        assert out["status"] == "MISSING" and out.get("normalized") is None and "보험" in out["reason"]
    assert factors.valuation(c)["normalized"] is not None


def test_version():
    assert config.MODEL_VERSION == "QSF-1.3.1"
