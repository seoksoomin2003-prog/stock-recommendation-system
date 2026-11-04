import unittest
import sqlite3
import os
import tempfile
from datetime import datetime, timezone, date, timedelta
from entity.historical_data_repository import HistoricalDataRepository
from contracts.historical_data import HistoricalFinancialFact, FactPeriodType

class TestP614PITSelection(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_repo.db")
        self.repo = HistoricalDataRepository(self.db_path, allow_synthetic=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_future_filing_is_not_visible_at_earlier_as_of_date(self):
        fact = HistoricalFinancialFact(
            security_id="CIK0000320193", provider="sec_edgar", source="SEC_TEST_FIXTURE",
            accession_number="0001-24", taxonomy="us-gaap", concept="NetIncomeLoss", normalized_metric="net_income",
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31),
            filed_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
            accepted_at=datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc),
            value=1000.0, unit="USD", form_type="10-Q", fiscal_year=2024, fiscal_period="Q1",
            is_amended=False, is_restated=False, source_url="",
            observed_at=datetime(2024, 5, 1, tzinfo=timezone.utc), ingested_at=datetime(2024, 5, 2, tzinfo=timezone.utc),
            schema_version="1.0", period_type=FactPeriodType.DURATION, prevrpt=0, source_id="F1"
        )
        self.repo.add_financial_fact(fact)
        
        snapshot = self.repo.financial_snapshot("CIK0000320193", datetime(2024, 4, 30, tzinfo=timezone.utc))
        self.assertIsNone(snapshot.metrics["net_income"])
        
        snapshot = self.repo.financial_snapshot("CIK0000320193", datetime(2024, 5, 2, tzinfo=timezone.utc))
        self.assertEqual(snapshot.metrics["net_income"], 1000.0)

    def test_amendment_does_not_rewrite_prior_simulation(self):
        fact1 = HistoricalFinancialFact(
            security_id="CIK0000320193", provider="sec_edgar", source="SEC_TEST_FIXTURE",
            accession_number="0001-24", taxonomy="us-gaap", concept="NetIncomeLoss", normalized_metric="net_income",
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31),
            filed_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
            accepted_at=datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc),
            value=1000.0, unit="USD", form_type="10-Q", fiscal_year=2024, fiscal_period="Q1",
            is_amended=False, is_restated=False, source_url="",
            observed_at=datetime(2024, 5, 1, tzinfo=timezone.utc), ingested_at=datetime(2024, 5, 2, tzinfo=timezone.utc),
            schema_version="1.0", period_type=FactPeriodType.DURATION, prevrpt=0, source_id="F1"
        )
        self.repo.add_financial_fact(fact1)
        
        fact2 = HistoricalFinancialFact(
            security_id="CIK0000320193", provider="sec_edgar", source="SEC_TEST_FIXTURE",
            accession_number="0002-24", taxonomy="us-gaap", concept="NetIncomeLoss", normalized_metric="net_income",
            period_start=date(2024, 1, 1), period_end=date(2024, 3, 31),
            filed_at=datetime(2024, 6, 15, tzinfo=timezone.utc),
            accepted_at=datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc),
            value=900.0, unit="USD", form_type="10-Q/A", fiscal_year=2024, fiscal_period="Q1",
            is_amended=True, is_restated=False, source_url="",
            observed_at=datetime(2024, 6, 15, tzinfo=timezone.utc), ingested_at=datetime(2024, 6, 16, tzinfo=timezone.utc),
            schema_version="1.0", period_type=FactPeriodType.DURATION, prevrpt=0, source_id="F2"
        )
        self.repo.add_financial_fact(fact2)
        
        snapshot = self.repo.financial_snapshot("CIK0000320193", datetime(2024, 5, 20, tzinfo=timezone.utc))
        self.assertEqual(snapshot.metrics["net_income"], 1000.0)
        
        snapshot = self.repo.financial_snapshot("CIK0000320193", datetime(2024, 6, 20, tzinfo=timezone.utc))
        self.assertEqual(snapshot.metrics["net_income"], 900.0)

if __name__ == '__main__':
    unittest.main()
