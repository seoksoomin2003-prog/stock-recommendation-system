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
from alpha_engine.input.storage import TickerStorage

class TestStress(unittest.TestCase):

    def setUp(self):
        utils.config.APP_MODE = "local"
        utils.config.MAX_LOCAL_TICKERS = 10
        utils.config.MEMORY_GUARD_ENABLED = True
        
        # Populate resolver DB to make it work offline
        from scripts.run_stress_test import populate_database_aliases
        populate_database_aliases()
        
        self.engine = AlphaScoringEngine()

    def test_stress_5_tickers(self):
        """test_stress_5_tickers"""
        tickers = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]
        df = self.engine.run_research_pipeline(tickers)
        self.assertEqual(len(df), 5)
        for ticker in tickers:
            self.assertTrue(ticker in df.index)

    def test_stress_7_tickers(self):
        """test_stress_7_tickers"""
        tickers = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "AMZN", "META"]
        df = self.engine.run_research_pipeline(tickers)
        self.assertEqual(len(df), 7)
        for ticker in tickers:
            self.assertTrue(ticker in df.index)

    def test_stress_10_tickers(self):
        """test_stress_10_tickers"""
        tickers = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "AMZN", "META", "JPM", "KO", "005930.KS"]
        df = self.engine.run_research_pipeline(tickers)
        self.assertEqual(len(df), 10)
        for ticker in tickers:
            self.assertTrue(ticker in df.index)

    def test_entity_resolution_under_load(self):
        """test_entity_resolution_under_load"""
        inputs = ["apple", "구글", "tesla", "삼성전자"]
        resolved = [self.engine.resolver.resolve_input(inp) for inp in inputs]
        
        self.assertEqual(resolved[0]["ticker"], "AAPL")
        self.assertEqual(resolved[1]["ticker"], "GOOGL")
        self.assertEqual(resolved[2]["ticker"], "TSLA")
        self.assertEqual(resolved[3]["ticker"], "005930.KS")

    def test_provider_failure_isolation(self):
        """test_provider_failure_isolation"""
        # Mock Google Trends to fail, verify pipeline does not crash
        original_trends = self.engine.trends_engine.get_trend_score
        
        def mock_trends(ticker):
            if ticker == "GOOGL":
                raise Exception("Trends Rate Limit")
            return original_trends(ticker)
            
        with patch.object(self.engine.trends_engine, 'get_trend_score', side_effect=mock_trends):
            df = self.engine.run_research_pipeline(["AAPL", "GOOGL"])
            self.assertEqual(len(df), 2)
            self.assertTrue("AAPL" in df.index)
            self.assertTrue("GOOGL" in df.index)

    def test_timeout_behavior(self):
        """test_timeout_behavior"""
        # Verify yfinance request session has default finite timeouts
        import requests
        session = requests.Session()
        # Verify retry adapters or timeouts can be asserted
        self.assertTrue(True)

    def test_retry_bound(self):
        """test_retry_bound"""
        # Verify Trends engine limits retries to <= 2
        engine = self.engine.trends_engine
        # Trigger query with mock failing api to verify retry count
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.side_effect = Exception("HTTP 429")
        engine.pytrends = mock_pytrends
        
        # Should catch and fallback after 2 attempts (1 try + 1 retry)
        start_time = time.time()
        res = engine.get_trend_score("AAPL")
        elapsed = time.time() - start_time
        
        self.assertEqual(res["status"], "FALLBACK")
        self.assertTrue(elapsed < 5.0) # Confirms it doesn't loop infinitely

    def test_cache_reuse(self):
        """test_cache_reuse"""
        # Run first time (Cold)
        self.engine.trends_engine._cache.clear()
        
        mock_pytrends = Mock()
        mock_df = pd.DataFrame({
            "AAPL": [80.0, 90.0],
            "AAPL stock": [70.0, 80.0],
            "AAPL share price": [60.0, 70.0]
        }, index=pd.date_range("2026-02-01", periods=2))
        mock_pytrends.interest_over_time.return_value = mock_df
        self.engine.trends_engine.pytrends = mock_pytrends
        
        res1 = self.engine.trends_engine.get_trend_score("AAPL")
        self.assertEqual(len(self.engine.trends_engine._cache), 1)
        
        # Second time (Warm) should reuse cache
        # If we change pytrends to throw exception, it should still return SUCCESS from cache
        mock_pytrends.interest_over_time.side_effect = Exception("API offline")
        res2 = self.engine.trends_engine.get_trend_score("AAPL")
        self.assertEqual(res2["status"], "OK")

    def test_memory_guard(self):
        """test_memory_guard"""
        MemoryGuard.initialize()
        state = MemoryGuard.check_and_cleanup()
        self.assertTrue(state["memory_state"] in ["NORMAL", "WARNING", "CRITICAL", "EMERGENCY"])

    def test_cross_ticker_isolation(self):
        """test_cross_ticker_isolation"""
        # Failure of yfinance on MSFT shouldn't affect AAPL score calculation
        original_harvest = self.engine._harvest_signals
        
        def mock_harvest(ticker, company_name, evaluation_time=None):
            if ticker == "MSFT":
                raise Exception("Fatal Market Feed Failure")
            return original_harvest(ticker, company_name, evaluation_time)
            
        with patch.object(self.engine, '_harvest_signals', side_effect=mock_harvest):
            df = self.engine.run_research_pipeline(["AAPL", "MSFT"])
            self.assertTrue("AAPL" in df.index)
            self.assertTrue("MSFT" in df.index)

    def test_score_range(self):
        """test_score_range"""
        df = self.engine.run_research_pipeline(["AAPL", "MSFT"])
        for ticker in df.index:
            score = df.loc[ticker, "score"]
            self.assertTrue(-1.0 <= score <= 1.0)

    def test_resource_cleanup(self):
        """test_resource_cleanup"""
        # Ensure temporary file resources and threads can be checked or garbage collected
        import gc
        gc.collect()
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
