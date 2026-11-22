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


def test_a_zero_the_filer_stopped_tagging_is_still_zero():
    d = base(liabilities=rows([30.0] * 4), cash=rows([6.0] * 4))
    repaid = metrics({**d, "debt_long": rows([10.0, 10.0, 0.0, None]), "debt_short": rows([2.0, 2.0, 2.0, 0.0])})
    assert repaid["debt_equity"] == 0.0 and repaid["cash_debt"] is None
    never = metrics({**d, "debt_short": rows([0.0, 0.0, 0.0, None])})
    assert never["debt_equity"] == 0.0
    older = metrics({**d, "debt_short": rows([0.0, 0.0, None, None])})      # two years without the tag: no longer known
    assert older["debt_equity"] == pytest.approx(30.0 / 60.0)


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
def test_per_is_market_value_over_profit_when_a_split_followed_the_report():
    d = base(eps=rows([20.0, 22.5, 25.0, 30.0]))                 # reported before a 25-for-1 split: 0.4 shares then, 10 now
    m = metrics(d, close=24.0, shares=10.0)
    assert m["pe"] == pytest.approx(24.0 * 10.0 / 12.0) and m["eps"] == pytest.approx(1.2) and m["eps_reported"] == 30.0
    assert m["pe"] * m["eps"] == pytest.approx(24.0) and m["pe_basis"] == "MARKET_VALUE"


def test_reported_eps_is_kept_while_its_share_count_is_todays():
    d = base(eps=rows([0.64, 0.72, 0.8, 0.96]))                  # 12.5 shares earn the profit, 10 of them are the listed class
    m = metrics(d, close=24.0, shares=10.0)
    assert m["pe"] == pytest.approx(25.0) and m["eps"] == 0.96 and m["pe_basis"] == "REPORTED_EPS"
    assert m["market_cap"] == pytest.approx(240.0) and m["pb"] == pytest.approx(4.0)        # market value itself is unchanged


def test_a_loss_keeps_a_negative_per_and_no_profit_gives_none():
    assert metrics(base(net_income=rows([8.0, 9.0, 10.0, -4.0])), close=24.0)["pe"] == pytest.approx(-60.0)
    m = metrics(base(net_income=rows([8.0, 9.0, 10.0, None]), eps=rows([0.8, 0.9, 1.0, 1.2])), close=24.0)
    assert m["pe"] is None and m["eps"] is None           # no profit to check the EPS share count with, and none for market value either
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


# ---------------------------------------------------------------------- Korean account ids
def kr_obs(*accounts, rcept="20260320000001"):
    from markets.kr import dart
    raw = [{"sj_div": sj, "account_id": acc, "account_nm": acc, "thstrm_amount": amount, "rcept_no": rcept, "currency": cur}
           for sj, acc, amount, *rest in accounts for cur in [rest[0] if rest else "KRW"]]
    return dart.normalize_statements(raw, corp_code="c", ticker="000000", year=2025, reprt_code="11011", fs_div="CFS")


def kr_concepts(*accounts, klass="NON_FINANCIAL"):
    from markets.kr import dart
    return dart.extract_concepts(kr_obs(*accounts), klass)


EPS, CONT, DISC = "ifrs-full_BasicEarningsLossPerShare", "ifrs-full_BasicEarningsLossPerShareFromContinuingOperations", "ifrs-full_BasicEarningsLossPerShareFromDiscontinuedOperations"


def test_total_basic_eps_is_preferred_and_the_two_parts_are_added_without_it():
    assert f.kr_basic_eps(kr_concepts(("IS", EPS, "900"), ("IS", CONT, "1000"), ("IS", DISC, "-100")))["value"] == 900.0
    assert f.kr_basic_eps(kr_concepts(("IS", EPS, "900"), ("IS", CONT, "1000")))["value"] == 900.0          # the other part is under a company id
    both = f.kr_basic_eps(kr_concepts(("CIS", CONT, "45935"), ("CIS", DISC, "781")))
    assert both["status"] == "REAL" and both["value"] == 46716.0 and both["period_end"] == "2025-12-31"
    assert f.kr_basic_eps(kr_concepts(("CIS", CONT, "-3951"), ("CIS", DISC, "-12")))["value"] == -3963.0


def test_continuing_eps_alone_is_the_total_and_a_repeated_line_is_not_added():
    assert f.kr_basic_eps(kr_concepts(("IS", CONT, "55832")))["value"] == 55832.0
    assert f.kr_basic_eps(kr_concepts(("IS", CONT, "55832"), ("IS", DISC, "")))["value"] == 55832.0
    assert f.kr_basic_eps(kr_concepts(("IS", CONT, "571"), ("IS", DISC, "571")))["value"] == 571.0           # one figure tagged twice
    assert f.kr_basic_eps(kr_concepts(("IS", CONT, "10569"), ("IS", DISC, "10567")))["value"] == 10569.0     # the preferred share's line
    assert f.kr_basic_eps(kr_concepts(("IS", DISC, "120"))).get("status") != "REAL"                          # a part alone is no EPS


def test_korean_series_take_the_newest_year_from_the_eps_parts():
    def year(y, *accounts):
        from markets.kr import dart
        raw = [{"sj_div": sj, "account_id": acc, "account_nm": acc, "thstrm_amount": amount, "rcept_no": f"{y + 1}0320000001"} for sj, acc, amount in accounts]
        return dart.extract_concepts(dart.normalize_statements(raw, corp_code="c", ticker="000000", year=y, reprt_code="11011", fs_div="CFS"), "NON_FINANCIAL")
    out = f.extract_kr({2022: year(2022, ("IS", EPS, "3964"), ("IS", "ifrs-full_Revenue", "100")),
                        2025: year(2025, ("IS", CONT, "28530"), ("IS", DISC, "0"), ("IS", "ifrs-full_Revenue", "300"))})
    assert [(r["end"], r["val"]) for r in out["eps"]] == [("2022-12-31", 3964.0), ("2025-12-31", 28530.0)]


REV, GOODS = "ifrs-full_Revenue", "dart_RevenueFromSaleOfGoodsProduct"


def test_product_sales_are_revenue_only_when_the_statement_proves_it():
    proven = kr_concepts(("IS", GOODS, "258497722389"), ("IS", "ifrs-full_CostOfSales", "220277193240"), ("IS", "ifrs-full_GrossProfit", "38220529149"))
    assert proven["revenue"]["status"] == "REAL" and proven["revenue"]["value"] == 258497722389.0 and proven["revenue"]["account_id"] == GOODS
    part = kr_concepts(("IS", GOODS, "100"), ("IS", "ifrs-full_CostOfSales", "220"), ("IS", "ifrs-full_GrossProfit", "80"))       # sales of 300 in all
    assert part["revenue"] == {"status": "UNAVAILABLE", "reason": "NOT_REPORTED_UNDER_STANDARD_ACCOUNT"}
    assert kr_concepts(("IS", GOODS, "100"))["revenue"]["status"] == "UNAVAILABLE"                                                 # nothing to prove it with
    std = kr_concepts(("IS", REV, "300"), ("IS", GOODS, "100"), ("IS", "ifrs-full_CostOfSales", "20"), ("IS", "ifrs-full_GrossProfit", "80"))
    assert std["revenue"]["value"] == 300.0


# ---------------------------------------------------------------------- statements in another currency than the price
def usd_group():
    """Won statements for 2022, dollar statements since 2023 (241560)."""
    def series(vals):
        return [{**r, **({} if r["end"] < "2023" else {"currency": "USD"})} for r in rows(vals, basis="CONSOLIDATED")]
    return {"revenue": series([8.0e12, 7.0e9, 6.5e9, 6.0e9]), "net_income": series([6.0e11, 7.0e8, 4.0e8, 3.0e8]), "equity": series([5.0e12, 4.6e9, 4.8e9, 5.0e9]),
            "assets": series([1.0e13, 8.0e9, 8.5e9, 9.0e9]), "ocf": series([9.0e11, 9.0e8, 8.0e8, 7.0e8]), "capex": series([2.0e11, 2.0e8, 2.0e8, 2.0e8]),
            "eps": series([6000.0, 7.0, 4.0, 3.0])}


def test_dollar_statements_are_never_set_against_a_won_price():
    m = metrics(usd_group(), close=51600.0, shares=1.0e8)
    assert m["pe"] is None and m["pb"] is None and m["fcf_yield"] is None and m["eps"] is None
    assert m["currency"] == "USD" and "USD" in m["currency_note"] and m["market_cap"] == pytest.approx(5.16e12)
    assert m["roe"] == pytest.approx(0.06) and m["net_margin"] == pytest.approx(0.05) and m["fcf_margin"] == pytest.approx(5.0e8 / 6.0e9)    # inside the statements


def test_growth_stops_where_the_currency_changed():
    m = metrics(usd_group(), close=51600.0, shares=1.0e8)
    assert m["rev_growth"] == pytest.approx(6.0 / 6.5 - 1) and m["eps_growth"] == pytest.approx(-0.25)
    assert m["rev_cagr3"] is None and m["eps_cagr3"] is None          # 2022 is in won


def test_won_statements_carry_no_currency_mark_and_are_unchanged():
    won = kr_concepts(("IS", REV, "300"), ("IS", "ifrs-full_ProfitLoss", "30"))
    usd = {2025: {k: v for k, v in dart_year(("IS", REV, "300", "USD"), ("IS", "ifrs-full_ProfitLoss", "30", "USD")).items()}}
    assert "currency" not in f.extract_kr({2025: won})["revenue"][0]
    assert f.extract_kr(usd)["revenue"][0]["currency"] == "USD" and f.extract_kr(usd)["net_income"][0]["currency"] == "USD"
    m = metrics(base(eps=rows([0.8, 0.9, 1.0, 1.2])))
    assert "currency" not in m and m["pe"] == pytest.approx(10.0 / 1.2)


def dart_year(*accounts):
    return kr_concepts(*accounts)


# ---------------------------------------------------------------------- a year without a parent line
def kr_year(y, basis, **vals):
    """One year's concepts: ni / ni_parent / eq / eq_parent given only when the statement has the line."""
    concept = {"ni": "net_income", "ni_parent": "net_income_parent", "eq": "total_equity", "eq_parent": "equity_parent", "rev": "revenue", "assets": "total_assets", "liab": "total_liabilities"}
    return {concept[k]: {"status": "REAL", "value": v, "period_end": f"{y}-12-31", "receipt_date": f"{y + 1}-03-20", "basis": basis} for k, v in vals.items()}


def test_a_company_that_went_back_to_separate_statements_keeps_profit_and_equity():
    st = {2022: kr_year(2022, "SEPARATE", ni=8.0, eq=40.0, rev=80.0, assets=100.0, liab=60.0), 2023: kr_year(2023, "SEPARATE", ni=9.0, eq=45.0, rev=90.0, assets=100.0, liab=55.0),
          2024: kr_year(2024, "CONSOLIDATED", ni=11.0, ni_parent=10.0, eq=55.0, eq_parent=50.0, rev=100.0, assets=120.0, liab=65.0),
          2025: kr_year(2025, "SEPARATE", ni=12.0, eq=60.0, rev=120.0, assets=100.0, liab=40.0)}
    out = f.extract_kr(st)
    assert [(r["end"][:4], r["val"], r["basis"][0]) for r in out["net_income"]] == [("2022", 8.0, "S"), ("2023", 9.0, "S"), ("2024", 10.0, "C"), ("2025", 12.0, "S")]
    m = metrics(out, close=10.0, shares=30.0)
    assert m["basis"] == "SEPARATE" and m["roe"] == pytest.approx(0.2) and m["pb"] == pytest.approx(5.0) and m["debt_equity"] == pytest.approx(40.0 / 60.0)
    assert m["rev_growth"] is None and m["rev_cagr3"] == pytest.approx(1.5 ** (1 / 3) - 1)        # 2024 is on the other basis


def test_a_consolidated_year_without_the_parent_line_takes_the_total_only_without_outside_holders():
    whole = f.extract_kr({2024: kr_year(2024, "CONSOLIDATED", ni=10.0, ni_parent=10.0, eq=50.0, eq_parent=50.0), 2025: kr_year(2025, "CONSOLIDATED", ni=-4.0, eq=46.0, eq_parent=46.0)})
    assert [r["val"] for r in whole["net_income"]] == [10.0, -4.0]
    outside = f.extract_kr({2024: kr_year(2024, "CONSOLIDATED", ni=10.0, ni_parent=8.0, eq=50.0, eq_parent=40.0), 2025: kr_year(2025, "CONSOLIDATED", ni=-4.0, eq=46.0, eq_parent=37.0)})
    assert [r["end"][:4] for r in outside["net_income"]] == ["2024"]               # the 2025 total includes other holders: no parent profit that year
    assert metrics({**outside, "revenue": rows([100.0, 120.0], basis="CONSOLIDATED")})["roe"] is None


def test_a_company_that_never_shows_a_parent_line_is_read_as_before():
    sep = f.extract_kr({y: kr_year(y, "SEPARATE", ni=float(y - 2015), eq=50.0) for y in (2024, 2025)})
    assert [r["val"] for r in sep["net_income"]] == [9.0, 10.0] and "net_income_all" not in sep and "equity_all" not in sep
    grp = f.extract_kr({2025: kr_year(2025, "CONSOLIDATED", ni=10.0, ni_parent=8.0, eq=50.0, eq_parent=40.0)})
    assert grp["net_income"][0]["val"] == 8.0 and grp["net_income_all"][0]["val"] == 10.0 and grp["equity_all"][0]["val"] == 50.0


# ---------------------------------------------------------------------- who is scored by the financial rule
def test_us_financial_rule_is_for_balance_sheet_institutions():
    for sic in ("6021", "6022", "6035", "6141", "6199", "6211", 6282, "6311", "6321", "6331", "6351", "6399", "6799"):
        assert f.is_financial_sic(sic), sic
    for sic in ("6200", "6324", "6411", "6500", "6510", "6531", "6792", "6794", "6798", "7372", None, "", "abc"):
        assert not f.is_financial_sic(sic), sic


def test_korean_financial_rule_is_decided_by_the_statements_for_holding_companies():
    classified = {"current_assets": rows([1.0]), "current_liabilities": rows([1.0]), "assets": rows([5.0])}
    by_liquidity = {"assets": rows([5.0]), "liabilities": rows([4.0])}
    assert f.is_financial_kr("HOLDING_OR_OTHER_FINANCIAL", classified) is False       # SK, LG, GS ...
    assert f.is_financial_kr("HOLDING_OR_OTHER_FINANCIAL", by_liquidity) is True       # financial groups, card and capital companies
    assert f.is_financial_kr("HOLDING_OR_OTHER_FINANCIAL", None) is True               # nothing to decide with: as before
    for klass in ("BANK", "INSURANCE", "SECURITIES_AND_FINANCIAL_SERVICES", "TRUST_AND_COLLECTIVE_INVESTMENT"):
        assert f.is_financial_kr(klass, classified) is True
    assert f.is_financial_kr("NON_FINANCIAL", by_liquidity) is False and f.is_financial_kr(None, by_liquidity) is False


def test_the_live_korean_score_uses_the_statement_rule(tmp_path):
    import inspect
    from terminal.qsf import research_kr_live, service
    assert "is_financial_kr(klass" in inspect.getsource(service.QSF._kr_fund_events)
    assert "is_financial_kr(klass" in inspect.getsource(research_kr_live.Statements.fund)


# ---------------------------------------------------------------------- a part of revenue is not revenue
def test_contract_revenue_below_the_years_profit_is_not_total_revenue():
    contract = f.CONTRACT_REVENUE[0]
    bank = base(revenue=rows([10.0, 11.0, 12.0, 13.0], alias=contract), net_income=rows([300.0, 320.0, 350.0, 384.0]), op_income=rows([9.0, 10.0, 11.0, 12.0]))
    m = metrics(bank)
    assert m["rev_growth"] is None and m["rev_cagr3"] is None and m["net_margin"] is None and m["op_margin"] is None and "총매출" in m["revenue_note"]
    assert m["roe"] == pytest.approx(384.0 / 60.0)                        # everything that does not need revenue stays
    whole = metrics(base(revenue=rows([80.0, 90.0, 100.0, 120.0], alias=contract)))
    assert whole["rev_growth"] == pytest.approx(0.2) and "revenue_note" not in whole
    total_tag = metrics(base(revenue=rows([10.0, 11.0, 12.0, 13.0], alias="Revenues"), net_income=rows([300.0, 320.0, 350.0, 384.0])))
    assert total_tag["rev_growth"] == pytest.approx(13.0 / 12.0 - 1)      # a total-revenue tag is taken as filed


# ---------------------------------------------------------------------- version and cache keys
def test_extracted_series_have_new_cache_keys_and_the_version_moved():
    from pathlib import Path
    from terminal.qsf import config
    code = (Path(__file__).resolve().parents[1] / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")
    assert code.count('f"annual4:') == 1 and code.count('f"krfund3:') == 2 and "annual2:" not in code and "annual3:" not in code and "krfund2:" not in code
    assert config.MODEL_VERSION == "QSF-1.5.0"          # 1.1.9 moved the keys; 1.2.1 moved the US key again for the debt parts


@pytest.mark.parametrize("long_name,short_name,sec_name,want", [
    ("AvalonBay Communities, Inc.", "Vivmark Residential", "VIVMARK RESIDENTIAL", "Vivmark Residential"),      # the long name is another company's
    ("SLB N.V.", "SLB N.V.", "SCHLUMBERGER LIMITED/NV", "SLB N.V."),                                          # SEC keeps an older wording: Yahoo agrees with itself
    ("PG&E Corporation", "Pacific Gas & Electric Co.", "PG&E Corp", "PG&E Corporation"),                      # the short name is the odd one
    ("Alphabet Inc.", "Alphabet Inc.", "Alphabet Inc.", "Alphabet Inc."),
    ("Alpha Co", "Beta Co", "GAMMA CORP", "Alpha Co"),                                                         # three names, no two agree: nothing to go on
    ("Alpha Co", None, "BETA CORP", "Alpha Co"), (None, "Alpha", "ALPHA CORP", "ALPHA CORP"), (None, None, None, None)])
def test_a_long_name_of_another_company_gives_way_to_the_two_that_agree(long_name, short_name, sec_name, want):
    assert f.us_display_name(long_name, short_name, sec_name) == want
