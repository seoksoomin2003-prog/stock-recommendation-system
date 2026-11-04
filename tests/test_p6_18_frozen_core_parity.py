"""P6-18 frozen-core numerical parity (behavioural, not source-text inspection).

The golden file was produced by ``scripts/generate_frozen_core_baseline.py``
from the unmodified P6-11B engines BEFORE any P6-18 change.
"""
import json
import math
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.decision_engine import DecisionEngine
from core.ranking_engine import RankingEngine
from scripts.generate_frozen_core_baseline import compute
from utils.config import DECISION_SETTINGS, DEFAULT_FACTOR_WEIGHTS, PORTFOLIO_SETTINGS

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "frozen_core_baseline_p6_18.json"
NOW = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)


def cand(i, **kw):
    c = {"security_id": f"S{i}", "ticker": f"T{i}", "close": 100.0, "volume": 1_000_000.0, "alpha": 1.0 - i / 100,
         "atr": 2.0, "ema20": 95.0, "entry_readiness": 1.0, "alpha_percentile": 1.0 - i / 100, "sector": "Energy",
         "data_status": "REAL", "price_status": "REAL", "volume_status": "REAL", "fundamental_status": "REAL"}
    c.update(kw)
    return c


class TestFrozenCoreParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = json.loads(GOLDEN.read_text())["result"]
        cls.now = compute()

    def assertNested(self, a, b, path=""):
        if isinstance(a, dict):
            self.assertEqual(set(a), set(b), path)
            for k in a:
                self.assertNested(a[k], b[k], f"{path}.{k}")
        elif isinstance(a, list):
            self.assertEqual(len(a), len(b), path)
            for i, (x, y) in enumerate(zip(a, b)):
                self.assertNested(x, y, f"{path}[{i}]")
        elif isinstance(a, float) or isinstance(b, float):
            if a is None or b is None:
                self.assertEqual(a, b, path)
            else:
                self.assertTrue(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12), f"{path}: {a} != {b}")
        else:
            self.assertEqual(a, b, path)

    def test_factor_matrix_parity(self):
        self.assertNested(self.golden["factor_matrix"], self.now["factor_matrix"], "factor_matrix")

    def test_standardization_and_scores_parity(self):
        self.assertNested(self.golden["standardized"], self.now["standardized"], "standardized")
        self.assertNested(self.golden["scores"], self.now["scores"], "scores")

    def test_model_rank_e_parity(self):
        self.assertEqual(self.golden["model_rank_e_order"], self.now["model_rank_e_order"])
        self.assertNested(self.golden["model_rank_e_combined"], self.now["model_rank_e_combined"], "rank_e")

    def test_decision_parity_all_regimes_and_capitals(self):
        self.assertNested(self.golden["decisions"], self.now["decisions"], "decisions")

    def test_frozen_constants(self):
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS, {"momentum": 0.35, "quality": 0.25, "value": 0.20, "low_volatility": 0.20})
        self.assertEqual(PORTFOLIO_SETTINGS["max_individual_weight"], 0.30)
        self.assertEqual(PORTFOLIO_SETTINGS["max_sector_exposure"], 0.40)
        self.assertEqual(DECISION_SETTINGS, {"entry_1_weight": 0.40, "entry_2_weight": 0.60, "hard_stop_atr_multiplier": 2.0,
                                             "expected_horizon_days": 30, "reentry_cooldown_days": 3, "bear_alpha_threshold": 0.75})


class TestFrozenBoundaries(unittest.TestCase):
    def test_liquidity_boundary_exact(self):
        e = DecisionEngine()
        self.assertFalse(e._check_data_quality(cand(0, volume=499_999.0)))
        self.assertTrue(e._check_data_quality(cand(0, volume=500_000.0)))
        self.assertFalse(e._check_data_quality(cand(0, volume=0.0)))
        self.assertFalse(e._check_data_quality(cand(0, volume=float("nan"))))

    def test_bear_threshold_exact_75th_percentile(self):
        items = [cand(i, alpha_percentile=p) for i, p in enumerate([0.95, 0.9, 0.85, 0.8, 0.75, 0.7499])]
        d = DecisionEngine().evaluate_portfolio(NOW, 100_000, "BEAR", items)
        self.assertEqual([s.ticker for s in d.top5], ["T0", "T1", "T2", "T3", "T4"])
        self.assertNotIn("T5", [s.ticker for s in d.top5 + d.watchlist5])
        d_bull = DecisionEngine().evaluate_portfolio(NOW, 100_000, "BULL", [cand(i, alpha_percentile=p) for i, p in
                                                                          enumerate([0.95, 0.9, 0.85, 0.8, 0.75, 0.7499])])
        self.assertIn("T5", [s.ticker for s in d_bull.watchlist5])

    def test_model_rank_e_formula(self):
        c = cand(0, alpha=0.8, entry_readiness=1.0, volatility=0.05, confidence=0.5, liquidity_score=2.0, close=50.0)
        out = RankingEngine().calculate_model_rank_e([c], capital=1000.0)[0]
        self.assertAlmostEqual(out["combined_score"], (0.8 * 0.6 + 1.0 * 0.4) * 1.0 - 0.05 * 0.5 - 0.0, places=12)
        expensive = RankingEngine().calculate_model_rank_e([cand(1, alpha=0.8, close=200.0)], capital=1000.0)[0]
        self.assertAlmostEqual(expensive["combined_score"], 0.8 * 0.6 + 0.4 - 0.02 * 0.1 - 0.1, places=12)

    def test_sector_cap_and_sizing(self):
        items = [cand(i, sector="Technology") for i in range(4)] + [cand(i, sector="Energy") for i in range(4, 8)]
        d = DecisionEngine().evaluate_portfolio(NOW, 10_000, "BULL", items)
        self.assertEqual(sum(1 for s in d.top5 if s.sector == "Technology"), 2)
        self.assertAlmostEqual(d.sector_exposure["Technology"], 0.40)
        for s in d.top5:
            self.assertAlmostEqual(s.target_weight, 0.20)
            self.assertAlmostEqual(s.entry_1_weight, 0.08)
            self.assertAlmostEqual(s.entry_2_weight, 0.12)
            self.assertAlmostEqual(s.hard_stop, 100.0 - 2 * 2.0)
            self.assertEqual(s.expected_horizon_days, 30)

    def test_final_validity_requires_five(self):
        d = DecisionEngine().evaluate_portfolio(NOW, 10_000, "BULL", [cand(i) for i in range(4)])
        self.assertEqual(len(d.top5), 4)
        self.assertEqual(d.data_quality, "DATA-INCOMPLETE / NO VALID RECOMMENDATION")
        d = DecisionEngine().evaluate_portfolio(NOW, 10_000, "BULL", [])
        self.assertEqual(d.data_quality, "DATA-INCOMPLETE / NO VALID RECOMMENDATION")
        self.assertEqual(d.top5, [])

    def test_mock_never_enters_portfolio(self):
        items = [cand(i) for i in range(5)] + [cand(9, alpha=99.0, alpha_percentile=1.0, data_status="MOCK")]
        d = DecisionEngine().evaluate_portfolio(NOW, 10_000, "BULL", items)
        self.assertNotIn("T9", [s.ticker for s in d.top5 + d.watchlist5])

    def test_exit_hierarchy(self):
        e = DecisionEngine()
        pos = {"security_id": "S", "ticker": "T", "lifecycle_state": "FULL_POSITION", "hard_stop": 90.0,
               "trailing_stop": 85.0, "entry_date": "2026-01-02"}
        self.assertEqual(e.evaluate_existing_position(NOW, pos, {"close": 89.0, "ema20": 95.0, "atr": 2.0}).exit_reason, "HARD_STOP")
        self.assertEqual(e.evaluate_existing_position(NOW, pos, {"close": 94.0, "ema20": 95.0, "atr": 2.0}).exit_reason, "THESIS_INVALIDATION")


if __name__ == "__main__":
    unittest.main()
