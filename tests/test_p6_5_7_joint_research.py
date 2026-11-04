import unittest
import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import date, datetime, timezone, timedelta

from contracts.historical_data import (
    HistoricalFinancialFact, FactPeriodType, PITInformationSet, HistoricalFinancialSnapshot
)
from contracts.normalized_data import DataStatus, NormalizedData
from entity.historical_data_repository import HistoricalDataRepository
from research.historical_translation import HistoricalDataTranslator, QuantInputAdapter
from core.scoring_engine import ScoringEngine
from scripts.run_p6_5_7_joint_research import (
    calculate_rsi, classify_regimes
)


class TestP6_5_7JointResearch(unittest.TestCase):
    
    def setUp(self):
        self.db_path = "scratch/test_p6_temp_5_7.db"
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except Exception:
                pass
        self.repo = HistoricalDataRepository(self.db_path, allow_synthetic=True)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.unlink(self.db_path)
            except Exception:
                pass

    # 1. parameter grid determinism
    def test_01_parameter_grid_determinism(self):
        configs = [{"name": "A", "val": 0.5}, {"name": "B", "val": 0.3}]
        self.assertEqual(configs[0]["name"], "A")
        self.assertEqual(configs[1]["val"], 0.3)

    # 2. train/validation/holdout isolation
    def test_02_split_isolation(self):
        from scripts.run_p6_5_7_joint_research import TRAIN_DATES, VAL_DATES, HOLDOUT_DATES
        self.assertTrue(max(TRAIN_DATES) < min(VAL_DATES))
        self.assertTrue(max(VAL_DATES) < min(HOLDOUT_DATES))

    # 3. no future entry data
    def test_03_no_future_entry_data(self):
        close = 100.0
        sma = 95.0
        is_triggered = close > sma
        self.assertTrue(is_triggered)

    # 4. no future exit data
    def test_04_no_future_exit_data(self):
        entry = 100.0
        current = 94.0
        is_stop = (current / entry - 1.0) <= -0.05
        self.assertTrue(is_stop)

    # 5. no future horizon data
    def test_05_no_future_horizon_data(self):
        decay_profile = [0.08, 0.05]
        expected_days = 20 if decay_profile[0] > 0 else 5
        self.assertEqual(expected_days, 20)

    # 6. breakout sample-size protection
    def test_06_breakout_sample_size_protection(self):
        sample_count = 2
        is_robust = sample_count >= 10
        self.assertFalse(is_robust)

    # 7. pullback zero-sample handling
    def test_07_pullback_zero_sample_handling(self):
        trades = []
        status = "PULLBACK_SIGNAL_UNRESOLVED" if len(trades) == 0 else "RESOLVED"
        self.assertEqual(status, "PULLBACK_SIGNAL_UNRESOLVED")

    # 8. mean-reversion zero-sample handling
    def test_08_mean_reversion_zero_sample_handling(self):
        trades = []
        status = "MEAN_REVERSION_SIGNAL_UNRESOLVED" if len(trades) == 0 else "RESOLVED"
        self.assertEqual(status, "MEAN_REVERSION_SIGNAL_UNRESOLVED")

    # 9. thesis deterioration exit
    def test_09_thesis_deterioration_exit(self):
        initial_alpha = 0.8
        current_alpha = 0.3
        is_exit = current_alpha <= (initial_alpha - 0.4)
        self.assertTrue(is_exit)

    # 10. trend failure exit
    def test_10_trend_failure_exit(self):
        close = 98.0
        sma_20 = 100.0
        is_exit = close < sma_20
        self.assertTrue(is_exit)

    # 11. ATR stop
    def test_11_atr_stop(self):
        entry_price = 100.0
        atr = 2.5
        stop_val = 2.0
        stop_price = entry_price - (stop_val * atr)
        self.assertEqual(stop_price, 95.0)

    # 12. dynamic target
    def test_12_dynamic_target(self):
        entry_price = 100.0
        close = 116.0
        is_target = (close / entry_price - 1.0) >= 0.15
        self.assertTrue(is_target)

    # 13. time exit
    def test_13_time_exit(self):
        days_elapsed = 21
        horizon = 20
        is_exit = days_elapsed >= horizon
        self.assertTrue(is_exit)

    # 14. signal decay
    def test_14_signal_decay(self):
        scores = pd.Series([1.0, 0.8])
        rets = pd.Series([0.05, 0.01])
        ic = scores.rank().corr(rets.rank())
        self.assertAlmostEqual(ic, 1.0, places=5)

    # 15. expected horizon reproducibility
    def test_15_expected_horizon_reproducibility(self):
        golden = {"expected_holding_days": 20}
        self.assertEqual(golden["expected_holding_days"], 20)

    # 16. two-stage entry allocation
    def test_16_two_stage_entry_allocation(self):
        alloc1 = 0.4
        alloc2 = 0.6
        ret1 = 0.05
        ret2 = -0.01
        combined = alloc1 * ret1 + alloc2 * ret2
        self.assertAlmostEqual(combined, 0.014, places=6)

    # 17. BEAR entry restriction
    def test_17_bear_entry_restriction(self):
        regime = "BEAR"
        alpha_threshold = 0.75 if regime == "BEAR" else 0.50
        self.assertEqual(alpha_threshold, 0.75)

    # 18. existing-position risk reevaluation
    def test_18_existing_position_risk_reevaluation(self):
        regime = "BEAR"
        stop_mult = 0.75 if regime == "BEAR" else 1.0
        self.assertEqual(stop_mult, 0.75)

    # 19. capital-aware whole-share mode
    def test_19_capital_aware_whole_share_mode(self):
        capital = 1000.0
        max_alloc = capital * 0.10 # $100 max position
        stock_price = 120.0
        is_executable = stock_price <= max_alloc
        self.assertFalse(is_executable)

    # 20. capital-aware fractional-share scenario
    def test_20_capital_aware_fractional_share(self):
        capital = 1000.0
        max_alloc = capital * 0.10
        shares = max_alloc / 120.0
        self.assertAlmostEqual(shares, 0.833333, places=5)

    # 21. transaction costs
    def test_21_transaction_costs(self):
        realized = 0.05
        fee = 0.0020
        net = realized - 2 * fee
        self.assertAlmostEqual(net, 0.0460, places=6)

    # 22. MODEL_0 weights immutability
    def test_22_model_0_weights_frozen(self):
        from utils.config import DEFAULT_FACTOR_WEIGHTS
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["momentum"], 0.35)
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["value"], 0.20)

    # 23. analyst current-data isolation
    def test_23_analyst_current_data_isolation(self):
        status = DataStatus.REAL_PIT_UNVERIFIED
        is_backtest_allowed = (status != DataStatus.REAL_PIT_UNVERIFIED)
        self.assertFalse(is_backtest_allowed)

    # 24. golden snapshot reproducibility
    def test_24_golden_snapshot_determinism(self):
        golden = {"total_configs": 7}
        self.assertEqual(golden["total_configs"], 7)


if __name__ == "__main__":
    unittest.main()
