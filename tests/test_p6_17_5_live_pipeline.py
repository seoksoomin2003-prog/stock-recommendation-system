import os
import tempfile
import unittest
from datetime import datetime, timezone
from core.universe_provider import WikipediaSP500BootstrapProvider
from data.loader import DataLoader
from core.decision_engine import DecisionEngine
from core.factor_engine import FactorEngine
from utils.market_calendar import expected_latest_trading_session, get_trading_session_lag
import pandas as pd
import numpy as np

PROVIDER_TESTS = os.getenv("QPP_PROVIDER_TESTS") == "1"


class TestP6175LivePipeline(unittest.TestCase):

    def setUp(self):
        # P6-18: never overwrite the production universe cache from a test.
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.universe_provider = WikipediaSP500BootstrapProvider(cache_file=os.path.join(self._tmp.name, "u.json"))
        self.loader = DataLoader()
        self.de = DecisionEngine()
        
    @unittest.skipUnless(PROVIDER_TESTS, "live provider test: set QPP_PROVIDER_TESTS=1")
    def test_01_universe_dynamically_acquired(self):
        universe = self.universe_provider.get_live_universe()
        self.assertIn(universe["status"], ["SUCCESS", "SUCCESS_FROM_CACHE"])
        self.assertGreater(len(universe["tickers"]), 450)
        
    @unittest.skipUnless(PROVIDER_TESTS, "live provider test: set QPP_PROVIDER_TESTS=1")
    def test_02_no_seven_ticker_fallback(self):
        universe = self.universe_provider.get_live_universe()
        tickers = universe["tickers"]
        dev_list = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]
        self.assertNotEqual(tickers, dev_list, "Production universe must not silently fallback to 7 tickers.")
        
    @unittest.skipUnless(PROVIDER_TESTS, "live provider test: set QPP_PROVIDER_TESTS=1")
    def test_03_universe_provenance_recorded(self):
        universe = self.universe_provider.get_live_universe()
        self.assertIn("provider_role", universe)
        self.assertIn("retrieved_at", universe)
        
    @unittest.skipUnless(PROVIDER_TESTS, "live provider test: set QPP_PROVIDER_TESTS=1")
    def test_04_sec_cik_mapping_works(self):
        universe = self.universe_provider.get_live_universe()
        ciks = universe.get("ciks", {})
        self.assertGreater(len(ciks), 450)
        self.assertIn("AAPL", ciks)
        
    @unittest.skipUnless(PROVIDER_TESTS, "live provider test: set QPP_PROVIDER_TESTS=1")
    def test_05_market_data_failures_become_nan(self):
        df = self.loader.get_price_data(["INVALID_TICKER_XYZ"], "2020-01-01", "2020-01-10")
        if not df.empty and "INVALID_TICKER_XYZ" in df.columns:
            self.assertTrue(df["INVALID_TICKER_XYZ"].isna().all())
            
    def test_06_market_data_stale_detection(self):
        # Create a stale dataframe (last bar is 10 days ago)
        dates = pd.date_range(end=pd.Timestamp.now() - pd.Timedelta(days=10), periods=20, freq='B')
        df = pd.DataFrame({'AAPL': np.random.rand(20)}, index=dates)
        checked = self.loader._enforce_lookback_and_freshness(df, ["AAPL"])
        self.assertEqual(checked.attrs["provider_status"]["AAPL"], "STALE")
        self.assertFalse(checked["AAPL"].isna().all(), "STALE identity must survive to the provenance gate")
        
    def test_07_weekend_holiday_freshness(self):
        # A Monday morning should expect Friday as latest completed session.
        # This tests utils.market_calendar logic conceptually.
        dt = datetime(2023, 1, 9, 10, 0, tzinfo=timezone.utc) # Jan 9 2023 was a Monday
        expected = expected_latest_trading_session(dt).normalize().tz_convert(None)
        # Friday was Jan 6
        self.assertEqual(expected.day, 6)
        
    def test_08_optional_data_failure_no_mock(self):
        news = self.loader.get_news_headlines("INVALID_XYZ")
        self.assertEqual(news, [], "MOCK data must not be created.")
        
    def test_09_mock_candidates_quarantined(self):
        # MOCK data must not pass data_quality check
        candidate = {"security_id": "X", "ticker": "XYZ", "close": 100, "volume": 1000000, "alpha": 0.5, "atr": 2,
                     "ema20": 98, "alpha_percentile": 1.0, "data_status": "MOCK"}
        self.assertFalse(self.de._check_data_quality(candidate))
        decision = self.de.evaluate_portfolio(datetime.now(timezone.utc), 10000, "BULL", [candidate])
        self.assertEqual(decision.top5, [])
        self.assertEqual(decision.watchlist5, [])
        
    def test_10_stale_candidates_not_real(self):
        # STALE data becomes NaN in price, which fails DecisionEngine check
        c = {"ticker": "XYZ", "close": np.nan, "volume": 1000000, "alpha": 0.5, "atr": 2, "ema20": 98}
        self.assertFalse(self.de._check_data_quality(c))
        
    def test_11_nan_volume_fails_liquidity(self):
        c = {"ticker": "XYZ", "close": 100, "volume": np.nan, "alpha": 0.5, "atr": 2, "ema20": 98}
        self.assertFalse(self.de._check_data_quality(c))
        
    def test_13_500k_liquidity_threshold_unchanged(self):
        base = {"ticker": "XYZ", "close": 100, "alpha": 0.5, "atr": 2, "ema20": 98}
        self.assertFalse(self.de._check_data_quality({**base, "volume": 499999}))
        self.assertTrue(self.de._check_data_quality({**base, "volume": 500000}))
        
    def test_16_model_rank_e_unchanged(self):
        mk = lambda i, p: {"security_id": str(i), "ticker": f"T{i}", "close": 100, "volume": 1e6, "alpha": p,
                           "atr": 2, "ema20": 95, "alpha_percentile": p, "entry_readiness": 1.0}
        d = self.de.evaluate_portfolio(datetime.now(timezone.utc), 10000, "BEAR", [mk(0, 0.75), mk(1, 0.7499)])
        self.assertEqual(d.model_version, "MODEL_RANK_E")
        self.assertEqual([s.ticker for s in d.top5], ["T0"])

if __name__ == '__main__':
    unittest.main()
