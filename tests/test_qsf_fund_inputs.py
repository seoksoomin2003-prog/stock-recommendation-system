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


# ---------------------------------------------------------------------- PER from market value
def test_per_is_market_value_over_profit_so_a_split_after_the_report_cannot_distort_it():
    d = base(eps=rows([20.0, 22.5, 25.0, 30.0]))                 # reported before a 25-for-1 split: 0.4 shares then, 10 now
    m = metrics(d, close=24.0, shares=10.0)
    assert m["pe"] == pytest.approx(24.0 * 10.0 / 12.0) and m["eps"] == pytest.approx(1.2) and m["eps_reported"] == 30.0
    assert m["pe"] * m["eps"] == pytest.approx(24.0)


def test_a_loss_keeps_a_negative_per_and_no_profit_gives_none():
    assert metrics(base(net_income=rows([8.0, 9.0, 10.0, -4.0])), close=24.0)["pe"] == pytest.approx(-60.0)
    m = metrics(base(net_income=rows([8.0, 9.0, 10.0, None]), eps=rows([0.8, 0.9, 1.0, 1.2])), close=24.0)
    assert m["pe"] is None and m["eps"] is None           # market value exists: an EPS without its profit is not trusted against the price
    assert metrics(base(net_income=rows([8.0, 9.0, 10.0, 0.0])), close=24.0)["pe"] is None


def test_reported_eps_is_the_fallback_only_without_market_value():
    m = f.metrics(base(eps=rows([0.8, 0.9, 1.0, 1.2])), 24.0, AS_OF)
    assert m["market_cap"] is None and m["pe"] == pytest.approx(20.0) and m["eps"] == 1.2
    stopped = f.metrics(base(eps=rows([0.8, 0.9, 1.0, None])), 24.0, AS_OF)
    assert stopped["pe"] is None and stopped["eps"] is None


# ---------------------------------------------------------------------- EPS growth across a change of share basis
def filings(per_filing):
    """US style: every report shows three years.  ``per_filing``: {report year: {fiscal year: value}} -> rows of every vintage."""
    out = [{"end": f"{fy}-12-31", "val": v, "filed": f"{year + 1}-02-15"} for year, shown in per_filing.items() for fy, v in shown.items()]
    return sorted(out, key=lambda r: (r["end"], r["filed"]))


def us_split(factor=10.0, restate_shares=True, restate_eps=True):
    """Profit 80, 90, 100, 120 on 10 shares; a split in 2025, so only the 2025 report shows 2023 and 2024 on the new basis."""
    ni = {2022: 80.0, 2023: 90.0, 2024: 100.0, 2025: 120.0}
    old = {y: {fy: ni[fy] / 10.0 for fy in (y - 2, y - 1, y) if fy in ni} for y in (2022, 2023, 2024)}
    new_eps = {fy: ni[fy] / (10.0 * (factor if restate_eps else 1.0)) for fy in (2023, 2024, 2025)}
    new_sh = {fy: 10.0 * (factor if restate_shares else 1.0) for fy in (2023, 2024, 2025)}
    return {"revenue": rows([800.0, 900.0, 1000.0, 1200.0]), "net_income": rows(list(ni.values())),
            "eps": filings({**old, 2025: new_eps}), "shares_avg": filings({**{y: {fy: 10.0 for fy in shown} for y, shown in old.items()}, 2025: new_sh})}


def test_a_split_restated_in_later_reports_is_carried_to_the_year_they_no_longer_show():
    m = metrics(us_split(10.0), shares=100.0)
    assert m["eps_growth"] == pytest.approx(0.2)                              # both years come from the newest report
    assert m["eps_cagr3"] == pytest.approx(1.5 ** (1 / 3) - 1)               # 2022 is 8.0 as filed, 0.8 on today's basis
    assert f.metrics(us_split(10.0), 10.0, "2025-06-01", shares=100.0)["eps_cagr3"] is None      # before the split report: no 2021 figure


def test_a_reverse_split_is_carried_the_same_way():
    assert metrics(us_split(0.2), shares=2.0)["eps_cagr3"] == pytest.approx(1.5 ** (1 / 3) - 1)


def test_a_restatement_only_one_series_shows_is_not_taken_for_a_split():
    assert metrics(us_split(10.0, restate_eps=False))["eps_cagr3"] is None               # the count moved tenfold and EPS did not
    profit_restated = metrics(us_split(10.0, restate_shares=False))                      # EPS restated, the count not: one share basis
    assert profit_restated["eps_cagr3"] == pytest.approx((1.2 / 8.0) ** (1 / 3) - 1)


def test_a_share_count_filed_in_another_unit_is_not_a_split():
    d = us_split(1.0)
    d["shares_avg"] = [{**r, "val": r["val"] * (1000.0 if r["filed"] < "2026" else 1.0)} for r in d["shares_avg"]]
    assert metrics(d)["eps_cagr3"] == pytest.approx(1.5 ** (1 / 3) - 1)


def test_a_real_share_issue_keeps_the_reported_us_growth():
    d = us_split(1.0)
    d["eps"] = [{**r, "val": r["val"] / 2.0} if r["end"] == "2025-12-31" else r for r in d["eps"]]         # shares doubled in 2025, nothing restated
    d["shares_avg"] = [{**r, "val": 20.0} if r["end"] == "2025-12-31" else r for r in d["shares_avg"]]
    m = metrics(d)
    assert m["eps_growth"] == pytest.approx(6.0 / 10.0 - 1) and m["eps_cagr3"] == pytest.approx((6.0 / 8.0) ** (1 / 3) - 1)


def kr(eps, ni=(8.0e9, 9.0e9, 10.0e9, 12.0e9)):
    """Korean style: one report a year, each showing only its own year, and no share count."""
    return {"revenue": rows([80.0, 90.0, 100.0, 120.0], basis="CONSOLIDATED"), "net_income": rows(list(ni), basis="CONSOLIDATED"), "eps": rows(list(eps), basis="CONSOLIDATED")}


def test_reported_eps_on_one_share_basis_is_compared_as_before():
    m = metrics(kr([800.0, 900.0, 1000.0, 1200.0]), shares=1.0e7)
    assert m["eps_growth"] == pytest.approx(0.2) and m["eps_cagr3"] == pytest.approx(1.5 ** (1 / 3) - 1)
    buyback = metrics(kr([800.0, 900.0, 1000.0, 1500.0]), shares=0.8e7)          # 20% fewer shares: a real change, kept
    assert buyback["eps_growth"] == pytest.approx(0.5)


def test_a_korean_split_gives_no_growth_rather_than_a_wrong_one():
    m = metrics(kr([800.0, 900.0, 1000.0, 240.0]), shares=5.0e7)                  # 5-for-1 in 2025: profit up 20%, reported EPS down 76%
    assert m["eps_growth"] is None and m["eps_cagr3"] is None
    merged = metrics(kr([800.0, 900.0, 5000.0, 6000.0]), shares=0.2e7)            # 1-for-5 consolidation in 2024
    assert merged["eps_growth"] == pytest.approx(0.2) and merged["eps_cagr3"] is None


def test_a_break_between_the_two_years_is_seen_without_a_count_at_the_older_end():
    m = metrics(kr([1600.0, 900.0, 500.0, 600.0], ni=(None, 9.0e9, 10.0e9, 12.0e9)), shares=2.0e7)       # 1-for-1 bonus issue in 2024, no 2022 profit row
    assert m["eps_cagr3"] is None and m["eps_growth"] == pytest.approx(0.2)


def test_without_counts_the_reported_figures_stand():
    m = metrics(kr([800.0, 900.0, 1000.0, 1200.0], ni=(None, None, None, 12.0e9)), shares=1.0e7)
    assert m["eps_growth"] == pytest.approx(0.2) and m["eps_cagr3"] == pytest.approx(1.5 ** (1 / 3) - 1)
