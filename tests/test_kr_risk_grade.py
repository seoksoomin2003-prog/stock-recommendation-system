"""The Korean risk grade: inputs read nothing after their day, the readings are computed as the protocol says, and the test runs once."""
import json

import numpy as np
import pytest

from terminal.qsf import kr_risk_grade as rg, research_kr as kr


def panel(days=420, stocks=120, seed=3):
    """Stocks whose daily swing differs and persists: stock j moves about (0.5 + j / 40) percent a day."""
    rng = np.random.default_rng(seed)
    sigma = 0.005 + np.arange(stocks) / 4000.0
    r = rng.normal(0, 1, (days, stocks)) * sigma
    close = 10000 * np.cumprod(1 + r, axis=0)
    spread = np.abs(rng.normal(0, 1, (days, stocks))) * sigma * close
    d = {"close": close, "adj_close": close.copy(), "open": np.vstack([close[:1], close[:-1]]), "high": close + spread, "low": close - spread,
         "volume": np.full((days, stocks), 1e5), "value": np.tile(5e9 + np.arange(stocks)[::-1] * 1e8, (days, 1)), "cap": np.tile(1e11 + np.arange(stocks)[::-1] * 1e9, (days, 1)),
         "watch": np.zeros((days, stocks), dtype=bool), "symbols": np.array([f"{j:05d}0" for j in range(stocks - 1)] + [kr.MARKET])}
    d = {k: (v.astype(np.float32) if v.dtype == float else v) for k, v in d.items()}
    return d, [f"d{n:04d}" for n in range(days)]


def test_inputs_and_score_read_nothing_after_their_day():
    d, _ = panel()
    i = 300
    ok = kr.eligible(d, i)
    before = rg.score(d, i, ok).copy()
    for k in ("close", "open", "high", "low", "value", "volume"):
        d[k][i + 1:] = d[k][i + 1:] * 3
    assert np.array_equal(before, rg.score(d, i, ok), equal_nan=True)
    assert np.isnan(before[-1]) and np.isfinite(before[:-1]).all()          # the market column is never graded


def test_a_stock_that_swings_more_scores_higher_and_the_grade_limits_are_the_protocol_ones():
    d, _ = panel()
    sc = rg.score(d, 300, kr.eligible(d, 300))[:-1]
    assert np.corrcoef(np.arange(len(sc)), sc)[0, 1] > 0.8 and sc.min() >= 0 and sc.max() <= 100
    assert [rg.grade(v) for v in (0, 39.9, 40, 69.9, 70, 89.9, 90, 100)] == ["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH", "VERY_HIGH", "VERY_HIGH"]
    assert rg.grade(None) is None and rg.grade(float("nan")) is None


def test_a_stock_needs_three_of_the_four_inputs():
    d, _ = panel()
    d["value"][:, 5] = np.nan                    # one input gone: still scored from three
    d["high"][:, 6], d["value"][:, 6] = np.nan, np.nan
    ok = np.ones(d["close"].shape[1], dtype=bool)
    sc = rg.score(d, 300, ok)
    assert np.isfinite(sc[5]) and np.isnan(sc[6])


def test_targets_start_at_the_next_open_and_a_stock_gone_early_closes_at_its_last_trade():
    d, _ = panel()
    i = 300
    d["close"][i + 6:, 7] = np.nan
    d["low"][i + 6:, 7] = np.nan
    t = rg.targets(d, i)
    entry = float(d["open"][i + 1, 7])
    assert t["ret"][7] == pytest.approx(float(d["close"][i + 5, 7]) / entry - 1, rel=1e-5)
    assert t["drawdown"][7] == pytest.approx(float(d["low"][i + 1:i + 6, 7].min()) / entry - 1, rel=1e-5)
    assert np.isnan(t["vol"][7])                 # five changes are too few for a swing reading
    assert t["ret"][3] == pytest.approx(float(d["close"][i + 20, 3]) / float(d["open"][i + 1, 3]) - 1, rel=1e-5)


def test_the_largest_stocks_are_taken_by_market_value_among_the_eligible():
    d, _ = panel()
    ok = kr.eligible(d, 300)
    m = rg.members(d, 300, ok, size=10)
    assert m.sum() == 10 and m[:10].all() and not m[-1]
    ok[0] = False
    assert not rg.members(d, 300, ok, size=10)[0] and rg.members(d, 300, ok, size=10)[10]


def test_the_readings_pass_when_swings_persist_and_the_verdict_needs_all_three():
    d, dates = panel(days=700)
    got = rg.evaluate(d, dates)
    ref = got["reference"]
    assert 10 < ref["days"] <= len(rg.eval_rows(dates)) and ref["volatility"]["mean"] > 0.5 and ref["checks"]["volatility"] is True
    assert ref["drawdown"]["top"] < ref["drawdown"]["bottom"] < 0 and ref["checks"]["drawdown"] is True
    assert set(ref["grades"]) <= set(rg.GRADE_NAMES) and ref["grades"]["VERY_HIGH"]["vol"] > ref["grades"]["LOW"]["vol"]
    assert ref["pair_win"] == pytest.approx(0.5 + ref["volatility"]["mean"] / 3.14159265, abs=1e-6)
    assert got["verdict"] == ("RISK_GRADE_SUPPORTED" if all(got["primary"]["checks"].values()) else "RISK_GRADE_NOT_SUPPORTED")
    flat = [{"date": "a", "n": 100, "ic_vol": 0.5, "ic_ret": 0.0, "loss_top": 0.1, "loss_all": 0.1, "loss_gap": 0.0, "drawdown_top": -0.1, "drawdown_bottom": -0.1, "drawdown_gap": 0.0, "grades": {}}] * 6
    assert rg.summarize(flat)["checks"] == {"volatility": False, "big_loss": False, "drawdown": False}          # no spread between days: no t-value, no pass


def test_the_test_runs_once(tmp_path, monkeypatch):
    d, dates = panel(days=420)

    class Px:
        data, dates_ = d, dates
    Px.dates = dates
    calls = []
    monkeypatch.setattr(rg.kr, "_load", lambda base: calls.append(1) or Px)
    first = rg.run_once(tmp_path, log=lambda m: None)
    assert first["status"] == "REAL" and (tmp_path / rg.REPORT).exists() and rg.supported(tmp_path) == (first["verdict"] == "RISK_GRADE_SUPPORTED")
    again = rg.run_once(tmp_path, log=lambda m: None)
    assert again["status"] == "ALREADY_RUN" and again["ran_at"] == first["ran_at"] and len(calls) == 1
    assert rg.supported(tmp_path / "nowhere") is False


def test_day_grades_name_every_scored_stock():
    d, _ = panel()
    g = rg.day_grades(d, 300)
    assert len(g) == d["close"].shape[1] - 1 and kr.MARKET not in g and g["000000"]["grade"] in rg.GRADE_NAMES and 0 <= g["000000"]["score"] <= 100
