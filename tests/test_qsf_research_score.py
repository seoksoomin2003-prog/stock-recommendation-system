"""Research score: factor definitions, the development wall and the one-shot test.  No network."""
import numpy as np
import pytest

from terminal.qsf import research_score as rs, validate


class Px:
    def __init__(self, n=600, symbols=("A", "B", "SPY")):
        import datetime as dt
        d0 = dt.date(2019, 1, 1)
        self.dates = [(d0 + dt.timedelta(days=k * 2)).isoformat() for k in range(n)]
        self.symbols = list(symbols)
        self.col = {s: j for j, s in enumerate(symbols)}

    def forward(self, i, h):
        if self.dates[i + h] >= rs.TEST_START:
            raise AssertionError("test-period return was read")
        return np.zeros(len(self.symbols))


def test_every_factor_has_a_declared_direction():
    assert len(rs.FACTORS) == 17 and set(rs.FACTORS) == set(rs.GOOD_HIGH)


def test_fund_features_compute_and_stay_empty_when_missing():
    y = lambda *v: [{"end": f"{2020 + k}-12-31", "val": float(x), "filed": f"{2021 + k}-02-01"} for k, x in enumerate(v)]    # noqa: E731
    view = {"shares_avg": y(10), "eps": y(1, 2), "net_income": y(20), "equity": y(100), "assets": y(100, 200), "ocf": y(30), "capex": y(5), "gross_profit": y(40), "revenue": y(80, 100), "op_income": y(10)}
    f = rs.fund_features(view, 20.0)
    assert f["earnings_yield"] == pytest.approx(2 / 20) and f["book_yield"] == pytest.approx(100 / 200) and f["fcf_yield"] == pytest.approx(25 / 200)
    assert f["accruals"] == pytest.approx((20 - 30) / 200) and f["asset_growth"] == pytest.approx(1.0) and f["gp_assets"] == pytest.approx(0.2) and f["rev_growth"] == pytest.approx(0.25)
    assert rs.fund_features({}, 20.0)["roe"] is None and rs.fund_features({}, 20.0)["accruals"] is None


def test_negative_equity_gives_no_roe():
    y = lambda v: [{"end": "2020-12-31", "val": float(v), "filed": "2021-02-01"}]    # noqa: E731
    assert rs.fund_features({"net_income": y(5), "equity": y(-1)}, 1.0)["roe"] is None


def test_price_features_read_nothing_after_the_date():
    n = 300
    adj = np.linspace(100, 200, n)
    high, close = adj.copy(), adj.copy()
    a = rs.price_features(adj, high, close, 280)
    adj2, high2, close2 = adj.copy(), high.copy(), close.copy()
    adj2[281:], high2[281:], close2[281:] = 9999.0, 9999.0, 9999.0
    assert rs.price_features(adj2, high2, close2, 280) == a
    assert a["mom_12_1"] == pytest.approx(adj[259] / adj[28] - 1) and a["rev_1m"] == pytest.approx(adj[280] / adj[259] - 1)


def test_short_history_gives_empty_values():
    a = np.linspace(1, 2, 100)
    f = rs.price_features(a, a, a, 99)
    assert f["mom_12_1"] is None and f["vol_252"] is None and f["high_52w"] is None


def test_percentile_direction_groups_and_missing():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, np.nan, 9.0])
    g = np.array(["S"] * 6 + ["T"])
    hi, lo = rs.percentile(x, True, g), rs.percentile(x, False, g)
    assert hi[4] == 1.0 and lo[4] == 0.0 and np.isnan(hi[5]) and np.isnan(hi[6])     # one peer in T: no rank


def test_composite_needs_half_the_factors():
    chosen = ["roe", "op_margin", "gp_assets", "vol_252"]
    row = np.full((3, len(rs.FACTORS)), np.nan)
    idx = [rs.FACTORS.index(f) for f in chosen]
    row[0, idx] = [1.0, 0.5, 0.0, 0.5]
    row[1, idx[:2]] = [1.0, 0.5]
    row[2, idx[0]] = 1.0
    s = rs.composite(row, chosen)
    assert s[0] == pytest.approx(50) and s[1] == pytest.approx(75) and np.isnan(s[2])


def test_development_rows_end_before_the_test_period():
    px = Px()
    rows = list(range(0, 580, 21))
    for h in (20, 252):
        picks = rs.dev_rows(px, rows, h) if h < 500 else []
        assert picks and all(px.dates[rows[n] + h] < rs.TEST_START for n in picks)


def test_select_refuses_test_data():
    px = Px()
    rows = list(range(0, 580, 21))
    late = [n for n, i in enumerate(rows) if px.dates[i + 20] >= rs.TEST_START]
    ranks = np.zeros((len(rows), 3, len(rs.FACTORS)))
    with pytest.raises(ValueError):
        rs.select(ranks, px, rows, late[:1], 20)


def test_test_rows_start_in_the_test_period():
    px = Px()
    rows = list(range(0, 580, 21))
    picks = rs.test_rows(px, rows, 20)
    assert picks and all(px.dates[rows[n]] >= rs.TEST_START for n in picks)


def test_selection_rule_needs_t_and_both_halves(monkeypatch):
    """A factor with a strong signal is chosen; one positive only in one half is not."""
    rng = np.random.default_rng(3)
    syms = [f"S{k}" for k in range(60)]
    px = Px(symbols=tuple(syms + ["SPY"]))
    rows = list(range(0, 300, 21))
    k_good, k_half = rs.FACTORS.index("roe"), rs.FACTORS.index("op_margin")
    ranks = np.full((len(rows), len(px.symbols), len(rs.FACTORS)), np.nan)
    fwd = {i: rng.normal(0, 0.05, len(px.symbols)) for i in rows}
    for n, i in enumerate(rows):
        ranks[n, :, k_good] = fwd[i] + rng.normal(0, 0.02, len(px.symbols))
        ranks[n, :, k_half] = fwd[i] * (1 if n < len(rows) // 2 else -1)
    px.forward = lambda i, h: fwd[i]
    res = rs.select(ranks, px, rows, list(range(len(rows))), 5)
    assert res["chosen"] == ["roe"]


def test_second_test_run_is_refused(tmp_path):
    (tmp_path / "reports" / "qsf").mkdir(parents=True)
    (tmp_path / "reports" / "qsf" / "QSF_RESEARCH_SCORE_TEST.json").write_text("{}")
    with pytest.raises(RuntimeError):
        rs.test_once(tmp_path)


def test_verdict_uses_the_top_fifth():
    s = {"ic": 0.03, "t": 2.5, "early": {"ic": 0.01, "spread_net": 0.001}, "late": {"ic": 0.02, "spread_net": 0.002}}
    assert rs.test_verdict({**s, "top_excess": 0.001})["verdict"] == "WEAK_POSITIVE_EVIDENCE"
    assert rs.test_verdict({**s, "top_excess": -0.001})["verdict"] == "NO_EVIDENCE"
    assert rs.test_verdict(s)["verdict"] == "NO_EVIDENCE"
