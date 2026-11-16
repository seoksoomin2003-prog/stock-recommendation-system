"""The market state test (reports/QSF_MARKET_STATE_PROTOCOL.md).  All offline, made-up data."""
import json

import numpy as np
import pytest

from terminal.qsf import factors, market_state as ms


def _walk(n, seed, drift=0.0003, vol=0.01):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(drift, vol, n)))


# ---------------------------------------------------------------------- the signals are the live formulas
@pytest.mark.parametrize("vix", [9.0, 12.0, 18.4, 23.5, 30.0, 35.0, 60.0])
def test_the_vix_signal_is_the_live_factor(vix):
    live = factors.vix_regime({"regime": {"vix": {"status": "REAL", "value": vix, "percentile": 0.5, "source": "x", "date": "2026-01-02"}}})
    assert live["normalized"] == pytest.approx(float(ms._ramp(np.array([vix]), *ms.VIX_RAMP)[0]))
    assert float(ms._ramp(np.array([23.5]), *ms.VIX_RAMP)[0]) == pytest.approx(ms.MID)


def test_trend_and_breadth_are_the_live_factors():
    c = _walk(400, 1)
    stocks = np.column_stack([_walk(400, s) for s in range(2, 40)])
    i = 399
    idx = {"status": "REAL", "symbol": "SPY", "close": float(c[i]), "ma50": float(c[i - 49:i + 1].mean()), "ma200": float(c[i - 199:i + 1].mean()), "source": "x", "date": "d"}
    share = float(ms.share_above(stocks)[i])
    live_kr = factors.index_trend({"regime": {"index": idx}})["normalized"]
    live_us = factors.index_trend_breadth({"regime": {"index": idx, "breadth": {"status": "REAL", "value": share}}})["normalized"]
    live_br = factors.breadth({"regime": {"breadth": {"status": "REAL", "value": share, "n": 38, "source": "x", "date": "d"}}})["normalized"]
    assert ms.trend(c)[i] == pytest.approx(live_kr)
    us = ms.us_signals([str(k) for k in range(400)], c, stocks, {str(k): 20.0 for k in range(400)})
    v = float(ms._ramp(np.array([20.0]), *ms.VIX_RAMP)[0])
    assert us["V_US"][i] == pytest.approx(v) and us["R_US"][i] == pytest.approx((5 * v + 7 * live_us) / 12)
    assert float(ms._ramp(np.array([share]), *ms.BREADTH_RAMP)[0]) == pytest.approx(live_br)
    assert np.isnan(ms.trend(c)[:199]).all() and np.isfinite(ms.trend(c)[199])


def test_a_signal_reads_nothing_after_its_own_day():
    n, i = 420, 300
    c, stocks = _walk(n, 3), np.column_stack([_walk(n, s) for s in range(10, 80)])
    cap = np.abs(np.column_stack([_walk(n, s) for s in range(100, 170)]))
    vix = {str(k): 15.0 + (k % 17) for k in range(n)}
    dates = [str(k) for k in range(n)]
    us, kr = ms.us_signals(dates, c, stocks, vix), ms.kr_signals(c, stocks, cap)
    c2, s2, cap2, vix2 = c.copy(), stocks.copy(), cap.copy(), dict(vix)
    c2[i + 1:] *= 9.0
    s2[i + 1:] *= 0.1
    cap2[i + 1:] = cap2[i + 1:][:, ::-1]
    for k in range(i + 1, n):
        vix2[str(k)] = 80.0
    us2, kr2 = ms.us_signals(dates, c2, s2, vix2), ms.kr_signals(c2, s2, cap2)
    for a, b in ((us["R_US"], us2["R_US"]), (us["V_US"], us2["V_US"]), (kr["R_KR"], kr2["R_KR"])):
        assert np.array_equal(a[:i + 1], b[:i + 1], equal_nan=True) and not np.array_equal(a[i + 1:], b[i + 1:], equal_nan=True)


def test_breadth_rules_and_the_largest_stocks():
    n = 260
    a = np.column_stack([np.linspace(1, 2, n), np.linspace(2, 1, n), np.concatenate([np.full(100, np.nan), np.linspace(1, 3, n - 100)])])
    assert ms.share_above(a)[n - 1] == pytest.approx(2 / 3)                      # the US rule averages the days a stock has
    wide = np.column_stack([a] + [np.linspace(1, 2, n)] * 60)
    assert ms.share_above(wide, whole_window=True)[n - 1] == pytest.approx(61 / 62)   # the short-history stock is left out
    assert np.isnan(ms.share_above(a, whole_window=True)[n - 1])                 # under 50 stocks: no breadth
    cap = np.array([[5.0, np.nan, 9.0, 1.0, 0.0]])
    assert ms.top_by_cap(cap, 2)(0).tolist() == [True, False, True, False, False]
    assert ms.top_by_cap(cap, 9)(0).tolist() == [True, False, True, True, False]


# ---------------------------------------------------------------------- outcomes and the judgement
def test_the_outcome_is_the_twenty_sessions_after_the_next_close():
    idx = np.arange(1.0, 61.0)
    o = ms.outcomes(idx)
    assert o["ret"][0] == pytest.approx(idx[21] / idx[1] - 1) and o["mdd"][0] == 0.0
    assert np.isfinite(o["ret"][60 - 22]) and np.isnan(o["ret"][60 - 21:]).all()
    idx2 = idx.copy()
    idx2[0] = 500.0                                                              # the signal day's own close is not in its outcome
    assert ms.outcomes(idx2)["ret"][0] == o["ret"][0]
    dip = np.array([10.0, 10, 12, 9, 11] + [11.0] * 30)
    assert ms.outcomes(dip)["mdd"][0] == pytest.approx(9 / 12 - 1)


def test_the_difference_and_its_t_value():
    rng = np.random.default_rng(5)
    d = rng.random(4000) < 0.5
    y = rng.normal(0, 1, 4000) + 0.2 * d
    r = ms.nw_diff(y, d, lag=0)
    plain = (y[d].mean() - y[~d].mean()) / np.sqrt(y[d].var(ddof=1) / d.sum() + y[~d].var(ddof=1) / (~d).sum())
    assert r["diff"] == pytest.approx(y[d].mean() - y[~d].mean()) and r["t"] == pytest.approx(plain, rel=0.02)
    run = np.repeat(rng.random(200) < 0.5, 20)                                   # a state that lasts: fewer independent days, a smaller t
    yy = np.repeat(rng.normal(0, 1, 200), 20) + 0.3 * run
    assert abs(ms.nw_diff(yy, run, lag=20)["t"]) < abs(ms.nw_diff(yy, run, lag=0)["t"]) / 2
    assert ms.nw_diff(y[:3], d[:3]) is None and ms.nw_diff(y, np.ones(4000, dtype=bool)) is None


def _made(n, gap_ret, gap_vol, seed=7):
    rng = np.random.default_rng(seed)
    sig = np.where(rng.random(n) < 0.6, 0.8, 0.2)
    good = sig >= ms.MID
    return sig, {"ret": rng.normal(0.01, 0.02, n) + gap_ret * good, "vol": np.abs(rng.normal(0.01, 0.002, n)) + gap_vol * ~good, "mdd": -np.abs(rng.normal(0.03, 0.01, n))}


def test_verdicts():
    sig, o = _made(3000, 0.02, 0.004)
    j = ms.judge(sig, o)
    assert (j["return_verdict"], j["risk_verdict"]) == ("RETURN_FOLLOWS", "RISK_HIGHER_WHEN_ADVERSE")
    assert j["favourable"]["days"] + j["adverse"]["days"] == 3000 and j["return"]["all"]["diff"] == pytest.approx(0.02, abs=0.004)
    sig, o = _made(3000, -0.02, 0.0)
    j = ms.judge(sig, o)
    assert (j["return_verdict"], j["risk_verdict"]) == ("RETURN_OPPOSITE", "RISK_NOT_DISTINCT")
    sig, o = _made(3000, 0.0, 0.0)
    assert ms.judge(sig, o)["return_verdict"] == "RETURN_NOT_DISTINCT"
    sig, o = _made(3000, 0.02, 0.004)
    o["ret"][1500:] -= 0.04 * (sig[1500:] >= ms.MID)                              # the later half goes the other way: not both halves
    assert ms.judge(sig, o)["return_verdict"] == "RETURN_NOT_DISTINCT"
    sig, o = _made(150, 0.02, 0.004)
    assert ms.judge(sig, o)["return_verdict"] == "NOT_TESTED"
    sig, o = _made(3000, 0.02, 0.004)
    sig[:10] = np.nan
    o["ret"][-10:] = np.nan
    assert ms.judge(sig, o)["days"] == 2980


# ---------------------------------------------------------------------- figures only
def test_the_gate_changes_at_the_next_close():
    idx = np.array([100.0, 100, 100, 110, 121, 121, 121])
    sig = np.array([0.9, 0.9, 0.1, 0.1, 0.9, np.nan, np.nan])
    g = ms.gate(idx, sig, 0.01)
    # days 2..6 hold by the signals of days 0..4: in, in, out, out, in.  Day 3 (+10%) is earned, day 4 (+10%) is not.
    assert g["always_in"]["days"] == 5 and g["invested_share"] == pytest.approx(3 / 5) and g["switches"] == 2
    level = lambda s: (1 + s["annual_return"]) ** (s["days"] / 252)             # noqa: E731
    assert level(g["gate"]) == pytest.approx(1.10) and level(g["always_in"]) == pytest.approx(1.21)
    assert level(g["gate_after_cost"]) == pytest.approx(1.10 * 0.99 * 0.99, rel=1e-3)
    assert ms.gate(idx, np.full(7, np.nan), 0.0) == {"days": 0}


def test_follow_counts_stocks_inside_the_same_window():
    n = ms.MA_LONG - 1 + 2 * ms.H + 1
    idx = np.ones(n)
    t0 = ms.MA_LONG - 1
    idx[t0 + ms.H:] = 1.1
    idx[t0 + 2 * ms.H:] = 0.9
    a = np.ones((n, 60))
    a[t0 + ms.H:, :45] = 1.2                                                      # the index rose: 45 of 60 stocks rose
    a[t0 + 2 * ms.H:, :] = a[t0 + ms.H] * 0.8
    a[t0 + 2 * ms.H:, :6] = a[t0 + ms.H, :6] * 1.05                               # the index fell: 6 of 60 rose
    f = ms.follow(idx, a)
    assert f["index_up"]["windows"] == 1 and f["index_up"]["stocks_up_share"] == pytest.approx(0.75)
    assert f["index_down"]["windows"] == 1 and f["index_down"]["stocks_up_share"] == pytest.approx(0.10)


def test_one_run_only(tmp_path):
    calls = []

    def load(base):
        calls.append(1)
        n = 900
        c = _walk(n, 11)
        stocks = np.column_stack([_walk(n, s) for s in range(20, 90)])
        dates = [f"d{k:04d}" for k in range(n)]
        return {"market": "US", "dates": dates, "index": c, "stocks": stocks, "members": None, "signals": ms.us_signals(dates, c, stocks, {d: 12.0 + (k % 30) for k, d in enumerate(dates)})}
    doc = ms.run_once(tmp_path, log=lambda *_: None, loaders={"US": load})
    assert doc["status"] == "REAL" and set(doc["markets"]["US"]["signals"]) == {"R_US", "V_US"}
    s = doc["markets"]["US"]["signals"]["R_US"]
    assert s["first_day"] == "d0199" and s["last_day"] == f"d{900 - 22:04d}" and s["gate"]["cost_per_switch"] == pytest.approx(0.00201, abs=1e-5)
    assert set(doc["markets"]["US"]["states"]) == {"UP_CALM", "UP_ROUGH", "DOWN"}
    stored = json.loads((tmp_path / ms.REPORT).read_text(encoding="utf-8"))
    again = ms.run_once(tmp_path, log=lambda *_: None, loaders={"US": load})
    assert again["status"] == "ALREADY_RUN" and again["run_at"] == stored["run_at"] and len(calls) == 1
