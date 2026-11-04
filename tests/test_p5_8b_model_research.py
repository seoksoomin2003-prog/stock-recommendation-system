import unittest
import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import date, datetime, timezone, timedelta

from contracts.historical_data import HistoricalFinancialFact, FactPeriodType
from providers.historical import OfficialSecHistoricalFinancialProvider, SecUserAgentConfig
from entity.historical_data_repository import HistoricalDataRepository
from research.p6_architecture import P6ResearchInput, P6ResearchSignal, P6SignalGeneratorInterface
from scripts.run_p5_8b_model_research import classify_regimes


class TestP5_8bModelResearch(unittest.TestCase):
    
    def setUp(self):
        self.provider = OfficialSecHistoricalFinancialProvider(user_agent="TestAgent (test@example.com)")
        self.db_path = "scratch/test_research_temp.db"
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

    # 1. Concept mappings verification
    def test_01_concept_mappings(self):
        concepts = self.provider._metric_concepts
        self.assertEqual(concepts.get("SalesRevenueNet"), "revenue")
        self.assertEqual(concepts.get("ProfitLoss"), "net_income")
        self.assertEqual(concepts.get("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"), "shareholders_equity")
        self.assertEqual(concepts.get("EarningsPerShareBasic"), "eps")

    # 2. Period semantics (instant vs duration classification)
    def test_02_period_semantics(self):
        instants = self.provider._instant
        self.assertIn("total_assets", instants)
        self.assertIn("total_liabilities", instants)
        self.assertIn("shareholders_equity", instants)
        self.assertIn("shares_outstanding", instants)
        self.assertNotIn("revenue", instants)
        self.assertNotIn("net_income", instants)
        self.assertNotIn("eps", instants)

    # 3. PIT selection eligibility filters (filed_at, accepted_at, period_end)
    def test_03_pit_selection_eligibility(self):
        # Ingest facts
        f1 = HistoricalFinancialFact(
            security_id="sec-aapl-123", provider="sec", source="TEST", accession_number="acc-1",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2024, 12, 31),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            value=1000.0, unit="USD", form_type="10-K", period_type=FactPeriodType.INSTANT,
            source_id="acc-1"
        )
        self.repo.add_financial_fact(f1)
        
        # Snapshot at T = 2025-01-15 (Before filing date) -> Should be empty
        snap_before = self.repo.financial_snapshot("sec-aapl-123", datetime(2025, 1, 15, tzinfo=timezone.utc))
        self.assertIsNone(snap_before.metrics.get("total_assets"))
        
        # Snapshot at T = 2025-02-15 (After filing date) -> Should return 1000
        snap_after = self.repo.financial_snapshot("sec-aapl-123", datetime(2025, 2, 15, tzinfo=timezone.utc))
        self.assertEqual(snap_after.metrics.get("total_assets"), 1000.0)

    # 4. Amendment preference (prevrpt and accession provenance)
    def test_04_amendment_preference(self):
        f1 = HistoricalFinancialFact(
            security_id="sec-aapl-123", provider="sec", source="TEST", accession_number="acc-1",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2024, 12, 31),
            filed_at=datetime(2025, 2, 1, tzinfo=timezone.utc), accepted_at=None,
            value=1000.0, unit="USD", form_type="10-K", period_type=FactPeriodType.INSTANT,
            is_amended=True, prevrpt=1, source_id="acc-1"
        )
        # Amendment filed later
        f2 = HistoricalFinancialFact(
            security_id="sec-aapl-123", provider="sec", source="TEST", accession_number="acc-2",
            taxonomy="us-gaap", concept="Assets", normalized_metric="total_assets",
            period_start=None, period_end=date(2024, 12, 31),
            filed_at=datetime(2025, 3, 1, tzinfo=timezone.utc), accepted_at=None,
            value=1050.0, unit="USD", form_type="10-K/A", period_type=FactPeriodType.INSTANT,
            is_amended=False, prevrpt=0, source_id="acc-2"
        )
        self.repo.add_financial_fact(f1)
        self.repo.add_financial_fact(f2)
        
        # Snapshot before amendment (T = 2025-02-15) -> Should be f1 (1000.0)
        snap1 = self.repo.financial_snapshot("sec-aapl-123", datetime(2025, 2, 15, tzinfo=timezone.utc))
        self.assertEqual(snap1.metrics.get("total_assets"), 1000.0)
        
        # Snapshot after amendment (T = 2025-03-15) -> Should be f2 (1050.0)
        snap2 = self.repo.financial_snapshot("sec-aapl-123", datetime(2025, 3, 15, tzinfo=timezone.utc))
        self.assertEqual(snap2.metrics.get("total_assets"), 1050.0)

    # 5. Look-ahead free regime classification
    def test_05_lookahead_free_regime(self):
        # Create prices dataframe containing 25 dates
        dates = pd.date_range(start="2025-01-01", periods=25, freq="D")
        prices = pd.DataFrame({
            "AAPL": np.linspace(100.0, 105.0, 25) # 5% increase over 25 days
        }, index=dates)
        
        regime_dir, regime_vol = classify_regimes(prices)
        self.assertEqual(regime_dir, "BULL") # 5% > 2% -> BULL

    # 6. P6 research interface signal generation correctness
    def test_06_p6_interface_correctness(self):
        input_data = P6ResearchInput(
            security_id="sec-aapl-123",
            as_of=datetime(2025, 2, 15),
            alpha_score=2.0,
            factor_scores={"momentum": 2.5, "value": 0.5, "quality": 1.2, "low_volatility": -0.2},
            market_regime="BULL",
            confidence=0.9,
            volatility=0.02,
            trend=0.04
        )
        
        generator = P6SignalGeneratorInterface()
        signal = generator.generate_signal(input_data)
        
        self.assertEqual(signal.security_id, "sec-aapl-123")
        self.assertTrue(signal.entry_signal)
        self.assertFalse(signal.exit_signal)
        self.assertEqual(signal.risk_reward, 2.0)
        self.assertIn("momentum", signal.factor_drivers)
        self.assertIn("quality", signal.factor_drivers)
        self.assertNotIn("VOLATILITY_SPIKE", signal.invalidation_conditions)


if __name__ == "__main__":
    unittest.main()
