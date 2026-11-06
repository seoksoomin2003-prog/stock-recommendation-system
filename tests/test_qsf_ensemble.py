"""Combined score: signals fixed by theme, alike themes merged without returns, missing stays missing, one run only.  No network."""
import numpy as np
import pytest

from terminal.qsf import research_ensemble as en


def test_every_signal_has_a_source_and_the_count_is_as_planned():
    signals = [s for v in en.THEMES.values() for s in v]
    assert len(signals) == len(set(signals)) == 23 and len(en.THEMES) == 10
    assert set(signals) == set(en.FUND) | set(en.SWING) | set(en.INSIDER)


def test_themes_that_failed_replication_or_add_nothing_are_left_out():
    signals = {s for v in en.THEMES.values() for s in v}
    assert not signals & {"debt_equity", "vcp", "nr7", "pattern_net", "breakout_vol", "rsi2"}


def test_a_theme_needs_half_of_its_signals():
    ranks = {"a": np.array([[0.2, np.nan, np.nan]]), "b": np.array([[0.4, 0.6, np.nan]]), "c": np.array([[np.nan, np.nan, np.nan]]), "d": np.array([[np.nan, 0.8, np.nan]])}
    s = en.theme_scores(ranks, {"t": ("a", "b", "c", "d")})["t"]
    assert s[0, 0] == pytest.approx(0.3) and s[0, 1] == pytest.approx(0.7) and np.isnan(s[0, 2])


def corr_table(pairs, names="abcd"):
    t = {a: {b: 0.0 for b in names} for a in names}
    for a, b, v in pairs:
        t[a][b] = t[b][a] = v
    return t


def test_alike_themes_merge_transitively_and_sign_does_not_matter():
    groups = en.merge_groups(corr_table([("a", "b", 0.6), ("b", "c", -0.5)]))
    assert sorted(groups) == [["a", "b", "c"], ["d"]]


def test_a_correlation_just_under_the_line_stays_apart():
    assert len(en.merge_groups(corr_table([("a", "b", 0.49)]))) == 4


def test_a_missing_correlation_does_not_merge():
    assert len(en.merge_groups(corr_table([("a", "b", None)]))) == 4


def test_groups_weigh_equally_however_many_themes_they_hold():
    scores = {"a": np.array([[1.0]]), "b": np.array([[1.0]]), "c": np.array([[0.0]])}
    assert en.combine(scores, [["a", "b"], ["c"]])[0, 0] == pytest.approx(50)


def test_a_stock_with_too_few_groups_gets_no_score():
    scores = {t: np.array([[0.5 if t < "c" else np.nan]]) for t in "abcd"}
    assert np.isnan(en.combine(scores, [[t] for t in "abcd"])[0, 0])


def test_correlation_of_identical_scores_is_one():
    x = np.arange(40.0).reshape(1, -1)
    c = en.theme_correlation({"a": x, "b": x * 2, "c": -x}, [0])
    assert c["a"]["b"] == pytest.approx(1) and c["a"]["c"] == pytest.approx(-1)


def test_too_few_stocks_give_no_correlation():
    x = np.arange(10.0).reshape(1, -1)
    assert en.theme_correlation({"a": x, "b": x}, [0])["a"]["b"] is None


class Px:
    dates = [f"{y}-{m:02d}-15" for y in range(2013, 2027) for m in range(1, 13)]


def test_earlier_returns_end_before_the_test_starts():
    rows = list(range(len(Px.dates) - 1))
    w = en.windows(Px, rows, 3)
    assert all(Px.dates[rows[n] + 3] < en.TEST_START and Px.dates[rows[n]] >= en.START for n in w["early"])
    assert all(Px.dates[rows[n]] >= en.TEST_START for n in w["test"]) and w["early"] and w["test"]


def test_the_run_is_refused_a_second_time(tmp_path):
    (tmp_path / en.REPORT).parent.mkdir(parents=True)
    (tmp_path / en.REPORT).write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError):
        en.run_once(tmp_path)
