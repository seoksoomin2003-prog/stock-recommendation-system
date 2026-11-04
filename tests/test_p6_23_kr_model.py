"""P6-23: independent KR model KR-EXP (offline, synthetic data)."""
import json

import numpy as np
import pandas as pd
import pytest

from tests import kr_fakes as F
from markets.kr import KR_MODEL_STATUS, model
from markets.kr.pipeline import KRContext, run_kr_evaluate, run_kr_scan


def _adj(n_tickers=30, n=200, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2026-01-01", periods=n)
    return pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, n_tickers)), axis=0)), index=idx,
                        columns=[f"{i:06d}" for i in range(n_tickers)])


def test_model_is_experimental_and_weights_fixed_equal():
    assert KR_MODEL_STATUS == "EXPERIMENTAL"
    assert set(model.ACTIVE_FACTORS) <= set(model.FACTOR_CANDIDATES)
    assert sum(model.WEIGHTS.values()) == pytest.approx(1.0)
    assert len(set(model.WEIGHTS.values())) == 1


def test_factor_formulas():
    adj = _adj()
    r = model.raw_factors(adj, list(model.FACTOR_CANDIDATES))
    t = adj.columns[0]
    assert r.loc[t, "MOM_6_1"] == pytest.approx(adj[t].iloc[-22] / adj[t].iloc[-127] - 1)
    assert r.loc[t, "REV_1M"] == pytest.approx(-(adj[t].iloc[-1] / adj[t].iloc[-22] - 1))
    lr = np.log(adj[t] / adj[t].shift()).iloc[-60:]
    assert r.loc[t, "LOWVOL_60"] == pytest.approx(-lr.std(ddof=1))
    assert r.loc[t, "TREND_50"] == pytest.approx(adj[t].iloc[-1] / adj[t].iloc[-50:].mean() - 1)


def test_no_look_ahead_future_rows_do_not_change_factors():
    adj = _adj()
    a = model.raw_factors(adj.iloc[:150])
    b = model.raw_factors(adj.iloc[:150].copy())
    fut = adj.copy()
    fut.iloc[150:] *= 5
    c = model.raw_factors(fut.iloc[:150])
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(a, c)


def test_insufficient_history_is_nan_never_filled():
    adj = _adj(n=100)
    r = model.raw_factors(adj)
    assert r["MOM_6_1"].isna().all() and r["REV_1M"].notna().all()


def test_standardize_winsorizes_and_handles_constant():
    raw = pd.DataFrame({"MOM_6_1": list(range(99)) + [10_000.0]}, index=[str(i) for i in range(100)])
    z = model.standardize(raw)
    s = raw["MOM_6_1"]
    unwinsorized_max = ((s - s.mean()) / s.std(ddof=0)).max()            # ~9.9 for the outlier
    assert abs(z["MOM_6_1"].mean()) < 1e-9 and z["MOM_6_1"].max() < unwinsorized_max / 2
    const = model.standardize(pd.DataFrame({"x": [1.0] * 5}))
    assert const["x"].isna().all()


def test_standardize_against_reference_is_not_influenced_by_point():
    ref = pd.DataFrame({f: np.random.default_rng(2).normal(size=50) for f in model.ACTIVE_FACTORS})
    p1 = pd.DataFrame({f: [0.5] for f in model.ACTIVE_FACTORS}, index=["X"])
    p2 = pd.DataFrame({f: [1e9] for f in model.ACTIVE_FACTORS}, index=["X"])
    z1, z2 = model.standardize_against(p1, ref), model.standardize_against(p2, ref)
    assert np.isfinite(z2.values).all() and (z2.values > z1.values).all()   # clipped at reference 99th pct


def test_rank_deterministic_tie_break_by_key():
    s = pd.Series({"b": 1.0, "a": 1.0, "c": 2.0})
    r = model.rank(s, pd.Series({"a": "KR:K:a", "b": "KR:K:b", "c": "KR:K:c"}))
    assert list(r.index) == ["c", "a", "b"] and list(r["rank"]) == [1, 2, 3]


def test_portfolio_industry_cap_whole_shares_and_cash():
    tick = [f"{i:06d}" for i in range(15)]
    ranked = model.rank(pd.Series(np.linspace(2, 1, 15), index=tick), pd.Series(tick, index=tick))
    info = pd.DataFrame({"industry": ["A"] * 6 + ["B", "C", "D"] * 3}, index=tick)
    closes = pd.Series(70_000.0, index=tick)
    p = model.portfolio(ranked, info, 10_000_000, closes)
    inds = [info.loc[x["ticker"], "industry"] for x in p["positions"]]
    assert inds.count("A") == model.MAX_PER_INDUSTRY and len(p["positions"]) == model.TOP_N and p["complete"]
    assert all(isinstance(x["shares"], int) and x["shares"] == 14 for x in p["positions"])
    assert p["cash_krw"] == pytest.approx(10_000_000 - 10 * 14 * 70_000)
    assert {s["reason"] for s in p["industry_cap_skips"]} == {"INDUSTRY_CAP"}


def _ctx(tmp_path, **kw):
    return KRContext(fetch_kind=F.fake_kind(), provider_factory=F.provider_factory(F.FakeDownload(**kw)),
                     now=F.NOW, base_dir=tmp_path)


def test_scan_end_to_end_offline_is_deterministic(tmp_path):
    a = run_kr_scan(10_000_000, ctx=_ctx(tmp_path / "a"))
    b = run_kr_scan(10_000_000, ctx=_ctx(tmp_path / "b"))
    assert a["recommendation_status"] == "REAL RECOMMENDATION" and a["model_status"] == "EXPERIMENTAL"
    assert a["currency"] == "KRW" and a["market"] == "KR"
    assert [p["ticker"] for p in a["recommendations"]] == [p["ticker"] for p in b["recommendations"]]
    assert a["universe"]["members"] == 300 and a["provider"]["basis"] == "PROXY_CLOSE_X_VOLUME"
    rd = tmp_path / "a" / "runs" / "KR" / a["run_id"]
    for n in ("run_manifest.json", "validation_result.json", "candidate_flow.json", "universe_snapshot.csv.gz",
              "report.md"):
        assert (rd / n).exists(), n
    assert "EXPERIMENTAL" in (rd / "report.md").read_text(encoding="utf-8")
    assert not (tmp_path / "a" / "runs" / a["run_id"]).exists()          # never in the US runs dir


def test_gating_happens_before_normalisation(tmp_path):
    # corrupt one member's latest bars: it must be quarantined and must not affect others' z-scores
    bad = "100005.KS"
    def stale(df):
        return df.iloc[:-5]
    a = run_kr_scan(10_000_000, ctx=_ctx(tmp_path / "a"))
    b = run_kr_scan(10_000_000, ctx=_ctx(tmp_path / "b", mutate={bad: stale}))
    fa = json.loads((tmp_path / "a/runs/KR" / a["run_id"] / "candidate_flow.json").read_text())["candidates"]
    fb = json.loads((tmp_path / "b/runs/KR" / b["run_id"] / "candidate_flow.json").read_text())["candidates"]
    if "100005" in fb:   # still a member through the 70-day universe window -> quarantined in history gate
        assert fb["100005"]["final_status"] == "QUARANTINED"
    assert all(f["final_status"] in ("SCORED", "QUARANTINED") for f in fb.values())
    assert "100005" not in [p["ticker"] for p in b["recommendations"]]


def test_bounded_scan_is_never_real_recommendation(tmp_path):
    v = run_kr_scan(10_000_000, limit=50, ctx=_ctx(tmp_path))
    assert v["validation_scope"] == "bounded" and v["recommendation_status"] != "REAL RECOMMENDATION"
    assert v["tracking"]["recorded_observations"] == 0 and "NOT_FULL_UNIVERSE" in v["tracking"]["reasons"]


def test_kr_provider_failure_fails_closed(tmp_path):
    def nothing(symbols, start, end):
        return pd.DataFrame()
    ctx = KRContext(fetch_kind=F.fake_kind(), provider_factory=F.provider_factory(nothing), now=F.NOW,
                    base_dir=tmp_path)
    with pytest.raises(RuntimeError):
        run_kr_scan(10_000_000, ctx=ctx)
    st = next(d for d in (tmp_path / "runs" / "KR").iterdir() if d.is_dir()) / "execution_status.json"
    assert json.loads(st.read_text())["state"] == "FAILED"


def test_evaluate_verdicts(tmp_path):
    ctx = _ctx(tmp_path)
    scan = run_kr_scan(10_000_000, ctx=ctx)
    snap = pd.read_csv(tmp_path / "runs/KR" / scan["run_id"] / "universe_snapshot.csv.gz", dtype={"ticker": str})
    outside = snap[snap["status"] == "NOT_SELECTED"]["ticker"].iloc[0]
    member = scan["recommendations"][0]["ticker"]
    run = run_kr_evaluate([member, outside, "999999"], ctx=_ctx(tmp_path))
    v = {r["input"]: r for r in run["results"]}
    assert v["999999"]["verdict"] == "NOT_FOUND"
    assert v[member]["verdict"] == "IN_UNIVERSE_SCORED" and v[member]["rank"] == 1
    o = v[outside]
    assert o["verdict"] == "OUTSIDE_UNIVERSE_SCORED_AGAINST_REFERENCE" and 0 <= o["percentile_vs_universe"] <= 1
    assert o["universe_status"] == "NOT_SELECTED"
    assert run["mode"] == "kr_direct_evaluation"
    # evaluation never adds tracking observations
    from markets.kr import tracking as kt
    assert len(kt.observations(ctx.tracking_dir)) == 10


def test_unaffordable_position_is_flagged_not_resized():
    tick = [f"{i:06d}" for i in range(10)]
    ranked = model.rank(pd.Series(np.linspace(2, 1, 10), index=tick), pd.Series(tick, index=tick))
    info = pd.DataFrame({"industry": list("ABCDEFGHIJ")}, index=tick)
    closes = pd.Series(50_000.0, index=tick)
    closes[tick[2]] = 1_115_000.0
    p = model.portfolio(ranked, info, 10_000_000, closes)
    assert [x["ticker"] for x in p["positions"]] == tick            # selection unchanged by capital
    assert p["unfunded_positions"] == [tick[2]] and p["positions"][2]["shares"] == 0
    assert all(x["funded"] for i, x in enumerate(p["positions"]) if i != 2)
