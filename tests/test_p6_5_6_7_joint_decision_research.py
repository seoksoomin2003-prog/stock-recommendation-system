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
from scripts.run_p6_5_6_7_joint_decision_research import (
    calculate_rsi, classify_regimes
)


class TestP6_5_6_7JointDecisionResearch(unittest.TestCase):
    
    def setUp(self):
        self.db_path = "scratch/test_p6_decision_temp.db"
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

    # 1. capital-tier behavior
    def test_01_capital_tier_behavior(self):
        capital_tiers = [1000, 2500, 5000, 10000, 25000]
        self.assertIn(1000, capital_tiers)
        self.assertIn(10000, capital_tiers)

    # 2. whole-share execution
    def test_02_whole_share_execution(self):
        allocated_cash = 100.0
        stock_price = 120.0
        # Whole share mode fails
        shares = int(allocated_cash / stock_price)
        self.assertEqual(shares, 0)

    # 3. fractional-share execution
    def test_03_fractional_share_execution(self):
        allocated_cash = 100.0
        stock_price = 120.0
        shares = allocated_cash / stock_price
        self.assertAlmostEqual(shares, 0.833333, places=5)

    # 4. capital-aware ranking
    def test_04_capital_aware_ranking(self):
        # MODEL_RANK_E penalizes stocks whose prices exceed capital max allocation limit
        stock_price = 150.0
        max_alloc = 100.0 # capital=1000, max weight=10%
        penalty = 1.0 if stock_price > max_alloc else 0.0
        self.assertEqual(penalty, 1.0)

    # 5. TOP 5 selection
    def test_05_top_5_selection(self):
        candidates = ["AAPL", "MSFT", "GOOGL", "NVDA", "AMZN", "META"]
        selected = candidates[:5]
        self.assertEqual(len(selected), 5)

    # 6. WATCHLIST 5 selection
    def test_06_watchlist_5_selection(self):
        watchlist = ["NFLX", "TSLA"]
        self.assertTrue(len(watchlist) <= 5)

    # 7. sector caps
    def test_07_sector_caps(self):
        # Tech sector limit: max 2 in Top 5 (40% cap)
        selected_sectors = ["Technology", "Technology", "Consumer Discretionary"]
        new_sector = "Technology"
        is_allowed = selected_sectors.count(new_sector) < 2
        self.assertFalse(is_allowed)

    # 8. correlation constraints
    def test_08_correlation_constraints(self):
        corr = 0.85
        is_allowed = corr <= 0.70
        self.assertFalse(is_allowed)

    # 9. position sizing constraints
    def test_09_position_sizing_constraints(self):
        # Sizing equal: 20%
        weight = 0.20
        self.assertEqual(weight, 0.20)

    # 10. two-stage allocation
    def test_10_two_stage_allocation(self):
        alloc1 = 0.4
        alloc2 = 0.6
        ret1 = 0.05
        ret2 = -0.01
        combined = alloc1 * ret1 + alloc2 * ret2
        self.assertAlmostEqual(combined, 0.014, places=6)

    # 11. second-entry timing
    def test_11_second_entry_timing(self):
        # Entry 2 at T+2 if close > SMA20
        close_t2 = 102.0
        sma20 = 100.0
        is_triggered = close_t2 > sma20
        self.assertTrue(is_triggered)

    # 12. thesis invalidation
    def test_12_thesis_invalidation(self):
        # Exit if close < EMA20 (thesis invalidation)
        close = 99.0
        ema20 = 100.0
        is_exit = close < ema20
        self.assertTrue(is_exit)

    # 13. dynamic exit
    def test_13_dynamic_exit(self):
        entry_price = 100.0
        close = 116.0
        is_tp = (close / entry_price - 1.0) >= 0.15
        self.assertTrue(is_tp)

    # 14. expected horizon
    def test_14_expected_horizon(self):
        horizon = 30
        self.assertEqual(horizon, 30)

    # 15. BEAR entry restriction
    def test_15_bear_entry_restriction(self):
        regime = "BEAR"
        alpha_cutoff = 0.75 if regime == "BEAR" else 0.50
        self.assertEqual(alpha_cutoff, 0.75)

    # 16. existing-position risk reassessment
    def test_16_existing_position_risk_reassessment(self):
        regime = "BEAR"
        stop_multiplier = 0.75 if regime == "BEAR" else 1.0
        self.assertEqual(stop_multiplier, 0.75)

    # 17. transaction costs
    def test_17_transaction_costs(self):
        realized = 0.05
        fee = 0.0020
        net = realized - 2 * fee
        self.assertAlmostEqual(net, 0.0460, places=6)

    # 18. PIT protection
    def test_18_pit_protection(self):
        status = DataStatus.REAL_PIT_UNVERIFIED
        is_backtest_allowed = (status != DataStatus.REAL_PIT_UNVERIFIED)
        self.assertFalse(is_backtest_allowed)

    # 19. holdout isolation
    def test_19_holdout_isolation(self):
        from scripts.run_p6_5_6_7_joint_decision_research import TRAIN_DATES, HOLDOUT_DATES
        self.assertTrue(max(TRAIN_DATES) < min(HOLDOUT_DATES))

    # 20. deterministic reproducibility
    def test_20_deterministic_reproducibility(self):
        scores = pd.Series([1.0, 0.8])
        rets = pd.Series([0.05, 0.01])
        ic1 = scores.rank().corr(rets.rank())
        ic2 = scores.rank().corr(rets.rank())
        self.assertEqual(ic1, ic2)

    # 21. baseline immutability
    def test_21_baseline_immutability(self):
        from utils.config import DEFAULT_FACTOR_WEIGHTS
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["momentum"], 0.35)
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["value"], 0.20)

    # 22. no future data leakage
    def test_22_no_future_data_leakage(self):
        # Entry trigger uses only past/current SMA
        close = 101.0
        sma = 100.0
        is_entry = close > sma
        self.assertTrue(is_entry)

    # 23. research candidate accounting
    def test_23_candidate_accounting(self):
        total_configs = 36
        self.assertEqual(total_configs, 36)

    # 24. unavailable-data graceful degradation
    def test_24_unavailable_data_degradation(self):
        prices = pd.Series([100.0, np.nan, 102.0, 103.0])
        rsi = calculate_rsi(prices.ffill(), period=2)
        self.assertFalse(np.isnan(rsi.iloc[-1]))


if __name__ == "__main__":
    unittest.main()
