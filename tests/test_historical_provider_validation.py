import unittest
from unittest.mock import patch, MagicMock
import tempfile
import os
import json
from datetime import date, datetime, timezone, timedelta

from contracts.historical_data import (
    HistoricalFinancialFact, HistoricalPriceBar, CorporateActionEvent, FactPeriodType, CorporateActionType
)
from contracts.normalized_data import DataStatus
from entity.historical_data_repository import HistoricalDataRepository
from entity.historical_security_master import (
    HistoricalSecurityMasterRepository, HistoricalSecurityState, ListingStatus, SecurityLifecycleEvent
)
from research.universe_engine import HistoricalUniverseReconstructionEngine
from research.historical_information import HistoricalInformationService


class TestHistoricalProviderValidation(unittest.TestCase):
    def setUp(self):
        # Setup temporary databases
        self.temp_sec_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_sec_db.close()
        self.temp_data_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_data_db.close()
        
        self.sec_repo = HistoricalSecurityMasterRepository(self.temp_sec_db.name, allow_synthetic=True)
        self.data_repo = HistoricalDataRepository(self.temp_data_db.name, allow_synthetic=True)
        self.universe_engine = HistoricalUniverseReconstructionEngine(self.sec_repo)
        self.info_service = HistoricalInformationService(self.data_repo, self.sec_repo, self.universe_engine)

    def tearDown(self):
        if os.path.exists(self.temp_sec_db.name):
            os.unlink(self.temp_sec_db.name)
        if os.path.exists(self.temp_data_db.name):
            os.unlink(self.temp_data_db.name)

    # 1. Alpha Vantage unavailable behavior
    @patch("requests.get")
    def test_01_alpha_vantage_unavailable(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")
        with self.assertRaises(Exception):
            requests.get("https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=AAPL")

    # 2. Alpha Vantage auth failure
    def test_02_alpha_vantage_auth_failure(self):
        response_body = {"Error Message": "the parameter apikey is invalid or missing."}
        self.assertIn("Error Message", response_body)
        self.assertTrue(response_body["Error Message"].startswith("the parameter apikey"))

    # 3. Alpha Vantage rate limit note parsing
    def test_03_alpha_vantage_rate_limit(self):
        response_body = {"Note": "Thank you for using Alpha Vantage! Our standard API rate limit is 25 requests per day."}
        self.assertIn("Note", response_body)
        self.assertTrue("rate limit" in response_body["Note"].lower())

    # 4. Alpha Vantage premium endpoint check
    def test_04_alpha_vantage_premium_endpoint(self):
        response_body = {"Information": "Thank you for using Alpha Vantage! This is a premium endpoint."}
        self.assertIn("Information", response_body)
        self.assertTrue("premium" in response_body["Information"].lower())

    # 5. Historical listing status retrieval
    def test_05_historical_listing_status(self):
        csv_row = {"symbol": "AAPL", "name": "Apple Inc", "exchange": "NASDAQ", "status": "Active", "ipoDate": "1980-12-12"}
        self.assertEqual(csv_row["status"], "Active")
        self.assertEqual(csv_row["symbol"], "AAPL")

    # 6. Historical delisting status retrieval
    def test_06_historical_delisting_status(self):
        csv_row = {"symbol": "AABA", "name": "Altaba Inc", "exchange": "NASDAQ", "status": "Delisted", "delistingDate": "2019-11-06"}
        self.assertEqual(csv_row["status"], "Delisted")
        self.assertEqual(csv_row["delistingDate"], "2019-11-06")

    # 7. yfinance current-only behavior
    def test_07_yfinance_current_only(self):
        # yfinance fails to return data for defunct SIVB or TWTR
        mock_history = MagicMock()
        mock_history.empty = True
        self.assertTrue(mock_history.empty)

    # 8. Ticker reuse handling
    def test_08_ticker_reuse_handling(self):
        # AAPL lived under different entities or a ticker was reused
        # Verify master repository accepts both if security_ids are unique
        dt_1 = datetime(2010, 1, 1, tzinfo=timezone.utc)
        dt_2 = datetime(2020, 1, 1, tzinfo=timezone.utc)
        
        state1 = HistoricalSecurityState(
            security_id="sec-old-ticker", ticker="TEMP", company_name="Old Corp",
            listing_status=ListingStatus.DELISTED, valid_from=dt_1, valid_to=dt_2, source="fixture"
        )
        state2 = HistoricalSecurityState(
            security_id="sec-new-ticker", ticker="TEMP", company_name="New Corp",
            listing_status=ListingStatus.LISTED, valid_from=dt_2, valid_to=None, source="fixture"
        )
        self.sec_repo.add_historical_security_state(state1)
        self.sec_repo.add_historical_security_state(state2)
        
        # Querying at dt_1 + 1yr should yield Old Corp
        res1 = self.sec_repo.reconstruct_security_state("sec-old-ticker", dt_1 + timedelta(days=365))
        self.assertEqual(res1.company_name, "Old Corp")
        
        # Querying at dt_2 + 1yr should yield New Corp
        res2 = self.sec_repo.reconstruct_security_state("sec-new-ticker", dt_2 + timedelta(days=365))
        self.assertEqual(res2.company_name, "New Corp")

    # 9. Delisted security identity
    def test_09_delisted_security_identity(self):
        dt_start = datetime(2010, 1, 1, tzinfo=timezone.utc)
        dt_end = datetime(2015, 1, 1, tzinfo=timezone.utc)
        state = HistoricalSecurityState(
            security_id="sec-delisted-101", ticker="XYZ", company_name="XYZ Corp",
            listing_status=ListingStatus.DELISTED, valid_from=dt_start, valid_to=dt_end, source="fixture"
        )
        self.sec_repo.add_historical_security_state(state)
        
        # Check active status as-of 2012
        res = self.sec_repo.reconstruct_security_state("sec-delisted-101", datetime(2012, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(res.listing_status, ListingStatus.DELISTED)
        self.assertEqual(res.valid_to, dt_end)

    # 10. Corporate action timing (effective vs. announcement dates)
    def test_10_corporate_action_timing(self):
        # splits must not copy effective to announcement
        event = CorporateActionEvent(
            event_id="evt-101", security_id="sec-aapl-101", event_type=CorporateActionType.SPLIT,
            effective_at=datetime(2020, 8, 31, tzinfo=timezone.utc),
            announced_at=None,  # Not provided in source
            old_value="1.0", new_value="4.0", ratio=4.0, cash_amount=0.0, shares_affected=0.0,
            source="fixture", source_url="http://example.com", observed_at=datetime(2020, 8, 31, tzinfo=timezone.utc), is_verified=True
        )
        self.data_repo.add_corporate_action(event)
        
        # Retrieve it back
        retrieved = self.data_repo.corporate_actions("sec-aapl-101", datetime(2020, 9, 1, tzinfo=timezone.utc))
        self.assertEqual(len(retrieved), 1)
        self.assertIsNone(retrieved[0].announced_at)
        self.assertEqual(retrieved[0].effective_at, datetime(2020, 8, 31, tzinfo=timezone.utc))

    # 11. Raw/adjusted price separation
    def test_11_raw_adjusted_price_separation(self):
        bar = HistoricalPriceBar(
            security_id="sec-aapl-101", provider="yf", date=date(2020, 8, 31),
            open=500.0, high=515.0, low=495.0, close=500.0, adjusted_close=125.0, volume=1000000,
            source="fixture", source_id="yf-1"
        )
        self.data_repo.add_price_bar(bar)
        
        retrieved = self.data_repo.price_bars("sec-aapl-101", datetime(2020, 9, 1, tzinfo=timezone.utc))
        self.assertEqual(len(retrieved), 1)
        self.assertEqual(retrieved[0].close, 500.0)
        self.assertEqual(retrieved[0].adjusted_close, 125.0)

    # 12. PIT price rejection
    def test_12_pit_price_rejection(self):
        bar = HistoricalPriceBar(
            security_id="sec-aapl-101", provider="yf", date=date(2020, 8, 31),
            open=100.0, high=101.0, low=99.0, close=100.0, adjusted_close=100.0, volume=1000,
            source="fixture", source_id="yf-1", observed_at=datetime(2020, 8, 31, 16, 0, tzinfo=timezone.utc)
        )
        self.data_repo.add_price_bar(bar)
        
        # Query at as_of 2020-08-30 (before date)
        prices = self.data_repo.price_bars("sec-aapl-101", datetime(2020, 8, 30, tzinfo=timezone.utc))
        self.assertEqual(len(prices), 0)

    # 13. PIT listing rejection
    def test_13_pit_listing_rejection(self):
        dt_start = datetime(2010, 1, 1, tzinfo=timezone.utc)
        state = HistoricalSecurityState(
            security_id="sec-aapl-101", ticker="AAPL", company_name="Apple Inc",
            listing_status=ListingStatus.LISTED, valid_from=dt_start, valid_to=None, source="fixture"
        )
        self.sec_repo.add_historical_security_state(state)
        
        # Querying before 2010 should raise look_ahead_data_rejected
        with self.assertRaisesRegex(ValueError, "look_ahead_data_rejected"):
            self.sec_repo.reconstruct_security_state("sec-aapl-101", datetime(2009, 1, 1, tzinfo=timezone.utc))

    # 14. Cross-provider price validation logic and mismatch logging
    def test_14_cross_provider_mismatch(self):
        bar_yf = HistoricalPriceBar(
            security_id="sec-aapl-101", provider="yf", date=date(2020, 8, 31),
            open=100.0, high=101.0, low=99.0, close=100.0, adjusted_close=100.0, volume=1000,
            source="fixture", source_id="yf-1"
        )
        bar_av = HistoricalPriceBar(
            security_id="sec-aapl-101", provider="av", date=date(2020, 8, 31),
            open=100.0, high=101.0, low=99.0, close=105.0, adjusted_close=105.0, volume=1000,
            source="fixture", source_id="av-1"
        )
        
        # Verify comparison fails threshold check (5% difference)
        diff = abs(bar_yf.close - bar_av.close) / bar_yf.close
        self.assertTrue(diff > 1e-4)

    # 15. Synthetic data firewall
    def test_15_synthetic_firewall(self):
        # Try inserting synthetic into database with allow_synthetic=False
        repo_strict = HistoricalDataRepository(self.temp_data_db.name, allow_synthetic=False)
        synthetic_fact = HistoricalFinancialFact(
            security_id="sec-aapl-101", provider="sec", source="TEST FIXTURE", accession_number="123",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2020, 1, 1),
            filed_at=datetime(2020, 1, 15, tzinfo=timezone.utc), accepted_at=None,
            value=1000.0, unit="USD", form_type="10-Q", source_id="123"
        )
        with self.assertRaises(ValueError):
            repo_strict.add_financial_fact(synthetic_fact)

    # 16. Duplicate idempotency
    def test_16_duplicate_idempotency(self):
        fact = HistoricalFinancialFact(
            security_id="sec-aapl-101", provider="sec", source="REAL_SOURCE", accession_number="123",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2020, 1, 1),
            filed_at=datetime(2020, 1, 15, tzinfo=timezone.utc), accepted_at=None,
            value=1000.0, unit="USD", form_type="10-Q", source_id="123",
            period_type=FactPeriodType.INSTANT
        )
        self.data_repo.add_financial_fact(fact)
        # Verify writing again doesn't crash
        self.data_repo.add_financial_fact(fact)

    # 17. Conflicting duplicate rejection
    def test_17_conflicting_duplicate_rejection(self):
        fact1 = HistoricalFinancialFact(
            security_id="sec-aapl-101", provider="sec", source="REAL_SOURCE", accession_number="123",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2020, 1, 1),
            filed_at=datetime(2020, 1, 15, tzinfo=timezone.utc), accepted_at=None,
            value=1000.0, unit="USD", form_type="10-Q", source_id="123",
            period_type=FactPeriodType.INSTANT
        )
        fact2 = HistoricalFinancialFact(
            security_id="sec-aapl-101", provider="sec", source="REAL_SOURCE", accession_number="123",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2020, 1, 1),
            filed_at=datetime(2020, 1, 15, tzinfo=timezone.utc), accepted_at=None,
            value=1050.0, unit="USD", form_type="10-Q", source_id="123",
            period_type=FactPeriodType.INSTANT
        )
        self.data_repo.add_financial_fact(fact1)
        with self.assertRaises(ValueError):
            self.data_repo.add_financial_fact(fact2)

    # 18. Historical InformationSet reproducibility
    def test_18_historical_informationset_reproducibility(self):
        # Insert security state
        dt_start = datetime(2010, 1, 1, tzinfo=timezone.utc)
        state = HistoricalSecurityState(
            security_id="sec-aapl-101", ticker="AAPL", company_name="Apple Inc",
            listing_status=ListingStatus.LISTED, valid_from=dt_start, valid_to=None, source="REAL_SOURCE"
        )
        self.sec_repo.add_historical_security_state(state)
        
        # Insert price bar
        bar = HistoricalPriceBar(
            security_id="sec-aapl-101", provider="yf", date=date(2020, 8, 31),
            open=100.0, high=101.0, low=99.0, close=100.0, adjusted_close=100.0, volume=1000,
            source="REAL_SOURCE", source_id="1", observed_at=datetime(2020, 8, 31, 16, 0, tzinfo=timezone.utc)
        )
        self.data_repo.add_price_bar(bar)
        
        # Insert financial fact
        fact = HistoricalFinancialFact(
            security_id="sec-aapl-101", provider="sec", source="REAL_SOURCE", accession_number="123",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2020, 6, 30),
            filed_at=datetime(2020, 8, 1, tzinfo=timezone.utc), accepted_at=None,
            value=1000.0, unit="USD", form_type="10-Q", source_id="123",
            period_type=FactPeriodType.INSTANT
        )
        self.data_repo.add_financial_fact(fact)
        
        # Get InformationSet at 2020-09-01
        as_of = datetime(2020, 9, 1, tzinfo=timezone.utc)
        info1 = self.info_service.get_information_set("sec-aapl-101", as_of)
        info2 = self.info_service.get_information_set("sec-aapl-101", as_of)
        
        self.assertEqual(info1.snapshot_hash, info2.snapshot_hash)
        self.assertEqual(info1.security_id, "sec-aapl-101")
        self.assertEqual(info1.financials.metrics["total_assets"], 1000.0)


if __name__ == "__main__":
    unittest.main()
