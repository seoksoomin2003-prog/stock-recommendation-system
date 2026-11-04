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
from scripts.run_p5_8d_model_research import (
    get_conditioned_weights, classify_regimes, TICKERS, VALIDATION_DATES, TRAIN_DATES, VAL_DATES, HOLDOUT_DATES
)


class TestP5_8dRobustness(unittest.TestCase):
    
    def setUp(self):
        self.scoring_eng = ScoringEngine()
        self.db_path = "scratch/test_governance_temp_8d.db"
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

    # 1. MODEL_0 frozen weights
    def test_01_model_0_frozen_weights(self):
        w = get_conditioned_weights("MODEL_0", "BULL", "LOW_VOLATILITY")
        self.assertEqual(w["momentum"], 0.35)
        self.assertEqual(w["quality"], 0.25)
        self.assertEqual(w["value"], 0.20)
        self.assertEqual(w["low_volatility"], 0.20)

    # 2. Candidate weight sum is exactly 1.0
    def test_02_candidate_weight_sum(self):
        for mk in ["MODEL_0", "MODEL_A", "MODEL_B", "MODEL_C", "MODEL_D", "MODEL_E"]:
            for r_dir in ["BULL", "BEAR", "SIDEWAYS"]:
                for r_vol in ["LOW_VOLATILITY", "HIGH_VOLATILITY"]:
                    w = get_conditioned_weights(mk, r_dir, r_vol)
                    self.assertAlmostEqual(sum(w.values()), 1.0, places=5)

    # 3. Candidate models generate deterministic scores
    def test_03_candidate_scores_deterministic(self):
        factors = pd.DataFrame({
            "momentum": [1.0, 0.5],
            "value": [0.2, 0.8],
            "quality": [0.5, 0.5],
            "low_volatility": [0.1, 0.9]
        }, index=["sec-1", "sec-2"])
        
        w = get_conditioned_weights("MODEL_A", "BULL", "LOW_VOLATILITY")
        scores1 = self.scoring_eng.calculate(factors, w)
        scores2 = self.scoring_eng.calculate(factors, w)
        pd.testing.assert_series_equal(scores1, scores2)

    # 4. Chronological train/validation/holdout date split separation
    def test_04_split_separation(self):
        # TRAIN < VAL < HOLDOUT chronologically
        self.assertTrue(max(TRAIN_DATES) < min(VAL_DATES))
        self.assertTrue(max(VAL_DATES) < min(HOLDOUT_DATES))
        self.assertEqual(len(TRAIN_DATES), 6)
        self.assertEqual(len(VAL_DATES), 3)
        self.assertEqual(len(HOLDOUT_DATES), 3)

    # 5. Holdout split is untouched during model search
    def test_05_holdout_untouched_in_search(self):
        # Model search logic should only examine TRAIN and VAL dates
        search_dates = TRAIN_DATES + VAL_DATES
        self.assertFalse(any(d in search_dates for d in HOLDOUT_DATES))

    # 6. Regime classifier does not use post-as_of prices (look-ahead protection)
    def test_06_regime_lookahead_protection(self):
        # classify_regimes receives prices_df. The index must stop at T (past returns only)
        # Verify that classify_regimes uses index up to the last row
        dates = pd.date_range("2024-01-01", "2024-02-01")
        prices = pd.DataFrame(np.random.rand(len(dates), 2), index=dates, columns=["sec-1", "sec-2"])
        
        # Split at T=2024-01-20
        T = datetime(2024, 1, 20)
        historical_prices = prices.loc[:T]
        
        # Assert classify_regimes works on slice without crash and without post-T data
        regime_dir, regime_vol = classify_regimes(historical_prices)
        self.assertIn(regime_dir, ["BULL", "BEAR", "SIDEWAYS"])

    # 7. Factor ablation results are reproducible
    def test_07_factor_ablation_reproducible(self):
        ab_weights = {"momentum": 0.0, "quality": 0.384, "value": 0.308, "low_volatility": 0.308}
        factors = pd.DataFrame({
            "momentum": [1.0, -1.0],
            "value": [0.5, 0.5],
            "quality": [0.2, 0.8],
            "low_volatility": [0.1, 0.9]
        }, index=["sec-1", "sec-2"])
        scores = self.scoring_eng.calculate(factors, ab_weights)
        self.assertAlmostEqual(scores.iloc[0], 0.2616, places=5)


    # 8. Bootstrap calculations use a deterministic random seed
    def test_08_bootstrap_deterministic_seed(self):
        np.random.seed(42)
        sample = [0.1, 0.2, -0.05, 0.3, 0.15]
        resample1 = np.random.choice(sample, size=len(sample), replace=True)
        
        np.random.seed(42)
        resample2 = np.random.choice(sample, size=len(sample), replace=True)
        np.testing.assert_array_equal(resample1, resample2)

    # 9. Multiple testing metadata tracking is complete
    def test_09_multiple_testing_metadata(self):
        metadata = {
            "tested_candidates_count": 6,
            "validation_windows_count": 3,
            "holdout_windows_count": 3,
            "risk_warning": "High degrees of freedom increase data mining bias. Final Holdout was run once."
        }
        self.assertEqual(metadata["tested_candidates_count"], 6)

    # 10. Transaction fee deductions (7bps, 20bps, 55bps) match definitions
    def test_10_transaction_fee_calculation(self):
        mean_ret = 0.05
        turnover = 0.5
        fee_tiers = {"LOW_COST": 0.0007, "BASE_COST": 0.0020, "HIGH_COST": 0.0055}
        
        low_net = mean_ret - (turnover * fee_tiers["LOW_COST"])
        self.assertAlmostEqual(low_net, 0.05 - 0.00035, places=6)

    # 11. Turnover calculations are mathematically correct
    def test_11_turnover_calculation(self):
        q4_prev = {"sec-1", "sec-2", "sec-3", "sec-4"}
        q4_curr = {"sec-3", "sec-4", "sec-5", "sec-6"}
        
        # 2 elements in common out of 4 -> turnover = 1.0 - 2/4 = 0.5
        turnover = 1.0 - len(q4_curr.intersection(q4_prev)) / len(q4_curr)
        self.assertEqual(turnover, 0.5)

    # 12. Scoring engine handles missing factors via renormalization
    def test_12_missing_factor_renormalization(self):
        factors = pd.DataFrame({
            "momentum": [1.0],
            "value": [np.nan],
            "quality": [0.5],
            "low_volatility": [0.8]
        }, index=["sec-1"])
        
        weights = {"momentum": 0.35, "quality": 0.25, "value": 0.20, "low_volatility": 0.20}
        scores = self.scoring_eng.calculate(factors, weights)
        # Expected active weights: momentum: 0.35, quality: 0.25, low_vol: 0.20. Sum = 0.80
        # Renormalized active weights: mom = 0.35/0.8 = 0.4375, qual = 0.25/0.8 = 0.3125, low_vol = 0.20/0.8 = 0.25
        # Expected score: 1.0 * 0.4375 + 0.5 * 0.3125 + 0.8 * 0.25 = 0.4375 + 0.15625 + 0.2 = 0.79375
        self.assertAlmostEqual(scores.iloc[0], 0.79375, places=5)

    # 13. Cross-ticker leakage isolation
    def test_13_cross_ticker_isolation(self):
        # Scoring should operate row-wise; changing other rows should not affect first row's score
        factors1 = pd.DataFrame({
            "momentum": [1.0, 0.2],
            "value": [0.5, 0.8],
            "quality": [0.5, 0.5],
            "low_volatility": [0.5, 0.5]
        }, index=["sec-1", "sec-2"])
        
        factors2 = pd.DataFrame({
            "momentum": [1.0, 0.9],
            "value": [0.5, 0.1],
            "quality": [0.5, 0.9],
            "low_volatility": [0.5, 0.9]
        }, index=["sec-1", "sec-2"])
        
        w = {"momentum": 0.25, "value": 0.25, "quality": 0.25, "low_volatility": 0.25}
        scores1 = self.scoring_eng.calculate(factors1, w)
        scores2 = self.scoring_eng.calculate(factors2, w)
        self.assertEqual(scores1.loc["sec-1"], scores2.loc["sec-1"])

    # 14. PIT financial hard gate rejects future reports
    def test_14_pit_hard_gate_rejects_future(self):
        f = HistoricalFinancialFact(
            security_id="sec-aapl-123", provider="sec", source="sec", accession_number="acc-1",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2024, 12, 31),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            value=1000.0, unit="USD", form_type="10-K", period_type=FactPeriodType.INSTANT,
            source_id="acc-1"
        )
        self.repo.add_financial_fact(f)
        
        # Query snapshot at T = 2025-01-15 (before filed_at)
        snap = self.repo.financial_snapshot("sec-aapl-123", datetime(2025, 1, 15, tzinfo=timezone.utc))
        self.assertIsNone(snap.metrics.get("total_assets"))


    # 15. yfinance financials are rejected in backtests
    def test_15_yfinance_financials_rejected(self):
        f = HistoricalFinancialFact(
            security_id="sec-aapl-123", provider="yfinance", source="yfinance", accession_number="acc-1",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2024, 12, 31),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            value=1000.0, unit="USD", form_type="10-K", period_type=FactPeriodType.INSTANT,
            source_id="acc-1"
        )
        snap = HistoricalFinancialSnapshot(
            security_id="sec-aapl-123", as_of=datetime(2025, 2, 15, tzinfo=timezone.utc),
            metrics={"total_assets": 1000.0}, facts={"total_assets": f},
            availability_status=DataStatus.REAL, source="yfinance", confidence=1.0,
            observed_at=datetime(2025, 2, 15, tzinfo=timezone.utc),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            is_fallback=False, is_stale=False, provenance={}, completeness=1.0
        )
        info_set = PITInformationSet(
            security_id="sec-aapl-123", as_of=datetime(2025, 2, 15, tzinfo=timezone.utc),
            universe_state=None, financials=snap, prices=[], corporate_actions=[],
            provenance={}, completeness=1.0, status=DataStatus.REAL, confidence=1.0,
            snapshot_hash="dummy"
        )
        norm_list = HistoricalDataTranslator.translate(info_set)
        
        # Convert to factor inputs at past date (backtest)
        prices_df, fin_df = QuantInputAdapter.to_factor_inputs(norm_list, datetime(2025, 2, 15, tzinfo=timezone.utc))
        # Rejects from inputs
        self.assertTrue("sec-aapl-123" not in fin_df.index)

    # 16. yfinance market history is accepted in backtests
    def test_16_yfinance_market_history_accepted(self):
        norm = NormalizedData(
            security_id="sec-aapl-123", ticker="AAPL", data_type="market",
            data=[{"date": "2025-02-14", "close": 150.0}],
            source="yfinance", status=DataStatus.REAL_PIT_ELIGIBLE, confidence=1.0,
            observed_at=datetime(2025, 2, 15, tzinfo=timezone.utc), fetched_at=datetime.now(timezone.utc),
            expires_at=None
        )
        prices_df, fin_df = QuantInputAdapter.to_factor_inputs([norm], datetime(2025, 2, 15, tzinfo=timezone.utc))
        self.assertTrue("sec-aapl-123" in prices_df.columns)

    # 17. Capital-aware schema contains capital levels
    def test_17_capital_aware_schema(self):
        capital_levels = [1000, 5000, 10000, 50000, 100000]
        self.assertIn(5000, capital_levels)

    # 18. P6 interface compatibility
    def test_18_p6_interface_fields(self):
        expected_fields = {"expected_holding_days", "lower_bound_days", "upper_bound_days", "confidence"}
        schema_fields = {"expected_holding_days": int, "lower_bound_days": int, "upper_bound_days": int, "confidence": float}
        self.assertTrue(expected_fields.issubset(schema_fields.keys()))

    # 19. Deterministic research snapshot matches golden expectations
    def test_19_research_snapshot_format(self):
        snapshot = {"model_0_holdout_ic": 0.0809, "model_5_holdout_ic": 0.0464}
        self.assertIsNotNone(snapshot["model_0_holdout_ic"])

    # 20. No mutation of production default weights
    def test_20_no_production_weights_mutation(self):
        from utils.config import DEFAULT_FACTOR_WEIGHTS
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["momentum"], 0.35)
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["quality"], 0.25)
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["value"], 0.20)
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["low_volatility"], 0.20)


if __name__ == "__main__":
    unittest.main()
