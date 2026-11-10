"""Following-the-screen simulation: selection, the random benchmark, the verdict rule's rates, and the one-run guard."""
import json

import numpy as np
import pytest

from terminal.qsf import sim_picks as sp


class FakePrices:
    """Forward returns fixed per (day, horizon): ``truth`` decides whether the score knows them."""

    def __init__(self, names, days, truth, seed=7):
        self.col = {t: j for j, t in enumerate([*names, "SPY"])}
        self.dates = [f"d{i:04d}" for i in range(max(days) + 1)]
        self.names, self.truth, self.rng = names, truth, np.random.default_rng(seed)
        self.cache = {}

    def forward(self, i, h, cost=0.0):
        if (i, h) not in self.cache:
            noise = self.rng.normal(0, 0.03, len(self.names))
            self.cache[(i, h)] = np.append(noise + self.truth * np.linspace(-0.05, 0.05, len(self.names)), 0.001)
        return self.cache[(i, h)]


def panel(names, days, seed=3):
    rng = np.random.default_rng(seed)
    by_i = {}
    for i in days:
        by_i[i] = [{"i": i, "t": t, "SWING|A": float(j) + rng.random() * 0.1, "LONG_TERM|A": float(j) + rng.random() * 0.1} for j, t in enumerate(names)]
    return by_i


NAMES = [f"T{j:03d}" for j in range(60)]
DAYS = list(range(0, 21 * 40, 21))


def test_top_picks_break_ties_by_ticker():
    got = sp.pick_top(np.array([5.0, 9.0, 9.0, 1.0, 9.0]), ["E", "D", "B", "A", "C"], 3)
    assert [["E", "D", "B", "A", "C"][j] for j in got] == ["B", "C", "D"]


def test_a_score_that_knows_the_returns_stands_out_from_random_screens():
    out = sp.picks_part(panel(NAMES, DAYS), FakePrices(NAMES, DAYS, truth=1.0), step=21, screens=2000)
    p = out["primary"]["SWING"]
    assert p["horizon"] == 5 and p["reading"] == "DISTINCT_FROM_RANDOM" and p["percentile_vs_random"] > 99 and p["mean_excess"] > 0.02
    t = out["tables"]["SWING|5"]
    assert t["days"] == 40 and t["picks"] == 120 and abs(t["random"]["mean"] + out["cost_round_trip"]) < 0.002       # random screens earn the average less the cost
    assert t["reference"]["top10"]["mean_excess"] < t["mean_excess"] and t["reference"]["buy_band_70"]["days"] == 0     # no score reaches 70 here
    assert t["growth"]["holds"] == 40 and t["growth"]["top"]["end"] > t["growth"]["universe_average"]["end"]
    assert out["tables"]["LONG_TERM|63"]["days"] == 14                    # every third day, so the holds do not overlap


def test_a_score_that_knows_nothing_is_not_called_distinct():
    out = sp.picks_part(panel(NAMES, DAYS), FakePrices(NAMES, DAYS, truth=0.0), step=21, screens=2000)
    assert all(v["reading"] == "NOT_DISTINCT_FROM_RANDOM" for v in out["primary"].values())
    assert sp.reading(99.0, 0.01, -0.01) == "NOT_DISTINCT_FROM_RANDOM" and sp.reading(1.0, 0.0, 0.0) == "WORSE_THAN_RANDOM"


def test_days_with_too_few_names_or_no_return_are_left_out():
    by_i = panel(NAMES[:20], DAYS[:5])
    assert sp.day_rows(by_i, FakePrices(NAMES[:20], DAYS[:5], 0.0), "SWING|A", 5, 21) == []


def test_rule_rates_match_the_t_distribution():
    rng = np.random.default_rng(1)
    false_alarm = sp.rule_rate(0.0, 0.1, 12, rng, trials=200_000)
    assert 0.030 < false_alarm < 0.041                                 # one-sided t(11) >= 2 is about 3.5%
    assert sp.rule_rate(0.1, 0.1, 12, rng, trials=20_000) > 0.85 and sp.rule_rate(0.01, 0.1, 12, rng, trials=20_000) < 0.10


def test_power_table_uses_the_observed_spread():
    out = sp.power_part(panel(NAMES, DAYS), FakePrices(NAMES, DAYS, truth=0.0), step=21, trials=5000)
    t = out["tables"]["SWING|20"]
    assert t["days"] == 40 and 0.05 < t["ic_sd"] < 0.25 and set(t["rate"]) == {"0", "0.01", "0.02", "0.03", "0.05"}
    assert t["rate"]["0.05"]["120"] > t["rate"]["0.05"]["12"] > t["rate"]["0"]["12"]


def test_second_run_is_refused(tmp_path):
    out = tmp_path / sp.REPORT
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"status": "REAL"}))
    with pytest.raises(RuntimeError, match="한 번만"):
        sp.run_once(tmp_path)
