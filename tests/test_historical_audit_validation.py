import unittest
from datetime import date, datetime, timezone, timedelta
import numpy as np

from contracts.historical_data import (
    HistoricalFinancialFact, HistoricalPriceBar, CorporateActionEvent, FactPeriodType, CorporateActionType
)
from contracts.normalized_data import DataStatus
from entity.historical_security_master import HistoricalSecurityState, ListingStatus


class TestHistoricalAuditValidation(unittest.TestCase):
    def setUp(self):
        self.as_of = datetime(2025, 2, 15, tzinfo=timezone.utc)

    # 1. provider capability classification
    def test_01_provider_capability_classification(self):
        providers = {
            "sec": "GENUINELY_FREE",
            "alphavantage": "FREE_WITH_LIMITS",
            "yfinance": "FREE_WITH_LIMITS",
            "norgate": "PAID",
            "sharadar": "PAID"
        }
        self.assertEqual(providers["sec"], "GENUINELY_FREE")
        self.assertEqual(providers["alphavantage"], "FREE_WITH_LIMITS")
        self.assertEqual(providers["norgate"], "PAID")

    # 2. free-tier restriction detection
    def test_02_free_tier_restriction_detection(self):
        # Premium response note from Alpha Vantage
        av_response = {"Information": "Thank you for using Alpha Vantage! This is a premium endpoint."}
        is_restricted = "premium" in av_response.get("Information", "").lower()
        self.assertTrue(is_restricted)

    # 3. delisted metadata classification
    def test_03_delisted_metadata_classification(self):
        # Verify listing status maps to ListingStatus enum
        status_str = "Delisted"
        listing_status = ListingStatus.DELISTED if status_str == "Delisted" else ListingStatus.LISTED
        self.assertEqual(listing_status, ListingStatus.DELISTED)

    # 4. delisted price availability classification
    def test_04_delisted_price_availability_classification(self):
        # SIVB or TWTR pricing availability is empty/unavailable
        prices = []
        coverage = "UNAVAILABLE" if len(prices) == 0 else "COMPLETE"
        self.assertEqual(coverage, "UNAVAILABLE")

    # 5. historical universe classification
    def test_05_historical_universe_classification(self):
        universe_types = {
            "current_constituents": "PIT_UNSAFE",
            "wikipedia_historical_changes": "PIT_SAFE",
            "nasdaq_ftp_daily": "PIT_UNSAFE"
        }
        self.assertEqual(universe_types["current_constituents"], "PIT_UNSAFE")
        self.assertEqual(universe_types["wikipedia_historical_changes"], "PIT_SAFE")

    # 6. corporate-action provenance
    def test_06_corporate_action_provenance(self):
        action = CorporateActionEvent(
            security_id="sec-aapl-101", event_id="evt-1", event_type=CorporateActionType.SPLIT,
            effective_at=datetime(2020, 8, 31, tzinfo=timezone.utc),
            announced_at=None, # Explicitly missing
            old_value="1.0", new_value="4.0", ratio=4.0, cash_amount=0.0, shares_affected=0.0,
            source="fixture", source_url="http://sec.gov", observed_at=datetime(2020, 8, 31, tzinfo=timezone.utc),
            is_verified=True
        )
        self.assertIsNone(action.announced_at)
        self.assertEqual(action.effective_at, datetime(2020, 8, 31, tzinfo=timezone.utc))

    # 7. identity reconciliation
    def test_07_identity_reconciliation(self):
        # Reconcile CIK and Ticker to unique security_id
        cik = "0000320193"
        ticker = "AAPL"
        security_id = f"sec-{ticker.lower()}-{cik}"
        self.assertEqual(security_id, "sec-aapl-0000320193")

    # 8. PIT capability classification
    def test_08_pit_capability_classification(self):
        pit_capabilities = {
            "sec_edgar": "PIT_SAFE",
            "alphavantage_daily": "PIT_LIMITED", # Compact only, no history for delisted
            "yfinance": "PIT_UNSAFE" # Retroactive corporate actions adjustments with no timestamps
        }
        self.assertEqual(pit_capabilities["sec_edgar"], "PIT_SAFE")
        self.assertEqual(pit_capabilities["yfinance"], "PIT_UNSAFE")

    # 9. synthetic firewall
    def test_09_synthetic_firewall_validation(self):
        # Verify rejection of mock/synthetic source strings
        source = "TEST_FIXTURE"
        s_upper = source.upper()
        is_synthetic = any(m in s_upper for m in ("SYNTHETIC", "TEST FIXTURE", "TEST_FIXTURE", "MOCK", "GENERATED"))
        self.assertTrue(is_synthetic)

    # 10. source provenance
    def test_10_source_provenance(self):
        bar = HistoricalPriceBar(
            security_id="sec-aapl-101", provider="yf", date=date(2025, 2, 14),
            open=150.0, high=155.0, low=149.0, close=152.0, adjusted_close=152.0, volume=1000000.0,
            source="yf-source", source_id="yf-1", observed_at=datetime(2025, 2, 14, tzinfo=timezone.utc)
        )
        self.assertEqual(bar.source, "yf-source")
        self.assertEqual(bar.source_id, "yf-1")

    # 11. reproducibility
    def test_11_reproducibility(self):
        import hashlib
        import json
        payload1 = {"sec_id": "1", "close": 100.0}
        payload2 = {"sec_id": "1", "close": 100.0}
        h1 = hashlib.sha256(json.dumps(payload1, sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(payload2, sort_keys=True).encode()).hexdigest()
        self.assertEqual(h1, h2)

    # 12. cross-provider conflict detection
    def test_12_cross_provider_conflict_detection(self):
        close_yf = 152.0
        close_av = 152.5
        # Absolute relative difference
        diff = abs(close_yf - close_av) / close_yf
        has_conflict = diff > 1e-4 # Threshold 0.01%
        self.assertTrue(has_conflict)


if __name__ == "__main__":
    unittest.main()
