"""Fundamental inputs after the 2026-11-11 audit: one fiscal year per figure, market-value PER, share bases, currency.  No network."""
import pytest

from terminal.qsf import fundamentals as f

AS_OF = "2026-06-01"


def rows(vals, last=2025, month_day="12-31", **more):
    """Yearly rows ending in ``last``; a None value leaves that year out."""
    first = last - len(vals) + 1
    return [{"end": f"{first + i}-{month_day}", "val": v, "filed": f"{first + i + 1}-02-15", **more} for i, v in enumerate(vals) if v is not None]


def base(**more):
    d = {"revenue": rows([80.0, 90.0, 100.0, 120.0]), "net_income": rows([8.0, 9.0, 10.0, 12.0]), "equity": rows([40.0, 45.0, 50.0, 60.0]), "assets": rows([100.0] * 4)}
    d.update(more)
    return d


def metrics(d, close=10.0, shares=10.0, **kw):
    return f.metrics(d, close, AS_OF, shares=shares, **kw)


# ---------------------------------------------------------------------- one fiscal year per figure
def test_a_series_that_stopped_last_year_gives_no_figure():
    m = metrics(base(op_income=rows([9.0, 10.0, 11.0, None]), eps=rows([0.8, 0.9, 1.0, None]), interest=rows([1.0, 1.0, 1.0, None])))
    assert m["op_margin"] is None and m["interest_cover"] is None and m["eps_growth"] is None and m["eps_cagr3"] is None
    assert m["net_margin"] == pytest.approx(0.1) and m["fiscal_end"] == "2025-12-31"


def test_a_ratio_never_mixes_two_fiscal_years():
    m = metrics(base(net_income=rows([8.0, 9.0, 10.0, None])))             # parent profit missing in the newest report
    assert m["roe"] is None and m["net_margin"] is None and m["roe_years_positive"] is None
    assert m["rev_growth"] == pytest.approx(0.2) and m["equity_assets"] == pytest.approx(0.6)


def test_growth_needs_the_year_exactly_before():
    m = metrics(base(revenue=rows([80.0, None, None, 120.0]), eps=rows([0.8, 0.9, None, 1.2])))
    assert m["rev_growth"] is None and m["eps_growth"] is None           # the last report but one is three (two) years older
    assert m["rev_cagr3"] == pytest.approx(1.5 ** (1 / 3) - 1) and m["eps_cagr3"] == pytest.approx(1.5 ** (1 / 3) - 1)


def test_three_year_growth_needs_the_year_three_before():
    m = metrics(base(revenue=rows([None, 90.0, 100.0, 120.0])))
    assert m["rev_cagr3"] is None and m["rev_growth"] == pytest.approx(0.2)


def test_a_53_week_year_is_still_one_year():
    d = {"revenue": [{"end": "2024-10-27", "val": 100.0, "filed": "2024-12-10"}, {"end": "2025-11-02", "val": 110.0, "filed": "2025-12-10"}],
         "net_income": [{"end": "2024-10-27", "val": 10.0, "filed": "2024-12-10"}, {"end": "2025-11-02", "val": 11.0, "filed": "2025-12-10"}]}
    assert metrics(d)["rev_growth"] == pytest.approx(0.1)


def test_a_quarter_end_balance_is_not_last_years_equity():
    equity = rows([40.0, 45.0, 50.0, 60.0]) + [{"end": "2025-09-30", "val": 1.0, "filed": "2026-02-15"}]
    m = metrics(base(equity=sorted(equity, key=lambda r: r["end"])))
    assert m["roe_prev"] == pytest.approx(10.0 / 50.0) and m["roe"] == pytest.approx(0.2)


def test_debt_parts_of_the_latest_year_only():
    d = base(liabilities=rows([30.0] * 4), cash=rows([6.0] * 4))
    both = metrics({**d, "debt_long": rows([10.0] * 4), "debt_short": rows([2.0] * 4)})
    assert both["debt_equity"] == pytest.approx(12.0 / 60.0) and both["cash_debt"] == pytest.approx(0.5)
    short_gone = metrics({**d, "debt_long": rows([10.0] * 4), "debt_short": rows([2.0, 2.0, 0.0, None])})
    assert short_gone["debt_equity"] == pytest.approx(10.0 / 60.0)         # long-term debt is the figure
    long_gone = metrics({**d, "debt_long": rows([10.0, 10.0, 10.0, None]), "debt_short": rows([2.0] * 4)})
    assert long_gone["debt_equity"] == pytest.approx(30.0 / 60.0)          # not short-term debt alone, not last year's sum


def test_capital_return_is_unknown_when_both_tags_stopped():
    assert metrics(base(buyback=rows([5.0, 5.0, 5.0, None]), dividends=rows([1.0, 1.0, 1.0, None])))["returns_capital"] is None
    assert metrics(base(buyback=rows([5.0, 5.0, 5.0, None]), dividends=rows([1.0] * 4)))["returns_capital"] is True


def test_positive_year_shares_stop_with_the_series_and_reach_five_years():
    six = base(net_income=rows([-1.0, -1.0, 8.0, 9.0, 10.0, 12.0]), ocf=rows([1.0, 1.0, 9.0, 9.0, 9.0, 9.0]), capex=rows([5.0] * 6))
    m = metrics(six)
    assert m["roe_years_positive"] == pytest.approx(4 / 5) and m["fcf_years_positive"] == pytest.approx(4 / 5)
    assert metrics(base(ocf=rows([9.0, 9.0, 9.0, None]), capex=rows([5.0] * 4)))["fcf_years_positive"] is None


def test_balance_sheet_newer_than_the_income_statement_gives_no_flow_ratio():
    m = metrics({"revenue": rows([100.0, 120.0], last=2024), "net_income": rows([10.0, 12.0], last=2024), "equity": rows([50.0, 60.0, 70.0]), "assets": rows([100.0] * 3)})
    assert m["fiscal_end"] == "2025-12-31" and m["roe"] is None and m["rev_growth"] is None and m["equity_assets"] == pytest.approx(0.7)
