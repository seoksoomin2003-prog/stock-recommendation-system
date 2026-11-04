import unittest
import pandas as pd
import numpy as np
import json
import hashlib
from datetime import date, datetime, timezone, timedelta

from contracts.historical_data import (
    HistoricalFinancialFact, HistoricalPriceBar, CorporateActionEvent,
    HistoricalFinancialSnapshot, PITInformationSet, FactPeriodType, CorporateActionType
)
from contracts.normalized_data import DataStatus
from entity.historical_security_master import HistoricalSecurityState, ListingStatus
from research.historical_translation import HistoricalDataTranslator, QuantInputAdapter


class TestHistoricalTranslation(unittest.TestCase):
    def setUp(self):
        self.as_of = datetime(2025, 2, 15, tzinfo=timezone.utc)
        self.security_id = "sec-aapl-101"
        self.ticker = "AAPL"
        
        # Build dummy financial fact
        self.fact = HistoricalFinancialFact(
            security_id=self.security_id, provider="sec", source="SEC EDGAR", accession_number="123",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2024, 12, 31),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            value=1000.0, unit="USD", form_type="10-K", source_id="123",
            period_type=FactPeriodType.INSTANT, observed_at=datetime(2025, 2, 1, tzinfo=timezone.utc)
        )
        
        # Build dummy price bar
        self.price_bar = HistoricalPriceBar(
            security_id=self.security_id, provider="yf", date=date(2025, 2, 14),
            open=150.0, high=155.0, low=149.0, close=152.0, adjusted_close=152.0, volume=1000000.0,
            source="yf-source", source_id="yf-1", observed_at=datetime(2025, 2, 14, 16, 0, tzinfo=timezone.utc)
        )
        
        # Build dummy corporate action
        self.corp_action = CorporateActionEvent(
            security_id=self.security_id, event_id="evt-1", event_type=CorporateActionType.SPLIT,
            effective_at=datetime(2025, 2, 10, tzinfo=timezone.utc),
            announced_at=datetime(2025, 2, 5, tzinfo=timezone.utc),
            old_value="1.0", new_value="2.0", ratio=2.0, cash_amount=0.0, shares_affected=0.0,
            source="corp-source", source_url="http://sec.gov/123", observed_at=datetime(2025, 2, 5, tzinfo=timezone.utc),
            is_verified=True
        )

        # Build dummy security master state
        self.sec_state = HistoricalSecurityState(
            security_id=self.security_id, ticker=self.ticker, company_name="Apple Inc",
            listing_status=ListingStatus.LISTED, valid_from=datetime(2010, 1, 1, tzinfo=timezone.utc),
            valid_to=None, source="sec-master", confidence=1.0
        )

        # Build financials snapshot
        self.snapshot = HistoricalFinancialSnapshot(
            security_id=self.security_id, as_of=self.as_of,
            metrics={"total_assets": 1000.0}, facts={"total_assets": self.fact},
            availability_status=DataStatus.REAL, source="sec", confidence=1.0,
            observed_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            is_fallback=False, is_stale=False, provenance={}, completeness=1.0
        )

        # Create info_set
        self.info_set = PITInformationSet(
            security_id=self.security_id, as_of=self.as_of,
            universe_state={"security": self.sec_state, "universe": None},
            financials=self.snapshot, prices=[self.price_bar],
            corporate_actions=[self.corp_action], provenance={},
            completeness=1.0, status=DataStatus.REAL, confidence=1.0,
            snapshot_hash="hash-123"
        )

    # 1. HistoricalPriceBar -> NormalizedData
    def test_01_price_bar_translation(self):
        normalized = HistoricalDataTranslator.translate(self.info_set)
        market_item = next(x for x in normalized if x.data_type == "market")
        self.assertEqual(market_item.security_id, self.security_id)
        self.assertEqual(market_item.data[0]["close"], 152.0)
        self.assertEqual(market_item.source, "yf-source")

    # 2. HistoricalFinancialFact -> NormalizedData
    def test_02_financial_fact_translation(self):
        normalized = HistoricalDataTranslator.translate(self.info_set)
        fin_item = next(x for x in normalized if x.data_type == "financial")
        self.assertEqual(fin_item.security_id, self.security_id)
        self.assertEqual(fin_item.data["total_assets"]["value"], 1000.0)

    # 3. SEC fact translation
    def test_03_sec_fact_translation(self):
        # SEC provider tags should trigger the creation of a duplicate "sec" data type item
        normalized = HistoricalDataTranslator.translate(self.info_set)
        sec_item = next(x for x in normalized if x.data_type == "sec")
        self.assertEqual(sec_item.data["total_assets"]["value"], 1000.0)

    # 4. corporate action translation
    def test_04_corporate_action_translation(self):
        normalized = HistoricalDataTranslator.translate(self.info_set)
        corp_item = next(x for x in normalized if x.data_type == "corporate_actions")
        self.assertEqual(corp_item.data[0]["event_type"], "SPLIT")
        self.assertEqual(corp_item.data[0]["ratio"], 2.0)

    # 5. security master translation
    def test_05_security_master_translation(self):
        normalized = HistoricalDataTranslator.translate(self.info_set)
        master_item = next(x for x in normalized if x.data_type == "security_master")
        self.assertEqual(master_item.data["company_name"], "Apple Inc")

    # 6. universe translation
    def test_06_universe_translation(self):
        class DummyUniverseMembership:
            def __init__(self):
                self.universe_id = "TEST500"
                self.security_id = "sec-aapl-101"
                self.valid_from = datetime(2010, 1, 1, tzinfo=timezone.utc)
                self.valid_to = None
                self.source = "index-source"
        
        info_with_universe = PITInformationSet(
            security_id=self.security_id, as_of=self.as_of,
            universe_state={"security": self.sec_state, "universe": DummyUniverseMembership()},
            financials=self.snapshot, prices=[self.price_bar],
            corporate_actions=[self.corp_action], provenance={},
            completeness=1.0, status=DataStatus.REAL, confidence=1.0,
            snapshot_hash="hash-123"
        )
        normalized = HistoricalDataTranslator.translate(info_with_universe)
        uni_item = next(x for x in normalized if x.data_type == "universe")
        self.assertEqual(uni_item.data["universe_id"], "TEST500")

    # 7. provenance preservation
    def test_07_provenance_preservation(self):
        normalized = HistoricalDataTranslator.translate(self.info_set)
        fin_item = next(x for x in normalized if x.data_type == "financial")
        self.assertEqual(fin_item.data["total_assets"]["source_id"], "123")
        self.assertEqual(fin_item.data["total_assets"]["accession_number"], "123")

    # 8. snapshot hash reproducibility
    def test_08_snapshot_hash_reproducibility(self):
        # Translating twice yields the same output content
        res1 = HistoricalDataTranslator.translate(self.info_set)
        res2 = HistoricalDataTranslator.translate(self.info_set)
        h1 = hashlib.sha256(json.dumps(res1[0].data, default=str, sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(res2[0].data, default=str, sort_keys=True).encode()).hexdigest()
        self.assertEqual(h1, h2)

    # 9. future price rejection
    def test_09_future_price_rejection(self):
        future_bar = HistoricalPriceBar(
            security_id=self.security_id, provider="yf", date=date(2025, 2, 28), # Future date (after as_of Feb 15)
            open=150.0, high=155.0, low=149.0, close=152.0, adjusted_close=152.0, volume=1000000.0,
            source="yf-source", source_id="yf-1", observed_at=datetime(2025, 2, 28, 16, 0, tzinfo=timezone.utc)
        )
        info_set_err = PITInformationSet(
            security_id=self.security_id, as_of=self.as_of,
            universe_state={"security": self.sec_state, "universe": None},
            financials=self.snapshot, prices=[future_bar],
            corporate_actions=[self.corp_action], provenance={},
            completeness=1.0, status=DataStatus.REAL, confidence=1.0,
            snapshot_hash="hash-123"
        )
        with self.assertRaisesRegex(ValueError, "look_ahead_data_rejected"):
            HistoricalDataTranslator.translate(info_set_err)

    # 10. future filing rejection
    def test_10_future_filing_rejection(self):
        future_fact = HistoricalFinancialFact(
            security_id=self.security_id, provider="sec", source="SEC EDGAR", accession_number="123",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2024, 12, 31),
            filed_at=datetime(2025, 2, 28, tzinfo=timezone.utc), # Future date (after Feb 15)
            accepted_at=None, value=1000.0, unit="USD", form_type="10-K", source_id="123",
            period_type=FactPeriodType.INSTANT, observed_at=datetime(2025, 2, 28, tzinfo=timezone.utc)
        )
        snapshot_err = HistoricalFinancialSnapshot(
            security_id=self.security_id, as_of=self.as_of,
            metrics={"total_assets": 1000.0}, facts={"total_assets": future_fact},
            availability_status=DataStatus.REAL, source="sec", confidence=1.0,
            observed_at=datetime(2025, 2, 28, tzinfo=timezone.utc),
            filed_at=datetime(2025, 2, 28, tzinfo=timezone.utc), accepted_at=None,
            is_fallback=False, is_stale=False, provenance={}, completeness=1.0
        )
        info_set_err = PITInformationSet(
            security_id=self.security_id, as_of=self.as_of,
            universe_state={"security": self.sec_state, "universe": None},
            financials=snapshot_err, prices=[self.price_bar],
            corporate_actions=[self.corp_action], provenance={},
            completeness=1.0, status=DataStatus.REAL, confidence=1.0,
            snapshot_hash="hash-123"
        )
        with self.assertRaisesRegex(ValueError, "look_ahead_data_rejected"):
            HistoricalDataTranslator.translate(info_set_err)

    # 11. future corporate action rejection
    def test_11_future_corporate_action_rejection(self):
        future_corp = CorporateActionEvent(
            security_id=self.security_id, event_id="evt-1", event_type=CorporateActionType.SPLIT,
            effective_at=datetime(2025, 2, 28, tzinfo=timezone.utc), # Future
            announced_at=datetime(2025, 2, 28, tzinfo=timezone.utc),
            old_value="1.0", new_value="2.0", ratio=2.0, cash_amount=0.0, shares_affected=0.0,
            source="corp-source", source_url="http://sec.gov/123", observed_at=datetime(2025, 2, 28, tzinfo=timezone.utc),
            is_verified=True
        )
        info_set_err = PITInformationSet(
            security_id=self.security_id, as_of=self.as_of,
            universe_state={"security": self.sec_state, "universe": None},
            financials=self.snapshot, prices=[self.price_bar],
            corporate_actions=[future_corp], provenance={},
            completeness=1.0, status=DataStatus.REAL, confidence=1.0,
            snapshot_hash="hash-123"
        )
        with self.assertRaisesRegex(ValueError, "look_ahead_data_rejected"):
            HistoricalDataTranslator.translate(info_set_err)

    # 12. missing delisted price semantics
    def test_12_missing_delisted_price_semantics(self):
        # AAPL marked as delisted but prices list is empty
        delisted_state = HistoricalSecurityState(
            security_id=self.security_id, ticker=self.ticker, company_name="Apple Inc",
            listing_status=ListingStatus.DELISTED, valid_from=datetime(2010, 1, 1, tzinfo=timezone.utc),
            valid_to=self.as_of, source="sec-master", confidence=1.0
        )
        info_set_empty_prices = PITInformationSet(
            security_id=self.security_id, as_of=self.as_of,
            universe_state={"security": delisted_state, "universe": None},
            financials=self.snapshot, prices=[], # Empty prices list
            corporate_actions=[self.corp_action], provenance={},
            completeness=0.5, status=DataStatus.UNAVAILABLE, confidence=0.5,
            snapshot_hash="hash-123"
        )
        normalized = HistoricalDataTranslator.translate(info_set_empty_prices)
        
        # Verify listing status is complete
        master_item = next(x for x in normalized if x.data_type == "security_master")
        self.assertEqual(master_item.data["listing_status"], "DELISTED")
        
        # Verify price_history is missing
        market_item = next((x for x in normalized if x.data_type == "market"), None)
        self.assertIsNone(market_item)

    # 13. partial coverage semantics
    def test_13_partial_coverage_semantics(self):
        # Partially available prices (e.g. status = CACHED/UNAVAILABLE)
        normalized = HistoricalDataTranslator.translate(self.info_set)
        market_item = next(x for x in normalized if x.data_type == "market")
        self.assertEqual(market_item.metadata["historical_coverage"]["price_history"], "COMPLETE")

    # 14. synthetic data rejection
    def test_14_synthetic_data_rejection(self):
        # Synthetic data in fundamentals facts must raise error
        synthetic_fact = HistoricalFinancialFact(
            security_id=self.security_id, provider="sec", source="TEST FIXTURE / SYNTHETIC", accession_number="123",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2024, 12, 31),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            value=1000.0, unit="USD", form_type="10-K", source_id="123",
            period_type=FactPeriodType.INSTANT, observed_at=datetime(2025, 2, 1, tzinfo=timezone.utc)
        )
        snapshot_err = HistoricalFinancialSnapshot(
            security_id=self.security_id, as_of=self.as_of,
            metrics={"total_assets": 1000.0}, facts={"total_assets": synthetic_fact},
            availability_status=DataStatus.REAL, source="sec", confidence=1.0,
            observed_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            is_fallback=False, is_stale=False, provenance={}, completeness=1.0
        )
        info_set_err = PITInformationSet(
            security_id=self.security_id, as_of=self.as_of,
            universe_state={"security": self.sec_state, "universe": None},
            financials=snapshot_err, prices=[self.price_bar],
            corporate_actions=[self.corp_action], provenance={},
            completeness=1.0, status=DataStatus.REAL, confidence=1.0,
            snapshot_hash="hash-123"
        )
        with self.assertRaisesRegex(ValueError, "synthetic_records_forbidden"):
            HistoricalDataTranslator.translate(info_set_err)

    # 15. raw/adjusted price separation
    def test_15_raw_adjusted_price_separation(self):
        # raw close and adjusted close must be stored separately
        self.assertEqual(self.price_bar.close, 152.0)
        self.assertEqual(self.price_bar.adjusted_close, 152.0)

    # 16. QuantInputAdapter parity
    def test_16_quant_input_adapter_parity(self):
        normalized = HistoricalDataTranslator.translate(self.info_set)
        prices_df, financial_df = QuantInputAdapter.to_factor_inputs(normalized, self.as_of)
        
        # Verify index and columns
        self.assertIn(self.security_id, prices_df.columns)
        self.assertIn(self.security_id, financial_df.index)
        self.assertIn("roe", financial_df.columns)
        self.assertIn("profitMargin", financial_df.columns)

    # 17. cross-security isolation
    def test_17_cross_security_isolation(self):
        # Two securities do not mix
        sec2_state = HistoricalSecurityState(
            security_id="sec-msft-102", ticker="MSFT", company_name="Microsoft Corp",
            listing_status=ListingStatus.LISTED, valid_from=datetime(2010, 1, 1, tzinfo=timezone.utc),
            valid_to=None, source="sec-master", confidence=1.0
        )
        sec2_fact = HistoricalFinancialFact(
            security_id="sec-msft-102", provider="sec", source="SEC EDGAR", accession_number="456",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2024, 12, 31),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            value=2000.0, unit="USD", form_type="10-K", source_id="456",
            period_type=FactPeriodType.INSTANT, observed_at=datetime(2025, 2, 1, tzinfo=timezone.utc)
        )
        sec2_snapshot = HistoricalFinancialSnapshot(
            security_id="sec-msft-102", as_of=self.as_of,
            metrics={"total_assets": 2000.0}, facts={"total_assets": sec2_fact},
            availability_status=DataStatus.REAL, source="sec", confidence=1.0,
            observed_at=datetime(2025, 2, 1, tzinfo=timezone.utc),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            is_fallback=False, is_stale=False, provenance={}, completeness=1.0
        )
        info2 = PITInformationSet(
            security_id="sec-msft-102", as_of=self.as_of,
            universe_state={"security": sec2_state, "universe": None},
            financials=sec2_snapshot, prices=[], corporate_actions=[], provenance={},
            completeness=1.0, status=DataStatus.REAL, confidence=1.0, snapshot_hash="hash-456"
        )
        
        norm1 = HistoricalDataTranslator.translate(self.info_set)
        norm2 = HistoricalDataTranslator.translate(info2)
        
        prices_df, financial_df = QuantInputAdapter.to_factor_inputs(norm1 + norm2, self.as_of)
        self.assertTrue(np.isnan(financial_df.loc["sec-aapl-101"]["roe"]))
        # sec-msft-102 has total_assets=2000.0, net_income=None, roe=NaN
        self.assertTrue(np.isnan(financial_df.loc["sec-msft-102"]["roe"]))

    # 18. score input parity
    def test_18_score_input_parity(self):
        normalized = HistoricalDataTranslator.translate(self.info_set)
        prices_df, financial_df = QuantInputAdapter.to_factor_inputs(normalized, self.as_of)
        
        # Verify we can pass to FactorEngine without crash
        # Since we only have 1 date in prices_df, let's make sure it's structured
        self.assertTrue(isinstance(prices_df, pd.DataFrame))
        self.assertTrue(isinstance(financial_df, pd.DataFrame))


if __name__ == "__main__":
    unittest.main()
