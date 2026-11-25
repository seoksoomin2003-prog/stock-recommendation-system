"""BT-1 (2026-11-25, user instruction): the score of today on the stored history, once per market, described as a rerun of used
windows (reports/QSF_BACKTEST_CURRENT_PROTOCOL.md).  The statistics are checked on made-up prices.  No network, no stored price."""
import json
from pathlib import Path

import numpy as np
import pytest

from terminal.qsf import backtest_current as bt, config

ROOT = Path(__file__).resolve().parents[1]
M = 40


class Px:
    """``M`` stocks whose daily return is their rank's edge plus an optional common wobble; SPY is their equal-weight mean."""

    def __init__(self, n=320, edge=0.004, noise=0.0, seed=1):
        rng = np.random.default_rng(seed)
        self.dates = [f"D{k:04d}" for k in range(n)]
        self.symbols = [f"S{j:02d}" for j in range(M)] + ["SPY"]
        self.col = {s: j for j, s in enumerate(self.symbols)}
        self.skill = np.linspace(-1.0, 1.0, M)
        self.daily = np.zeros((n, M)) + edge * self.skill / 21 + (rng.normal(0.0, noise, (n, M)) if noise else 0.0) + 0.0004

    def forward(self, i, h, cost=0.0):
        out = np.full(M + 1, np.nan)
        if i + h < len(self.dates):
            out[:M] = np.prod(1 + self.daily[i + 1:i + h + 1], axis=0) - 1 - cost
            out[M] = out[:M].mean()
        return out


def scored(px, score=lambda j, i: 50 + 30 * np.linspace(-1.0, 1.0, M)[j], last=280):
    recs = [{"i": i, "t": f"S{j:02d}", "sector": None, "SWING": score(j, i), "LONG_TERM": score(j, i)} for i in range(0, last, bt.HOLD) for j in range(M)]
    return {"px": px, "records": recs, "bench": lambda i, h: float(px.forward(i, h)[M]), "bench_name": "made-up index"}


def test_a_score_that_orders_returns_reads_as_rank_and_money_and_its_fifths_rise():
    res = bt.analyse(scored(Px(edge=0.02)), "US")              # an edge well above the round-trip cost (a smaller one ranks right and still loses to the index)
    s = res["strategies"]["SWING"]
    f = s["horizons"]["20"]["fifths"]
    assert f["monotone"] and f["top_minus_bottom"] > 0 and f["top_minus_index"] > 0 and f["band"]["minus_index"] > 0
    assert s["horizons"]["20"]["rank"]["ic"] > 0.9 and s["reading"] in ("RANK_AND_MONEY", "MONEY_ONLY")      # a rank that never varies has no t: the label follows the conditions as they are
    acc = s["accounts"]["accounts"]
    assert acc["TOP_FIFTH"]["cagr_pct"] > acc["ALL_SCORED"]["cagr_pct"] > 0 and acc["TOP_FIFTH"]["beat_index_share"] == 1.0
    assert res["evaluation_days"] == 14 and res["cost_round_trip_pct"] == config.round_trip_cost("US") * 100


def test_a_score_against_returns_and_a_score_of_noise_are_read_as_what_they_are():
    against = bt.analyse(scored(Px(), score=lambda j, i: 50 - 30 * np.linspace(-1.0, 1.0, M)[j]), "US")["strategies"]["SWING"]
    assert against["reading"] == "NEITHER" and against["horizons"]["20"]["fifths"]["top_minus_bottom"] < 0 and against["accounts"]["accounts"]["TOP_FIFTH"]["excess_per_period_pct"] < 0
    rng = np.random.default_rng(3)
    table = rng.uniform(30, 80, (400, M))
    noise = bt.analyse(scored(Px(edge=0.0, noise=0.01), score=lambda j, i: float(table[i, j])), "US")["strategies"]["SWING"]
    assert noise["reading"] != "RANK_AND_MONEY" and abs(noise["horizons"]["20"]["rank"]["ic"]) < 0.1


def test_an_account_pays_the_cost_on_what_changed_hands_and_waits_in_cash_without_a_band():
    px = Px(edge=0.0)                                            # every stock earns the same: an account's return is the market's less its cost
    same = bt.portfolios(px, bt._by_day(scored(px)["records"]), "SWING", 0.01, lambda i, h: float(px.forward(i, h)[M]))["accounts"]
    assert same["TOP_FIFTH"]["mean_turnover"] == pytest.approx(1 / 14)          # bought once, never changed
    assert same["INDEX"]["cagr_pct"] > same["TOP_FIFTH"]["cagr_pct"] > same["INDEX"]["cagr_pct"] - 1.2      # one round trip of 1% over 14 months
    low = bt.portfolios(px, bt._by_day(scored(px, score=lambda j, i: 40.0 + j * 0.1)["records"]), "SWING", 0.01, lambda i, h: float(px.forward(i, h)[M]))["accounts"]
    assert low["BUY_BAND"]["cagr_pct"] == pytest.approx(0.0) and low["BUY_BAND"]["mean_names"] == 0.0           # no score of 70: cash, never a made-up return
    m = bt._metrics(np.array([0.1, -0.2, 0.05, 0.05, 0.05, 0.05]))
    assert m["max_drawdown_pct"] == pytest.approx(-20.0) and m["worst_period_pct"] == pytest.approx(-20.0) and m["periods"] == 6
    assert bt._metrics(np.array([0.01] * 3)) == {"periods": 3}                                                    # too short to say anything


def test_a_day_with_too_few_names_or_no_matured_return_is_left_out():
    px = Px(n=60)
    res = bt.analyse(scored(px, last=60), "KR")
    assert res["strategies"]["LONG_TERM"]["horizons"]["252"]["rank"] == {"status": "UNAVAILABLE", "dates": 0}     # nothing matured: said, never zero
    few = {"px": px, "records": [r for r in scored(px, last=60)["records"] if r["t"] < "S10"], "bench": lambda i, h: 0.0, "bench_name": "x"}
    assert bt.analyse(few, "KR")["strategies"]["SWING"]["horizons"]["20"]["rank"]["dates"] == 0


def test_a_report_on_file_is_never_run_again_and_the_run_touches_no_record(tmp_path):
    target = tmp_path / bt.REPORT["US"]
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps({"status": "REAL", "market": "US", "marker": 1}), encoding="utf-8")
    assert bt.run(tmp_path, "US")["marker"] == 1                                 # no scoring, no price: the stored report as it is
    code = (ROOT / "terminal" / "qsf" / "backtest_current.py").read_text(encoding="utf-8")
    assert "ledger" not in code.replace("no ledger", "") and "live_forward" not in code and "MODEL_RANK_E" not in code
    doc = (ROOT / "reports" / "QSF_BACKTEST_CURRENT_PROTOCOL.md").read_text(encoding="utf-8")
    assert "이 결과는 새 증거가 아니다" in doc and "한 번만" in doc and "가설이다" in doc
    import app
    assert "backtest-current" in app.QSF_ACTIONS and "backtest-current" in app.QSF_HANDLERS
    assert bt.NOTE.startswith("이 결과는 지금 공식을 이미 여러 번 본 과거 구간에 다시 적용한 것입니다")
