"""QSF 1.2 candidate: point-in-time TTM, split handling, sector ranks and the pre-registered statistics.  No network."""
import json

import numpy as np
import pytest

from terminal.qsf import engine, factors, fundamentals, ledger, pit, validate


def row(start, end, val, filed):
    return {"start": start, "end": end, "val": float(val), "filed": filed}


REV = [row("2022-01-01", "2022-12-31", 100, "2023-02-15"), row("2023-01-01", "2023-12-31", 120, "2024-02-15"),
       row("2023-01-01", "2023-03-31", 25, "2023-05-01"), row("2023-01-01", "2023-06-30", 55, "2023-08-01"),
       row("2024-01-01", "2024-03-31", 40, "2024-05-01"), row("2023-01-01", "2023-03-31", 25, "2024-05-01"),
       row("2024-01-01", "2024-06-30", 70, "2024-08-01"), row("2024-04-01", "2024-06-30", 30, "2024-08-01"), row("2023-01-01", "2023-06-30", 55, "2024-08-01")]


def test_ttm_is_fy_plus_ytd_minus_prior_ytd():
    pts = {p["end"]: p["val"] for p in pit.ttm_points(REV, "2024-08-15")}
    assert pts["2024-03-31"] == 120 + 40 - 25
    assert pts["2024-06-30"] == 120 + 70 - 55            # the longest period, never the 3-month one


def test_ttm_uses_only_what_was_filed():
    pts = pit.ttm_points(REV, "2024-06-01")
    assert pts[-1]["end"] == "2024-03-31" and all(p["filed"] <= "2024-06-01" for p in pts)
    assert pit.ttm_points(REV, "2023-01-01") == []


def test_ttm_skips_a_period_it_cannot_build():
    rows = [row("2024-01-01", "2024-03-31", 40, "2024-05-01")]
    assert pit.ttm_points(rows, "2024-06-01") == []


def test_later_restatement_is_invisible_before_its_filing():
    rows = [row("2023-01-01", "2023-12-31", 100, "2024-02-15"), row("2023-01-01", "2023-12-31", 90, "2025-02-15")]
    assert pit.ttm_points(rows, "2024-06-01")[0]["val"] == 100
    assert pit.ttm_points(rows, "2025-06-01")[0]["val"] == 90


def test_yearly_view_compares_one_year_apart():
    pts = [{"end": e, "val": 1.0, "filed": e} for e in ("2022-06-30", "2022-12-31", "2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31", "2024-03-31", "2024-06-30")]
    assert [p["end"] for p in pit._yearly(pts)] == ["2022-06-30", "2023-06-30", "2024-06-30"]


def test_full_extract_keeps_quarters_and_drops_other_forms():
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        {"form": "10-Q", "start": "2024-01-01", "end": "2024-03-31", "val": 40, "filed": "2024-05-01"},
        {"form": "8-K", "start": "2024-01-01", "end": "2024-03-31", "val": 41, "filed": "2024-04-20"},
        {"form": "10-K", "start": "2023-01-01", "end": "2023-12-31", "val": 120, "filed": "2024-02-15"},
        {"form": "10-Q", "start": "2024-03-20", "end": "2024-03-31", "val": 5, "filed": "2024-05-01"}]}}}}}
    got = pit.extract_full(facts)["revenue"]
    assert [r["val"] for r in got] == [120.0, 40.0]


# ---------------------------------------------------------------- splits
def test_split_factor_range():
    s = pit.Splits([("2020-08-31", 4.0), ("2014-06-09", 7.0)])
    assert s.factor("2020-01-01") == 4.0
    assert s.factor("2014-01-01") == 28.0
    assert s.factor("2014-01-01", "2015-01-01") == 7.0
    assert s.factor("2020-08-31") == 1.0                 # the split day itself is already on the new basis
    assert s.factor("2021-01-01") == 1.0


def test_pe_uses_the_price_quoted_at_the_time():
    """A 4-for-1 after the evaluation date: Yahoo's close is a quarter of the quoted price, the filed EPS is not."""
    s = pit.Splits([("2020-08-31", 4.0)])
    rec = {"annual": {"eps": [{"end": "2019-09-28", "val": 12.0, "filed": "2019-10-30"}], "net_income": [{"end": "2019-09-28", "val": 55e9, "filed": "2019-10-30"}],
                      "revenue": [{"end": "2019-09-28", "val": 260e9, "filed": "2019-10-30"}], "shares_avg": [{"end": "2019-09-28", "val": 4.6e9, "filed": "2019-10-30"}]},
           "full": {}}
    a = validate.fund_views(rec, 60.0, s, "2020-01-15", False)["A"]      # quoted 240
    assert a["pe"] == pytest.approx(20.0)
    assert a["market_cap"] == pytest.approx(240 * 4.6e9)


def test_split_after_filing_is_applied_to_shares_and_eps():
    s = pit.Splits([("2020-08-31", 4.0)])
    view = {"shares_avg": [{"end": "2020-06-27", "val": 4.3e9, "filed": "2020-07-31"}], "eps": [{"end": "2020-06-27", "val": 12.0, "filed": "2020-07-31"}]}
    got = pit.adjust_shares(view, "2020-10-01", s)
    assert got["shares_avg"][0]["val"] == 17.2e9 and got["eps"][0]["val"] == 3.0


def test_ttm_eps_comes_from_net_income_and_shares():
    v = pit.with_ttm_eps({"net_income": [{"end": "2024-06-30", "val": 100.0, "filed": "2024-08-01"}], "shares_avg": [{"end": "2024-06-30", "val": 50.0, "filed": "2024-08-01"}]})
    assert v["eps"][0]["val"] == 2.0


# ---------------------------------------------------------------- sector ranks
def test_sector_ranks_within_sector_and_direction():
    funds = {f"T{k}": {"roe": 0.01 * k, "pe": 10.0 + k} for k in range(5)}
    funds["BANK"] = {"roe": 0.5}
    sectors = {**{f"T{k}": "Tech" for k in range(5)}, "BANK": "Financials"}
    got = pit.sector_ranks(funds, sectors)
    assert got["T4"]["roe"] == 1.0 and got["T0"]["roe"] == 0.0
    assert got["T0"]["pe"] == 1.0 and got["T4"]["pe"] == 0.0     # a low PER is good
    assert "roe" not in got["BANK"]                              # too few peers: keeps its absolute anchor


def test_sector_ranks_share_ties_and_skip_negative_pe():
    funds = {f"T{k}": {"roe": 0.1, "pe": 10.0 + k} for k in range(5)}
    funds["T0"]["pe"] = -5.0
    funds["T1"]["pe"] = None
    funds["T5"] = {"roe": 0.2, "pe": 30.0}
    funds["T6"] = {"roe": 0.3, "pe": 31.0}
    got = pit.sector_ranks(funds, {t: "S" for t in funds})
    assert got["T0"].get("pe") is None and got["T1"].get("pe") is None
    assert got["T0"]["roe"] == got["T1"]["roe"] == 2 / 6


def test_factor_prefers_rank_and_is_unchanged_without_one():
    f = {"status": "REAL", "roe": 0.10, "op_margin": 0.10, "source": "x", "filed": "2024-01-01"}
    plain = factors.profitability({"fund": f})
    assert plain["normalized"] == pytest.approx((0.5 + 0.5) / 2)
    ranked = factors.profitability({"fund": {**f, "rel": {"roe": 1.0, "op_margin": 0.0}}})
    assert ranked["normalized"] == pytest.approx(0.5)
    half = factors.profitability({"fund": {**f, "rel": {"roe": 1.0}}})
    assert half["normalized"] == pytest.approx((1.0 + 0.5) / 2)


def test_negative_pe_scores_zero_even_with_ranks():
    f = {"status": "REAL", "pe": -3.0, "pb": None, "fcf_yield": None, "rel": {}, "source": "x", "filed": "2024-01-01"}
    assert factors.valuation({"fund": f})["normalized"] == 0.0


# ---------------------------------------------------------------- statistics
def test_rank_shares_ties():
    assert list(validate.rank(np.array([3.0, 1.0, 1.0, 2.0]))) == [3.0, 0.5, 0.5, 2.0]


def test_newey_west_lowers_t_for_autocorrelated_series():
    rng = np.random.default_rng(1)
    e = rng.normal(0.02, 0.05, 400)
    smooth = np.convolve(e, np.ones(12) / 12, mode="valid")
    plain, nw = validate.newey_west_t(list(smooth), 0), validate.newey_west_t(list(smooth), 12)
    assert nw < plain
    assert validate.newey_west_t([0.1, 0.2], 1) is None


def test_per_date_measures():
    score = np.array([float(k) for k in range(50)])
    ret = score / 100
    d = validate.per_date(score, ret, 0.002)
    assert d["ic"] == pytest.approx(1.0) and d["spread_net"] > 0
    assert d["buy_n"] == 0 and d["buy_excess"] is None


def test_per_date_ignores_missing_and_needs_enough_names():
    score = np.array([float(k) for k in range(40)] + [np.nan] * 5)
    ret = np.array([0.01 * k for k in range(40)] + [0.5] * 5)
    assert validate.per_date(score, ret, 0.0)["n"] == 40
    assert validate.per_date(score[:20], ret[:20], 0.0) is None


def _s(**kw):
    base = {"ic": 0.03, "t": 2.5, "early": {"ic": 0.01, "spread_net": 0.001}, "late": {"ic": 0.02, "spread_net": 0.002}, "buy_excess": 0.001, "buy_dates": 12}
    return {**base, **kw}


def test_verdict_needs_every_condition():
    assert validate.verdict(_s())["verdict"] == "WEAK_POSITIVE_EVIDENCE"
    for bad in ({"ic": 0.019}, {"t": 2.23}, {"t": None}, {"early": {"ic": -0.01, "spread_net": 0.001}}, {"late": {"ic": 0.02, "spread_net": -0.001}},
                {"buy_excess": -0.001}, {"buy_excess": None}, {"buy_dates": 11}):
        assert validate.verdict(_s(**bad))["verdict"] == "NO_EVIDENCE", bad


def test_verdict_of_nothing_is_no_evidence():
    assert validate.verdict({"dates": 0, "status": "UNAVAILABLE"})["verdict"] == "NO_EVIDENCE"


def test_summarize_splits_halves():
    rows = [{"date": f"2020-01-{k:02d}", "ic": 0.1 if k <= 5 else -0.1, "n": 100, "spread_net": 0.01, "buy_excess": None, "buy_n": 0} for k in range(1, 11)]
    s = validate.summarize(rows, 20)
    assert s["early"]["ic"] == pytest.approx(0.1) and s["late"]["ic"] == pytest.approx(-0.1) and s["ic"] == pytest.approx(0.0)


# ---------------------------------------------------------------- prices
def _prices(tmp_path):
    n = 12
    d = {x: np.full((n, 2), np.nan) for x in validate.FIELDS}
    base = np.arange(100.0, 100.0 + n)
    for x in ("open", "high", "low", "close", "adj_close"):
        d[x][:, 0] = base
    d["adj_close"][:, 0] = base * 0.5                # dividends adjust the basis
    d["volume"][:, 0] = 1000.0
    for x in ("open", "close", "adj_close"):
        d[x][:, 1] = 50.0
    d["close"][6, 1] = np.nan
    d["adj_close"][6, 1] = np.nan
    dates = [f"2024-01-{k + 1:02d}" for k in range(n)]
    f = tmp_path / "p.npz"
    np.savez_compressed(f, dates=np.array(dates), symbols=np.array(["AAA", "SPY"]), **d)
    return validate.Prices(f)


def test_forward_matches_the_ledger_outcome(tmp_path):
    p = _prices(tmp_path)
    path = p.bars(0, 0, 12)
    want = ledger.outcome(path, path, "2024-01-03", 5, 0.0)["gross"]
    assert p.forward(2, 5)[0] == pytest.approx(want)


def test_forward_is_nan_when_unmatured_or_missing(tmp_path):
    p = _prices(tmp_path)
    assert np.isnan(p.forward(10, 5)).all()
    assert np.isnan(p.forward(1, 5)[1])                # missing close on the exit day stays missing


def test_bars_never_turn_missing_into_zero(tmp_path):
    p = _prices(tmp_path)
    assert len(p.bars(1, 0, 12)) == 11
    assert p.bars(1, 0, 1)[0]["high"] is None


def test_bucket_table_reports_what_happened_per_band():
    score = np.array([85.0, 85.0, 30.0, np.nan])
    ret = np.array([0.10, -0.05, 0.02, 0.9])
    bench = np.full(4, 0.01)
    t = validate.bucket_table(score, ret, bench, ret - 0.02, 0.0)
    assert t["80-100"]["n"] == 2 and t["80-100"]["win_rate"] == 0.5 and t["80-100"]["mean_net"] == pytest.approx(0.025)
    assert t["80-100"]["beat_bench_rate"] == 0.5 and t["0-40"]["n"] == 1
    assert t["70-80"]["n"] == 0 and t["70-80"]["win_rate"] is None    # no data stays empty


def test_facts_download_resumes_and_reports_failures(tmp_path):
    def fetch(cik):
        if cik == "2":
            raise ConnectionError("x")
        return {"facts": {}}
    r = validate.download_facts({"A": "1", "B": "2"}, tmp_path, fetch=fetch)
    assert r["failed"] == [("B", "ConnectionError")] and (tmp_path / "A.json.gz").exists()
    r = validate.download_facts({"A": "1"}, tmp_path, fetch=lambda c: 1 / 0)
    assert r["failed"] == []


def test_usable_requires_score_no_gate_no_short_domain():
    ok = {"score": 50.0, "gates": [], "short_domains": []}
    assert validate.usable(ok)
    assert not validate.usable({**ok, "score": None})
    assert not validate.usable({**ok, "gates": [{"code": "LOW_LIQUIDITY"}]})
    assert not validate.usable({**ok, "short_domains": ["TECHNICAL"]})


def test_live_score_does_not_import_the_candidate():
    import terminal.qsf.service as svc
    assert "pit" not in vars(svc) and "validate" not in vars(svc) and "pit" not in vars(engine)
