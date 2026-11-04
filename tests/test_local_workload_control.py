#!/usr/bin/env python3
import sys
import os
import unittest
from unittest.mock import Mock, patch
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

import utils.config
from main import QuantTradingSystemV2
from alpha_engine.system import AlphaScoringEngine
from alpha_engine.input.storage import TickerStorage

class TestLocalWorkloadControl(unittest.TestCase):

    def setUp(self):
        # Force fresh providers state for testing
        from core.providers import ProviderFactory
        ProviderFactory.reset_providers()
        
        # Populate DB with mock tickers and aliases to support full Entity Resolution testing
        storage = TickerStorage()
        
        def populate_ticker_and_alias(ticker, company_name):
            try:
                ticker_id = storage.add_ticker(ticker, company_name)
                alias_id = storage.add_alias(ticker_id, ticker, "manual", 1.0)
                storage.add_token(alias_id, ticker)
                for t in company_name.split():
                    if len(t) > 2:
                        storage.add_token(alias_id, t)
                return ticker_id
            except Exception:
                pass
                
        # Populate tickers
        googl_id = populate_ticker_and_alias("GOOGL", "Alphabet Inc.")
        aapl_id = populate_ticker_and_alias("AAPL", "Apple Inc.")
        populate_ticker_and_alias("MSFT", "Microsoft Corporation")
        populate_ticker_and_alias("TSLA", "Tesla Inc.")
        
        # Extra aliases
        if googl_id:
            try:
                alias_googl = storage.add_alias(googl_id, "구글", "manual", 1.0)
                storage.add_token(alias_googl, "구글")
                alias_google = storage.add_alias(googl_id, "google", "manual", 1.0)
                storage.add_token(alias_google, "google")
                alias_alph = storage.add_alias(googl_id, "Alphabet", "manual", 1.0)
                storage.add_token(alias_alph, "Alphabet")
            except Exception:
                pass
                
        if aapl_id:
            try:
                alias_aapl = storage.add_alias(aapl_id, "애플", "manual", 1.0)
                storage.add_token(alias_aapl, "애플")
                alias_apple = storage.add_alias(aapl_id, "apple", "manual", 1.0)
                storage.add_token(alias_apple, "apple")
            except Exception:
                pass

        # Populate production 10 tickers
        tickers_10 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX", "JPM", "XOM"]
        for t in tickers_10:
            populate_ticker_and_alias(t, f"{t} Corporation")

    @patch('yfinance.download')
    def test_test1_local_1_ticker(self, mock_yf_download):
        """TEST 1 - LOCAL / 1 TICKER -> PASS, lookback <= 365 days"""
        print("Testing Local Mode / 1 Ticker...")
        utils.config.APP_MODE = "local"
        
        idx = pd.date_range("2026-01-01", "2026-01-05")
        columns = pd.MultiIndex.from_product([["Close", "Volume"], ["AAPL"]])
        mock_df = pd.DataFrame(100.0, index=idx, columns=columns)
        mock_yf_download.return_value = mock_df

        system = QuantTradingSystemV2(mode="backtest")
        res = system.run_live_cycle(["AAPL"])
        
        self.assertEqual(res["status"], "SUCCESS")
        
        # Locate the specific yfinance call for AAPL
        call_found = None
        for call in mock_yf_download.call_args_list:
            args, kwargs = call
            target = args[0] if len(args) > 0 else kwargs.get("tickers")
            if target == "AAPL" or target == ["AAPL"]:
                call_found = call
                break
                
        self.assertIsNotNone(call_found, "yfinance.download not called for AAPL")
        _, kwargs = call_found
        start_date = kwargs.get("start")
        end_date = kwargs.get("end")
        
        days_diff = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
        print(f"- Start: {start_date}, End: {end_date}, Lookback: {days_diff} days")
        self.assertTrue(days_diff <= 365, f"Lookback exceeded 365 days in Local Mode: {days_diff} days")
        print("[PASS] Local Mode / 1 Ticker lookback constraint verified.")

    @patch('yfinance.download')
    def test_test2_local_3_tickers(self, mock_yf_download):
        """TEST 2 - LOCAL / 3 TICKERS -> PASS, lookback <= 365 days"""
        print("\nTesting Local Mode / 3 Tickers...")
        utils.config.APP_MODE = "local"
        
        idx = pd.date_range("2026-01-01", "2026-01-05")
        columns = pd.MultiIndex.from_product([["Close", "Volume"], ["AAPL", "MSFT", "GOOGL"]])
        mock_df = pd.DataFrame(100.0, index=idx, columns=columns)
        mock_yf_download.return_value = mock_df

        system = QuantTradingSystemV2(mode="backtest")
        res = system.run_live_cycle(["AAPL", "MSFT", "GOOGL"])
        
        self.assertEqual(res["status"], "SUCCESS")
        
        call_found = None
        for call in mock_yf_download.call_args_list:
            args, kwargs = call
            target = args[0] if len(args) > 0 else kwargs.get("tickers")
            if isinstance(target, list) and set(target) == {"AAPL", "MSFT", "GOOGL"}:
                call_found = call
                break
                
        self.assertIsNotNone(call_found, "yfinance.download not called for the 3 tickers")
        _, kwargs = call_found
        start_date = kwargs.get("start")
        end_date = kwargs.get("end")
        days_diff = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
        self.assertTrue(days_diff <= 365)
        print("[PASS] Local Mode / 3 Tickers verification succeeded.")

    @patch('yfinance.download')
    def test_test3_local_4_tickers_rejection(self, mock_yf_download):
        """TEST 3 - LOCAL / 4 TICKERS -> LIMIT_EXCEEDED, NO API FETCH"""
        print("\nTesting Local Mode / 4 Tickers Rejection (No fetch)...")
        utils.config.APP_MODE = "local"

        system = QuantTradingSystemV2(mode="backtest")
        res = system.run_live_cycle(["AAPL", "MSFT", "GOOGL", "TSLA"])
        
        print(f"- Result payload: {res}")
        self.assertEqual(res["status"], "LIMIT_EXCEEDED")
        self.assertEqual(res["executable"], False)
        self.assertEqual(res["max_tickers"], 3)
        self.assertEqual(res["received"], 4)
        self.assertIn("TSLA", res["rejected"])
        
        # Verify no calls were made to mock_yf_download for our tickers
        for call in mock_yf_download.call_args_list:
            args, kwargs = call
            target = args[0] if len(args) > 0 else kwargs.get("tickers")
            if isinstance(target, list) and len(target) >= 4:
                self.fail("yfinance.download should not have been called with 4 tickers!")
                
        print("[PASS] Rejected cleanly without initiating network data harvests.")

    @patch('yfinance.download')
    @patch('data.loader.DataLoader.get_financial_data')
    @patch('core.llm_fundamental_engine.LLMFundamentalEngine.batch_analyze_full')
    def test_test4_local_duplicates(self, mock_batch_analyze, mock_get_financial, mock_yf_download):
        """TEST 4 - LOCAL DUPLICATES -> GOOGL deduplicated -> PASS"""
        print("\nTesting Local Mode Ticker Deduplication...")
        utils.config.APP_MODE = "local"
        
        idx = pd.date_range("2026-01-01", "2026-01-05")
        columns = pd.MultiIndex.from_product([["Close", "Volume"], ["GOOGL"]])
        mock_df = pd.DataFrame(100.0, index=idx, columns=columns)
        mock_yf_download.return_value = mock_df
        
        mock_financial = pd.DataFrame({'per': [15.0], 'pbr': [3.0], 'roe': [0.2], 'profitMargin': [0.1]}, index=["GOOGL"])
        mock_get_financial.return_value = mock_financial
        
        mock_batch_analyze.return_value = {"GOOGL": {"final_score": 80.0, "data_status": "REAL"}}

        system = QuantTradingSystemV2(mode="backtest")
        res = system.run_live_cycle(["GOOGLE", "google", "googl", "Alphabet"])
        
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(len(res["scores"]), 1)
        self.assertEqual(res["scores"].index[0], "GOOGL")
        print("[PASS] Deduplication to single canonical ticker successful.")

    def test_test5_local_natural_language(self):
        """TEST 5 - LOCAL NATURAL LANGUAGE -> Resolves and parses -> PASS"""
        print("\nTesting Local Mode Natural Language parsing resolution...")
        utils.config.APP_MODE = "local"
        
        engine = AlphaScoringEngine()
        with patch.object(engine, '_harvest_signals') as mock_harvest:
            def mock_harvest_side_effect(ticker, company_name, **kwargs):
                return {"ticker": ticker, "sentiment": 0.0, "buzz": 0.0, "trends": 50.0, "insider": 0.0, "macro": 0.0}
            mock_harvest.side_effect = mock_harvest_side_effect
            
            res = engine.run_research_pipeline("구글이랑 애플 분석해줘")
            
            print(f"- Resolved pipeline output columns/index:\n{res}")
            self.assertIn("GOOGL", res.index)
            self.assertIn("AAPL", res.index)
            self.assertEqual(len(res), 2)
        print("[PASS] Natural language resolved and executed under limit.")

    @patch('yfinance.download')
    def test_test6_test7_production_mode_unconstrained(self, mock_yf_download):
        """TEST 6 & 7 - PRODUCTION MODE -> 10+ tickers, 4Y lookback -> PASS"""
        print("\nTesting Production Mode Immutability (Unconstrained)...")
        utils.config.APP_MODE = "production"
        
        idx = pd.date_range("2022-01-01", "2026-01-05")
        tickers_10 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "NFLX", "JPM", "XOM"]
        columns = pd.MultiIndex.from_product([["Close", "Volume"], tickers_10])
        mock_df = pd.DataFrame(100.0, index=idx, columns=columns)
        mock_yf_download.return_value = mock_df

        system = QuantTradingSystemV2(mode="backtest")
        res = system.run_live_cycle(tickers_10)
        
        self.assertEqual(res["status"], "SUCCESS")
        
        call_found = None
        for call in mock_yf_download.call_args_list:
            args, kwargs = call
            target = args[0] if len(args) > 0 else kwargs.get("tickers")
            if isinstance(target, list) and len(target) == 10:
                call_found = call
                break
                
        self.assertIsNotNone(call_found)
        _, kwargs = call_found
        start_date = kwargs.get("start")
        end_date = kwargs.get("end")
        
        days_diff = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days
        print(f"- Start: {start_date}, End: {end_date}, Lookback: {days_diff} days")
        
        self.assertEqual(len(res["scores"]), 10)
        self.assertTrue(days_diff > 1400, f"Production lookback was clipped: {days_diff} days")
        print("[PASS] Production Mode completely unconstrained by Local limits.")

if __name__ == "__main__":
    unittest.main()
