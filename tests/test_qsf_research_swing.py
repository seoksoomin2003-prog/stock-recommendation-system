"""The swing research must read only past rows, keep gaps empty, and refuse test data in development or a second test."""
import json

import numpy as np
import pytest

from terminal.qsf import research_swing as rs


def _panel(rows=400, cols=6, seed=3):
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0005, 0.015, (rows, cols))
    adj = 100 * np.exp(np.cumsum(r, axis=0))
    d = {"adj_close": adj.copy(), "close": adj.copy(), "high": adj * 1.01, "low": adj * 0.99, "open": adj.copy(), "volume": rng.uniform(1e6, 2e6, (rows, cols))}
    return d


def test_price_factors_are_the_full_preregistered_set():
    f = rs.price_features(_panel(), 350, 0)
    assert set(f) | {"rev_sector_1m", "pattern_net", "sue"} == set(rs.FACTORS)
    assert len(rs.FACTORS) == 24


def test_price_factors_do_not_read_after_the_row():
    d = _panel()
    base = rs.price_features(d, 350, 0)
    changed = {k: v.copy() for k, v in d.items()}
    for v in changed.values():
        v[351:] = 1e9
    after = rs.price_features(changed, 350, 0)
    for k in base:
        np.testing.assert_array_equal(base[k], after[k], err_msg=k)


def test_price_factors_match_hand_values():
    d = _panel()
    f = rs.price_features(d, 350, 0)
    a = d["adj_close"][:, 1]
    assert f["rev_1m"][1] == pytest.approx(a[350] / a[329] - 1)
    assert f["mom_12_1"][1] == pytest.approx(a[329] / a[98] - 1)
    assert f["ma200_ratio"][1] == pytest.approx(a[350] / a[151:351].mean())
    assert f["high_52w"][1] == pytest.approx(d["close"][350, 1] / d["high"][99:351, 1].max())
    assert f["boll_z"][1] == pytest.approx((a[350] - a[331:351].mean()) / a[331:351].std())
    assert f["max_21"][1] == pytest.approx((a[330:351] / a[329:350] - 1).max())


def test_missing_prices_stay_empty_not_zero():
    d = _panel()
    d["adj_close"][:, 2] = np.nan
    d["close"][:, 2] = d["high"][:, 2] = d["low"][:, 2] = d["volume"][:, 2] = np.nan
    f = rs.price_features(d, 350, 0)
    for k, v in f.items():
        assert np.isnan(v[2]), k
    assert np.isfinite(f["rev_1m"][1])


def test_rsi2_extremes():
    up = np.linspace(100, 130, 60)[:, None]
    down = np.linspace(130, 100, 60)[:, None]
    assert rs.rsi2(up, 59)[0] == pytest.approx(100)
    assert rs.rsi2(down, 59)[0] == pytest.approx(0)


def test_market_residual_removes_the_market():
    rng = np.random.default_rng(1)
    m = rng.normal(0, 0.01, 200)
    x = np.column_stack([m, 2 * m])
    beta, e = rs._residual(x, m, 100)
    assert beta[1] == pytest.approx(2)
    assert np.abs(e[:, 1]).max() < 1e-9


def _shape(points, tail=3, base=None):
    """A path through ``points`` at even spacing, ending ``tail`` sessions after the last level so the turn can be read."""
    legs = []
    span = (rs.PATTERN_WINDOW - tail) // (len(points) - 1)
    for a, b in zip(points, points[1:]):
        legs.append(np.linspace(a, b, span, endpoint=False))
    path = np.concatenate(legs + [[points[-1]], np.linspace(points[-1], points[-1] * (0.97 if points[-1] > points[-2] else 1.03), tail)])
    if len(path) < rs.PATTERN_WINDOW:
        path = np.concatenate([np.full(rs.PATTERN_WINDOW - len(path), path[0]), path])
    return path[-rs.PATTERN_WINDOW:]


def test_head_and_shoulders_is_bearish_and_its_mirror_bullish():
    hs = _shape([90, 110, 100, 125, 100, 110])
    assert rs.pattern_signal(hs) == -1
    ihs = _shape([120, 90, 100, 75, 100, 90])
    assert rs.pattern_signal(ihs) == 1


def test_uneven_shoulders_are_no_pattern():
    assert rs.pattern_signal(_shape([90, 110, 100, 125, 100, 130])) != -1


def test_stale_pattern_is_ignored():
    hs = _shape([90, 110, 100, 125, 100, 110])
    drifted = np.concatenate([hs[10:], np.linspace(hs[-1], hs[-1] * 0.9, 10)])
    assert rs.pattern_signal(drifted) == 0


def test_pattern_needs_a_full_window():
    assert rs.pattern_signal(np.linspace(100, 110, 10)) is None
    w = np.linspace(100, 110, rs.PATTERN_WINDOW)
    w[5] = np.nan
    assert rs.pattern_signal(w) is None


def _ni(val_by_q, filed_gap=40):
    """Quarterly values in the shape filings report them: year-to-date within a year, then the full year."""
    from datetime import date, timedelta
    ends = {0: (3, 31), 1: (6, 30), 2: (9, 30), 3: (12, 31)}
    rows, ytd = [], 0.0
    for k, v in enumerate(val_by_q):
        y, q = 2015 + k // 4, k % 4
        ytd = float(v) if q == 0 else ytd + float(v)
        end = date(y, *ends[q])
        rows.append({"start": date(y, 1, 1).isoformat(), "end": end.isoformat(), "val": ytd, "filed": (end + timedelta(days=filed_gap)).isoformat()})
    return rows


def test_sue_uses_only_filed_quarters_and_expires():
    rows = _ni([10, 11, 12, 13, 11, 12, 13, 14, 12, 13, 14, 15, 13, 14, 15, 16, 30])
    seen = rs.sue_at(rows, "2019-05-15")
    before = rs.sue_at(rows, "2019-05-05")
    assert seen is not None and seen > 2
    assert before is None or before < seen
    assert rs.sue_at(rows, "2019-10-01") is None
    assert rs.sue_at(rows[:4], "2016-03-01") is None
    assert rs.sue_point(rows[:-1], "2019-05-15") == rs.sue_point(rows, "2019-05-05")


def test_rank_direction_and_gaps():
    n = 40
    t = np.full((1, n, len(rs.FACTORS)), np.nan, dtype=np.float32)
    t[0, :, rs.FACTORS.index("rev_1m")] = np.arange(n)
    t[0, :, rs.FACTORS.index("mom_12_1")] = np.arange(n)
    r = rs.rank_tensor(t)
    assert r[0, 0, rs.FACTORS.index("rev_1m")] == 1.0
    assert r[0, 0, rs.FACTORS.index("mom_12_1")] == 0.0
    assert np.isnan(r[0, 0, rs.FACTORS.index("vcp")])


def test_composite_needs_half_of_the_factors():
    row = np.full((2, len(rs.FACTORS)), np.nan, dtype=np.float32)
    a, b, c = rs.FACTORS.index("rev_1m"), rs.FACTORS.index("vcp"), rs.FACTORS.index("sue")
    row[0, [a, b]] = 0.5, 1.0
    row[1, a] = 1.0
    s = rs.composite(row, ["rev_1m", "vcp", "sue"])
    assert s[0] == pytest.approx(75)
    assert np.isnan(s[1])


def test_sector_demean_keeps_unknown_and_thin_groups_empty():
    v = np.array([1.0] * 6 + [9.0] * 2 + [5.0])
    groups = np.array(["A"] * 6 + ["B"] * 2 + ["?"])
    out = rs.sector_demean(v, groups, np.ones(9, dtype=bool))
    assert np.isnan(out[6]) and np.isnan(out[8])
    assert out[0] == pytest.approx(0)


class _Px:
    def __init__(self, dates):
        self.dates = dates


def test_development_refuses_test_dates():
    px = _Px(["2021-12-20", "2021-12-31", "2022-01-03"])
    with pytest.raises(ValueError):
        rs.select(np.zeros((1, 1, len(rs.FACTORS))), px, [0], [0], 2)


def test_eligible_applies_the_filters():
    d = _panel(rows=330, cols=3)
    d["close"][:, 1] = 2.0
    d["volume"][:, 2] = 1.0
    assert rs.eligible(d, 329, [0, 1, 2]) == [0]


def test_second_test_is_refused(tmp_path):
    target = tmp_path / rs.TEST_REPORT
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({}), encoding="utf-8")
    with pytest.raises(RuntimeError):
        rs.test_once(tmp_path)
