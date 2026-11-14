"""Korean earnings-surprise test: one quarter read correctly, usable the day after every report it reads, stale after 150 days, a
score that needs both signals, a verdict that asks for independence, one run.  No network, no real data."""
from datetime import date, timedelta

import numpy as np
import pytest

from terminal.qsf import research_kr as kr, research_kr_fund as kf, research_kr_sue as sue
from tests.test_qsf_kr_events import small_prices

QUIET = lambda m: None      # noqa: E731


def rep(rcept, op, sales=None, assets=1000.0):
    """One report on the consolidated basis: each flow is (three months, year to date)."""
    return {"CFS": {"rcept": rcept, "assets": (assets, None), "op": op, "sales": sales if sales is not None else op}}


def year(y, q1, q2, q3, fy, day="15"):
    """Four reports of one year from single-quarter operating profits: Q1, Q2, Q3 and the full year."""
    return {(y, "Q1"): rep(f"{y}-05-{day}", (q1, None)), (y, "H1"): rep(f"{y}-08-{day}", (q2, q1 + q2)),
            (y, "Q3"): rep(f"{y}-11-{day}", (q3, q1 + q2 + q3)), (y + 0, "FY"): rep(f"{y + 1}-03-{day}", (fy, None))}


# ----------------------------------------------------------------------------- one quarter's figure
def test_each_quarter_is_three_months_and_the_fourth_is_the_year_less_nine_months():
    r = year(2023, 10.0, 20.0, 30.0, 100.0)
    assert [sue.quarter_value(r, 2023, q, "CFS", "op") for q in ("Q1", "H1", "Q3", "FY")] == [10.0, 20.0, 30.0, 40.0]


def test_columns_that_disagree_leave_the_quarter_empty_and_a_missing_column_is_filled_from_the_other():
    r = year(2023, 10.0, 20.0, 30.0, 100.0)
    r[(2023, "H1")]["CFS"]["op"] = (30.0, 30.0)             # the "three months" column holds the half-year: not 30 - 10
    assert sue.quarter_value(r, 2023, "H1", "CFS", "op") is None
    r[(2023, "H1")]["CFS"]["op"] = (None, 30.0)             # only the year to date: the quarter is the difference
    assert sue.quarter_value(r, 2023, "H1", "CFS", "op") == 20.0
    r[(2023, "H1")]["CFS"]["op"] = (20.2, 30.0)             # within the tolerance (restated first quarter)
    assert sue.quarter_value(r, 2023, "H1", "CFS", "op") == 20.2
    del r[(2023, "Q1")]                                      # nothing to compare with: the documented column is taken
    assert sue.quarter_value(r, 2023, "H1", "CFS", "op") == 20.2


def test_a_missing_report_or_basis_is_empty_not_zero():
    r = year(2023, 10.0, 20.0, 30.0, 100.0)
    del r[(2023, "Q3")]
    assert sue.quarter_value(r, 2023, "FY", "CFS", "op") is None          # no nine months to take off
    assert sue.quarter_value(r, 2023, "Q1", "OFS", "op") is None and sue.quarter_value(r, 2022, "Q1", "CFS", "op") is None


# ----------------------------------------------------------------------------- when a figure is known
def test_the_change_is_against_the_same_quarter_a_year_before_and_known_after_both_reports():
    r = {**year(2022, 10.0, 20.0, 30.0, 100.0), **year(2023, 14.0, 20.0, 25.0, 100.0)}
    days, rows = sue.timeline(r)
    by_day = dict(zip(days, rows))
    assert by_day["2023-05-15"][1:] == (4.0, 4.0)            # Q1: 14 - 10
    assert by_day["2023-08-15"][1:] == (0.0, 0.0) and by_day["2023-11-15"][1:] == (-5.0, -5.0)
    assert by_day["2024-03-15"][1:] == (1.0, 1.0)            # Q4: (100 - 59) - (100 - 60)
    assert np.isnan(by_day["2022-05-15"][1])                 # no year before: empty, never zero


def test_an_amended_year_before_report_holds_the_figure_back():
    r = {**year(2022, 10.0, 20.0, 30.0, 100.0), **year(2023, 14.0, 20.0, 25.0, 100.0)}
    r[(2022, "Q1")]["CFS"]["rcept"] = "2023-06-20"           # the year-before quarter was amended after the new report
    days, rows = sue.timeline(r)
    assert "2023-05-15" not in days
    assert np.isnan(sue.latest(days, rows, "2023-06-20")[1])                 # the day before it is known: still last year's fourth quarter
    assert sue.latest(days, rows, "2023-06-21") == ("2023-06-20", 4.0, 4.0)


def test_an_amended_old_quarter_never_replaces_a_newer_one():
    r = {**year(2022, 10.0, 20.0, 30.0, 100.0), **year(2023, 14.0, 20.0, 25.0, 100.0)}
    r[(2023, "Q1")]["CFS"]["rcept"] = "2023-12-01"           # Q1 amended after Q3 came out
    days, rows = sue.timeline(r)
    assert rows[days.index("2023-12-01")] == rows[days.index("2023-11-15")]


def test_bases_do_not_mix():
    r = {**year(2022, 10.0, 20.0, 30.0, 100.0), **year(2023, 14.0, 20.0, 25.0, 100.0)}
    r[(2022, "Q1")] = {"OFS": r[(2022, "Q1")]["CFS"]}        # last year's quarter exists only on the separate basis
    days, rows = sue.timeline(r)
    assert np.isnan(rows[days.index("2023-05-15")][1])


def test_usable_the_day_after_and_blank_once_stale():
    days, rows = ["2023-05-15"], [("2023-05-15", 4.0, 4.0)]
    assert sue.latest(days, rows, "2023-05-15") is None and sue.latest(days, rows, "2023-05-16") == rows[0]
    last = (date(2023, 5, 15) + timedelta(days=sue.STALE_DAYS)).isoformat()
    after = (date(2023, 5, 15) + timedelta(days=sue.STALE_DAYS + 1)).isoformat()
    assert sue.latest(days, rows, last) == rows[0] and sue.latest(days, rows, after) is None


# ----------------------------------------------------------------------------- features
def reports_for(px, i, d_op=4.0, d_sales=8.0, back=3):
    known = str(px.dates[i - back])
    y = int(known[:4])
    return {(y - 1, "Q1"): rep(f"{y - 1}-05-15", (10.0, None), (100.0, None)), (y, "Q1"): rep(known, (10.0 + d_op, None), (100.0 + d_sales, None))}


def test_the_divisor_is_the_market_value_when_the_figures_became_known():
    px = small_prices(start=date(2019, 1, 1), sessions=800)
    i, back = 700, 3
    code = px.symbols[0]
    tensor, age = sue.build_features(px, [i], {code: reports_for(px, i, back=back)}, log=QUIET)
    cap = float(px.data["cap"][i - back, 0])
    assert tensor[0, 0].tolist() == pytest.approx([4.0 / cap, 8.0 / cap]) and age[0, 0] == back
    px.data["cap"][i, 0] *= 5                                 # a later price move does not change the signal
    again, _ = sue.build_features(px, [i], {code: reports_for(px, i, back=back)}, log=QUIET)
    assert again[0, 0].tolist() == tensor[0, 0].tolist()
    assert np.isnan(tensor[0, 1:]).all()                      # stocks without reports stay empty


def test_a_receipt_on_the_evaluation_day_an_ineligible_stock_and_a_missing_value_stay_empty():
    px = small_prices(start=date(2019, 1, 1), sessions=800)
    i = 700
    same_day, _ = sue.build_features(px, [i], {px.symbols[0]: reports_for(px, i, back=0)}, log=QUIET)
    assert np.isnan(same_day[0, 0]).all()
    px.data["volume"][i, 1] = 0
    off, _ = sue.build_features(px, [i], {px.symbols[1]: reports_for(px, i)}, log=QUIET)
    assert np.isnan(off[0, 1]).all()
    px.data["cap"][i - 3, 2] = np.nan
    blank, _ = sue.build_features(px, [i], {px.symbols[2]: reports_for(px, i)}, log=QUIET)
    assert np.isnan(blank[0, 2]).all()


def test_a_score_needs_both_signals():
    t = np.full((1, 40, 2), np.nan, dtype=np.float32)
    t[0, :, 0] = np.arange(40)
    t[0, :35, 1] = np.arange(35)
    s = sue.score_of(t)[0]
    assert np.isfinite(s[:35]).all() and np.isnan(s[35:]).all() and s[34] > s[0]


def test_the_residual_takes_an_existing_theme_out():
    rng = np.random.default_rng(3)
    theme = rng.random((4, 200))
    own = rng.random((4, 200))
    score = (0.7 * theme + 0.3 * own) * 100
    left = sue.residual(score, {"theme": theme})
    for n in range(4):
        assert abs(np.corrcoef(left[n], theme[n])[0, 1]) < 1e-8 and np.corrcoef(left[n], own[n])[0, 1] > 0.95
    assert np.isnan(sue.residual(score[:, :40], {"theme": theme[:, :40]})).all()          # too few stocks: no residual
    holes = theme.copy()
    holes[:, :20] = np.nan                                     # a missing control does not drop the stock
    assert np.isfinite(sue.residual(score, {"theme": holes})).all()


# ----------------------------------------------------------------------------- the reading
@pytest.mark.parametrize("verdict,independent,b1,b2,want", [
    ("NO_EVIDENCE", True, True, True, "NO_EVIDENCE"),
    ("WEAK_POSITIVE_EVIDENCE", False, True, True, "A_NOT_INDEPENDENT"),
    ("WEAK_POSITIVE_EVIDENCE", True, True, False, "A_C_AND_B1"),
    ("WEAK_POSITIVE_EVIDENCE", True, False, True, "A_C_AND_B2"),
    ("WEAK_POSITIVE_EVIDENCE", True, False, False, "A_C_ONLY"),
])
def test_the_reading_is_fixed(verdict, independent, b1, b2, want):
    assert sue.reading({"verdict": verdict}, independent, {"b1_top_beats_market": b1, "b2_avoiding_bottom_helps": b2}) == want


def test_condition_c_needs_both_figures():
    assert sue.condition_c({"ic": 0.02, "t": 2.24}) and not sue.condition_c({"ic": 0.019, "t": 9.0})
    assert not sue.condition_c({"ic": 0.05, "t": 2.0}) and not sue.condition_c({"ic": None, "t": None})


def panel(tmp_path, monkeypatch, edge, alike=False):
    """A known effect: returns follow a fixed order of stocks by ``edge`` a session, and the surprise signals carry that order.
    With ``alike`` the existing earnings-change theme carries the same order, so nothing is left once it is taken out."""
    rng = np.random.default_rng(11)
    sessions, stocks = 2300, 80
    px = small_prices(stocks=stocks, sessions=sessions)
    order = np.arange(stocks) / (stocks - 1)
    daily = rng.normal(0.0004, 0.02, (sessions, stocks + 1)) + rng.normal(0, 0.008, (sessions, 1))
    daily[:, :stocks] += edge * (order - 0.5)
    path = 100 * np.exp(np.cumsum(daily, axis=0))
    px.data["adj_close"], px.data["close"], px.data["open"] = path, path, path
    rows = list(range(260, sessions - 1, kr.STEP))
    tensor = np.full((len(rows), stocks + 1, 2), np.nan, dtype=np.float32)
    tensor[:, :stocks, 0], tensor[:, :stocks, 1] = order, order * 2
    age = np.full((len(rows), stocks + 1), 10.0, dtype=np.float32)
    age[1::2] = 45.0
    (tmp_path / sue.FEATURES).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(tmp_path / sue.FEATURES, tensor=tensor, age=age)
    fund = rng.normal(size=(len(rows), stocks + 1, len(kf.SIGNALS))).astype(np.float32)
    if alike:
        for name in kf.THEMES["earnings_change"]:
            fund[:, :stocks, kf.SIGNALS.index(name)] = order
    fund[:, stocks] = np.nan
    np.savez_compressed(tmp_path / kf.FEATURES, tensor=fund)
    price = rng.normal(size=(len(rows), stocks + 1, len(kr.SIGNALS))).astype(np.float32)
    price[:, stocks] = np.nan
    (tmp_path / kr.FEATURES).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(tmp_path / kr.FEATURES, tensor=price)
    monkeypatch.setattr(sue, "_inputs", lambda base: (px, rows, np.ones((len(rows), stocks + 1), dtype=bool)))


def test_the_whole_run_finds_a_planted_independent_effect_and_refuses_a_second_time(tmp_path, monkeypatch):
    panel(tmp_path, monkeypatch, 0.004)
    out = sue.run_once(tmp_path, log=QUIET)
    assert out["reading"] in ("A_C_AND_B1", "A_C_AND_B2") and out["conditions"]["c_independent"] and out["partial"]["ic"] > 0.02
    assert set(out["scores"]) == {"SUE", "SUE_RESIDUAL", "SUE_OP", "SUE_SALES", "SUE_FRESH", "SUE_OLDER", "EARNINGS_CHANGE", "FUND_ONLY", "FUND_WITH_SUE"}
    assert set(out["scores"]["SUE"][sue.PRIMARY]["subsets"]) == {"kospi", "kosdaq", "top300"} and set(out["money_20d"]) == set(sue.PORTFOLIO_PERIODS)
    assert out["scores"]["SUE_FRESH"][sue.PRIMARY]["dates"] < out["scores"]["SUE"][sue.PRIMARY]["dates"]
    assert "size" in out["controls"] and "earnings_change" in out["controls"]
    with pytest.raises(RuntimeError):
        sue.run_once(tmp_path, log=QUIET)


def test_an_effect_the_existing_theme_already_carries_is_not_independent(tmp_path, monkeypatch):
    panel(tmp_path, monkeypatch, 0.004, alike=True)
    out = sue.run_once(tmp_path, log=QUIET)
    assert out["scores"]["SUE"][sue.PRIMARY]["verdict"] == "WEAK_POSITIVE_EVIDENCE"
    assert out["reading"] == "A_NOT_INDEPENDENT" and not out["conditions"]["c_independent"]


def test_the_whole_run_finds_nothing_when_nothing_is_planted(tmp_path, monkeypatch):
    panel(tmp_path, monkeypatch, 0.0)
    assert sue.run_once(tmp_path, log=QUIET)["reading"] == "NO_EVIDENCE"


def test_only_the_primary_horizon_decides(tmp_path, monkeypatch):
    assert sue.PRIMARY == "SWING_20" and sue.HORIZONS[sue.PRIMARY] == 20
