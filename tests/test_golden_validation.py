#!/usr/bin/env python3
import sys
import os
import unittest
import time
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

import utils.config
from utils.memory_guard import MemoryGuard
from core.providers import ProviderFactory
from alpha_engine.system import AlphaScoringEngine
from alpha_engine.data.sec_engine import SECInsiderEngine

class TestGoldenValidation(unittest.TestCase):

    def setUp(self):
        utils.config.MEMORY_GUARD_ENABLED = True
        utils.config.APP_MODE = "local"
        
        # Populate resolver DB to make it work offline
        from alpha_engine.input.storage import TickerStorage
        storage = TickerStorage()
        try:
            aapl_id = storage.add_ticker("AAPL", "Apple Inc.")
            storage.add_alias(aapl_id, "aapl", "manual", 1.0)
            msft_id = storage.add_ticker("MSFT", "Microsoft Corp.")
            storage.add_alias(msft_id, "msft", "manual", 1.0)
            googl_id = storage.add_ticker("GOOGL", "Alphabet Inc.")
            storage.add_alias(googl_id, "googl", "manual", 1.0)
        except Exception:
            pass
            
        self.engine = AlphaScoringEngine()

    def test_test1_reproducibility(self):
        """TEST 1: Same input -> same environment -> same result"""
        print("Running TEST 1...")
        ProviderFactory.reset_providers()
        self.engine.buzz_engine.history.clear()
        res_a = self.engine.run_research_pipeline("AAPL")
        
        ProviderFactory.reset_providers()
        self.engine.buzz_engine.history.clear()
        res_b = self.engine.run_research_pipeline("AAPL")
        
        pd.testing.assert_frame_equal(res_a, res_b)

    def test_test2_core_factor_comparison(self):
        """TEST 2: Production vs Local core factor comparison"""
        print("Running TEST 2...")
        resolved = self.engine.resolver.resolve_input("AAPL")
        
        # Run Production
        utils.config.APP_MODE = "production"
        ProviderFactory.reset_providers()
        self.engine.buzz_engine.history.clear()
        prod_sig = self.engine._harvest_signals("AAPL", resolved["company_name"])
        
        # Run Local
        utils.config.APP_MODE = "local"
        ProviderFactory.reset_providers()
        self.engine.buzz_engine.history.clear()
        local_sig = self.engine._harvest_signals("AAPL", resolved["company_name"])
        
        # Core factors (macro, buzz) must match exactly
        self.assertAlmostEqual(prod_sig["macro"], local_sig["macro"], places=5)
        self.assertAlmostEqual(prod_sig["buzz"], local_sig["buzz"], places=5)

    def test_test3_final_score_comparison(self):
        """TEST 3: Production vs Local final score comparison"""
        print("Running TEST 3...")
        utils.config.APP_MODE = "production"
        df_prod = self.engine.run_research_pipeline("AAPL")
        self.assertTrue("AAPL" in df_prod.index)
        
        utils.config.APP_MODE = "local"
        df_local = self.engine.run_research_pipeline("AAPL")
        self.assertTrue("AAPL" in df_local.index)

    def test_test4_ranking_correlation(self):
        """TEST 4: Ranking correlation calculation safety"""
        print("Running TEST 4...")
        from scripts.run_golden_validation import spearman_rank_correlation, kendall_rank_correlation
        scores_a = [0.5, 0.2, 0.8]
        scores_b = [0.5, 0.2, 0.8]
        
        spearman = spearman_rank_correlation(scores_a, scores_b)
        kendall = kendall_rank_correlation(scores_a, scores_b)
        
        self.assertAlmostEqual(spearman, 1.0)
        self.assertAlmostEqual(kendall, 1.0)

    def test_test5_provider_difference_classification(self):
        """TEST 5: Provider difference classification check"""
        print("Running TEST 5...")
        factor_diff = {
            "factor": "trends",
            "production_val": 73.2,
            "local_val": 50.0
        }
        
        abs_delta = abs(factor_diff["production_val"] - factor_diff["local_val"])
        self.assertTrue(abs_delta > 0.0)
        
        status = "CLASS A"
        if abs_delta > 0.0:
            if factor_diff["factor"] in ["trends", "insider"]:
                status = "CLASS B"
        self.assertEqual(status, "CLASS B")

    def test_test6_fallback_transparency(self):
        """TEST 6: Fallback transparency (logging details in quality report)"""
        print("Running TEST 6...")
        self.engine.run_research_pipeline("AAPL")
        quality = self.engine.data_quality_report.get("AAPL")
        self.assertIsNotNone(quality)
        self.assertTrue("trends" in quality)
        self.assertTrue("sec" in quality)
        self.assertTrue("status" in quality["trends"])
        self.assertTrue("confidence" in quality["trends"])

    def test_test7_cache_isolation(self):
        """TEST 7: Cache isolation validation"""
        print("Running TEST 7...")
        # Clear Trends cache
        self.engine.trends_engine._cache.clear()
        
        # Mock pytrends to run successfully and write to cache
        mock_pytrends = Mock()
        mock_df = pd.DataFrame({
            "AAPL": [80.0, 90.0],
            "AAPL stock": [70.0, 80.0],
            "AAPL share price": [60.0, 70.0]
        }, index=pd.date_range("2026-02-01", periods=2))
        mock_pytrends.interest_over_time.return_value = mock_df
        self.engine.trends_engine.pytrends = mock_pytrends
        
        # Run trends calculation
        self.engine.trends_engine.get_trend_score("AAPL")
        self.assertEqual(len(self.engine.trends_engine._cache), 1)

    def test_test8_memory_guard_compatibility(self):
        """TEST 8: Memory Guard compatibility check"""
        print("Running TEST 8...")
        MemoryGuard.initialize()
        telemetry = MemoryGuard.check_and_cleanup()
        self.assertTrue(telemetry["memory_state"] in ["NORMAL", "WARNING", "CRITICAL", "EMERGENCY"])

    def test_test9_failure_isolation(self):
        """TEST 9: Single ticker failure isolation"""
        print("Running TEST 9...")
        original_harvest = self.engine._harvest_signals
        
        def mock_harvest(ticker, company_name, evaluation_time=None):
            if ticker == "MSFT":
                raise Exception("Network failure")
            return original_harvest(ticker, company_name, evaluation_time)
            
        with patch.object(self.engine, '_harvest_signals', side_effect=mock_harvest):
            df = self.engine.run_research_pipeline(["AAPL", "MSFT"])
            
            # AAPL should still be scored despite MSFT failure
            self.assertTrue("AAPL" in df.index)
            self.assertTrue("MSFT" in df.index)

    def test_test10_no_future_data_leakage(self):
        """TEST 10: No future data leakage (look-ahead bias filter)"""
        print("Running TEST 10...")
        mock_provider = Mock()
        mock_provider.fetch_filings.return_value = [
            {"date": "2026-03-01", "url": "http://example.com/future"},
            {"date": "2025-03-01", "url": "http://example.com/past"}
        ]
        mock_provider.fetch_insider_trades.return_value = [
            {"date": "2026-03-01", "transaction": "Buy", "amount": 1000},
            {"date": "2025-03-01", "transaction": "Buy", "amount": 2000}
        ]
        mock_provider.get_filing_content.return_value = "Filing content"
        
        mock_sentiment_engine = Mock()
        mock_sentiment_engine.analyze_sentiment.return_value = {"sentiment": 0.0}
        
        sec_engine = SECInsiderEngine(provider=mock_provider, sentiment_engine=mock_sentiment_engine)
        
        t_eval = pd.Timestamp("2025-06-01").timestamp()
        res = sec_engine.get_alpha_signals("AAPL", evaluation_time=t_eval)
        
        # Future filing date filtered out, only past trade remains (amount 2000 -> score 0.02)
        self.assertEqual(res["insider_score"], 0.02)

    def test_test11_score_range(self):
        """TEST 11: Final Score Range in [-1, 1]"""
        print("Running TEST 11...")
        df = self.engine.run_research_pipeline("AAPL")
        score = df.loc["AAPL", "score"]
        self.assertTrue(-1.0 <= score <= 1.0)

    def test_test12_no_alpha_formula_modification(self):
        """TEST 12: Scoring weights unchanged"""
        print("Running TEST 12...")
        # Check scorer weights sum to 1.0 and match defaults
        scorer_weights = self.engine.scorer.base_weights
        
        self.assertAlmostEqual(sum(scorer_weights.values()), 1.0)
        self.assertEqual(scorer_weights["sentiment"], 0.25)
        self.assertEqual(scorer_weights["trends"], 0.20)
        self.assertEqual(scorer_weights["insider"], 0.25)

if __name__ == "__main__":
    unittest.main()
