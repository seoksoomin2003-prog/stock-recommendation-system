"""Portfolio risk: today's weights over the past year; cash earns 0; short histories are listed, not filled."""
import math

import numpy as np
import pytest

from terminal import portfolio_risk as pr


def path(rets, start=100.0, first="2025-01-01"):
    from datetime import date, timedelta
    d0, v, out = date.fromisoformat(first), start, [{"date": first, "close": start, "adj_close": start}]
    for i, r in enumerate(rets):
        v *= 1 + r
        out.append({"date": (d0 + timedelta(days=i + 1)).isoformat(), "close": v, "adj_close": v})
    return out


def test_one_stock_twice_the_market_at_half_weight():
    rng = np.random.default_rng(1)
    m = rng.normal(0, 0.01, 260)
    bench, stock = path(m), path(2 * m)
    out = pr.analyse({"A": 0.5}, {"A": stock}, bench, 1000.0)
    assert out["status"] == "REAL" and out["days"] == 252 and out["invested"] == 0.5
    assert out["beta"] == pytest.approx(1.0) and out["holdings"][0]["beta"] == pytest.approx(2.0) and out["holdings"][0]["risk_share"] == pytest.approx(1.0)
    assert out["volatility"] == pytest.approx(out["benchmark_volatility"], rel=1e-9)        # half of a twice-as-volatile stock
    p = np.array(m[-252:])
    assert out["var95"] == pytest.approx(-np.percentile(p, 5)) and out["var95_amount"] == pytest.approx(1000 * out["var95"])
    assert out["es95"] >= out["var95"] and out["effective_n"] == pytest.approx(1.0) and out["correlation"]["matrix"] == [[pytest.approx(1.0)]]


def test_two_stocks_risk_shares_sum_to_one_and_short_history_is_left_out():
    rng = np.random.default_rng(2)
    m, a, b = (rng.normal(0, s, 260) for s in (0.01, 0.02, 0.01))
    out = pr.analyse({"A": 0.3, "B": 0.3, "NEW": 0.2}, {"A": path(a), "B": path(b), "NEW": path(b[:30])}, path(m), None)
    assert out["short_history"] == ["NEW"] and [h["ticker"] for h in out["holdings"]] == ["A", "B"]        # the riskier one first
    assert sum(h["risk_share"] for h in out["holdings"]) == pytest.approx(1.0) and out["var95_amount"] is None
    assert out["effective_n"] == pytest.approx(2.0) and -1 <= out["avg_correlation"] <= 1
    assert out["max_drawdown"] <= 0 and out["worst_20d"] <= out["return_1y"] + 1


def test_unavailable_cases():
    m = path([0.0] * 260)
    assert pr.analyse({"A": 0.5}, {"A": path([0.0] * 50)}, m, 1.0) == {"status": "UNAVAILABLE", "reason": "NO_HISTORY", "short_history": ["A"]}
    assert pr.analyse({"A": 0.5}, {"A": m}, path([0.0] * 20), 1.0)["reason"] == "NO_BENCHMARK"
    flat = pr.analyse({"A": 0.5}, {"A": m}, m, 1.0)
    assert flat["status"] == "REAL" and flat["beta"] is None and flat["volatility"] == 0 and math.isnan(flat["holdings"][0]["volatility"]) is False
