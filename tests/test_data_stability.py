#!/usr/bin/env python3
import sys
import os
import unittest
import time
import json
import pandas as pd
from unittest.mock import Mock, patch

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

import utils.config
from alpha_engine.data.trends_engine import GoogleTrendsEngine
from alpha_engine.data.sec_engine import SECInsiderEngine
from alpha_engine.data.sec.sec_api_provider import SecApiProvider
from alpha_engine.system import AlphaScoringEngine

class TestDataStability(unittest.TestCase):

    def setUp(self):
        utils.config.APP_MODE = "local"
        
        self.cache_dir = "data/sec_cache"
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except Exception:
                pass
                
        for f in os.listdir(self.cache_dir):
            try:
                os.remove(os.path.join(self.cache_dir, f))
            except Exception:
                pass

    def test_trends_normal_response(self):
        """TEST 1: Normal Trends response -> correct score"""
        print("Testing normal Google Trends response...")
        engine = GoogleTrendsEngine()
        
        mock_pytrends = Mock()
        mock_df = pd.DataFrame({
            "AAPL": [80.0, 90.0],
            "AAPL stock": [70.0, 80.0],
            "AAPL share price": [60.0, 70.0],
            "Apple Inc.": [50.0, 60.0]
        }, index=pd.date_range("2026-02-01", periods=2))
        mock_pytrends.interest_over_time.return_value = mock_df
        engine.pytrends = mock_pytrends
        
        res = engine.get_trend_score("AAPL", "Apple Inc.")
        print(f"- Trends returned: {res}")
        self.assertEqual(res["status"], "OK")
        self.assertEqual(res["confidence"], 1.0)
        self.assertTrue(50.0 <= res["value"] <= 100.0)

    def test_trends_timeout_fallback(self):
        """TEST 2: Trends timeout -> fallback"""
        print("Testing Google Trends timeout...")
        engine = GoogleTrendsEngine()
        
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.side_effect = Exception("ConnectTimeout")
        engine.pytrends = mock_pytrends
        
        res = engine.get_trend_score("AAPL")
        print(f"- Trends returned: {res}")
        self.assertEqual(res["status"], "FALLBACK")
        self.assertEqual(res["confidence"], 0.0)
        self.assertEqual(res["value"], 50.0)

    def test_trends_429_retry_fallback(self):
        """TEST 3: Trends 429 rate limit -> fallback"""
        print("Testing Google Trends 429 Rate Limit...")
        engine = GoogleTrendsEngine()
        
        mock_pytrends = Mock()
        mock_pytrends.interest_over_time.side_effect = Exception("HTTP Error 429 Too Many Requests")
        engine.pytrends = mock_pytrends
        
        with patch('time.sleep'):
            res = engine.get_trend_score("AAPL")
            
        print(f"- Trends returned: {res}")
        self.assertEqual(res["status"], "FALLBACK")
        self.assertEqual(res["confidence"], 0.0)
        self.assertEqual(res["value"], 50.0)

    def test_sec_cik_resolution(self):
        """TEST 10: Valid CIK resolution mapping"""
        print("Testing SEC CIK resolution mapping...")
        provider = SecApiProvider()
        
        cik = provider._resolve_cik("AAPL")
        print(f"- AAPL CIK resolved: {cik}")
        self.assertEqual(cik, "320193")
        
        cik_fallback = provider._resolve_cik("GOOGL")
        self.assertEqual(cik_fallback, "1652044")

    def test_sec_normal_response(self):
        """TEST 10 bis: Normal SEC submissions fetch"""
        print("Testing normal SEC EDGAR response...")
        provider = SecApiProvider()
        
        mock_submissions = {
            "cik": "320193",
            "tickers": ["AAPL"],
            "filings": {
                "recent": {
                    "form": ["10-K", "10-Q", "4"],
                    "accessionNumber": ["000-111", "000-222", "000-333"],
                    "filingDate": ["2026-03-01", "2026-03-02", "2026-03-03"],
                    "primaryDocument": ["aapl.htm", "aapl_q.htm", "ceo_form4.htm"]
                }
            }
        }
        
        with patch('requests.get') as mock_get:
            mock_res = Mock()
            mock_res.status_code = 200
            mock_res.json.return_value = mock_submissions
            mock_get.return_value = mock_res
            
            filings = provider.fetch_filings("AAPL", filing_type="10-K")
            print(f"- Filings returned: {filings}")
            self.assertEqual(len(filings), 1)
            self.assertEqual(filings[0]["date"], "2026-03-01")
            self.assertEqual(provider.last_status["AAPL"], "OK")

    def test_sec_timeout_fallback(self):
        """TEST 12: SEC timeout -> fallback"""
        print("Testing SEC API timeout...")
        provider = SecApiProvider()
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Timeout")
            filings = provider.fetch_filings("AAPL")
            # P6-17.4 relabelled the simulated SEC fallback as MOCK (synthetic data is never FALLBACK/REAL).
            self.assertEqual(provider.last_status["AAPL"], "MOCK")
            self.assertEqual(provider.last_confidence["AAPL"], 0.0)

    def test_sec_stale_cache(self):
        """TEST 17: Stale SEC cache -> stale status + reduced confidence"""
        print("Testing SEC stale cache recovery...")
        provider = SecApiProvider()
        
        cache_path = os.path.join(provider.cache_dir, "AAPL_submissions.json")
        mock_submissions = {
            "cik": "320193",
            "tickers": ["AAPL"],
            "filings": {
                "recent": {
                    "form": ["10-K"],
                    "accessionNumber": ["000-111"],
                    "filingDate": ["2025-03-01"],
                    "primaryDocument": ["aapl.htm"]
                }
            }
        }
        with open(cache_path, "w") as f:
            json.dump(mock_submissions, f)
            
        past_time = time.time() - 90000
        os.utime(cache_path, (past_time, past_time))
        
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("Connection Timeout")
            filings = provider.fetch_filings("AAPL", filing_type="10-K")
            
            print(f"- Filings returned from stale cache: {filings}")
            self.assertEqual(len(filings), 1)
            self.assertEqual(provider.last_status["AAPL"], "STALE")
            self.assertEqual(provider.last_confidence["AAPL"], 0.5)

    def test_insider_engine_fallback_value(self):
        """TEST 13 bis: SEC failure -> fallback reset score to 0.0"""
        print("Testing SEC Insider Engine fallback value...")
        mock_provider = Mock()
        mock_provider.last_status = {"AAPL": "FALLBACK"}
        mock_provider.last_source = {"AAPL": "sec_fallback"}
        mock_provider.last_confidence = {"AAPL": 0.0}
        
        mock_provider.fetch_filings.return_value = []
        mock_provider.fetch_insider_trades.return_value = []
        
        engine = SECInsiderEngine(provider=mock_provider)
        res = engine.get_alpha_signals("AAPL")
        print(f"- SEC insider signals: {res}")
        self.assertEqual(res["insider_score"], 0.0)
        self.assertEqual(res["status"], "FALLBACK")
        self.assertEqual(res["confidence"], 0.0)

    def test_look_ahead_bias_prevention(self):
        """TEST 26: Look-ahead bias prevention"""
        print("Testing SEC look-ahead bias prevention...")
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
        
        engine = SECInsiderEngine(provider=mock_provider, sentiment_engine=mock_sentiment_engine)
        
        t_eval = pd.Timestamp("2025-06-01").timestamp()
        
        res = engine.get_alpha_signals("AAPL", evaluation_time=t_eval)
        print(f"- SEC look-ahead check returned: {res}")
        self.assertEqual(res["insider_score"], 0.02)

    def test_alpha_pipeline_integration_fallback(self):
        """TEST 22: Both fallback does not crash AlphaScoringEngine"""
        print("Testing scoring engine pipeline integration fallbacks...")
        from alpha_engine.input.storage import TickerStorage
        storage = TickerStorage()
        try:
            aapl_id = storage.add_ticker("AAPL", "Apple Inc.")
            storage.add_alias(aapl_id, "aapl", "manual", 1.0)
        except Exception:
            pass

        scoring_engine = AlphaScoringEngine()
        
        mock_trends = Mock()
        mock_trends.get_trend_score.return_value = {
            "value": 50.0,
            "status": "FALLBACK",
            "confidence": 0.0,
            "source": "google_trends_fallback"
        }
        scoring_engine.trends_engine = mock_trends
        
        mock_sec = Mock()
        mock_sec.get_alpha_signals.return_value = {
            "insider_score": 0.0,
            "filing_sentiment": 0.0,
            "status": "FALLBACK",
            "confidence": 0.0,
            "source": "sec_fallback"
        }
        scoring_engine.sec_engine = mock_sec
        
        df = scoring_engine.run_research_pipeline("AAPL")
        print(f"- Integrated scoring pipeline df columns: {df.columns.tolist()}")
        print(f"- AAPL score: {df.loc['AAPL', 'score']}")
        
        self.assertTrue("AAPL" in df.index)
        
        quality = scoring_engine.data_quality_report.get("AAPL")
        print(f"- AAPL data quality log: {quality}")
        self.assertIsNotNone(quality)
        self.assertEqual(quality["trends"]["status"], "FALLBACK")
        self.assertEqual(quality["sec"]["status"], "FALLBACK")

if __name__ == "__main__":
    unittest.main()
