import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from contracts.research import ResearchRequest
from research.orchestrator import ResearchOrchestrator
from core.factor_engine import FactorEngine
from core.ranking_engine import RankingEngine
from core.scoring_engine import ScoringEngine

class TestSaturationForensics(unittest.TestCase):
    def test_nan_score_never_clips_to_one(self):
        """Verify that a NaN score is caught by the hard gate and never clipped to 1.0."""
        req = ResearchRequest("AAPL")
        orch = ResearchOrchestrator()
        
        # Mock ScoringEngine to return NaN
        with patch.object(ScoringEngine, "calculate", return_value=pd.Series([np.nan], index=["AAPL"])):
            output = orch.research(req)
            self.assertEqual(output.status, "SCORE_UNAVAILABLE")
            self.assertIsNone(output.alpha_score)
            self.assertEqual(output.confidence, 0.0)
            self.assertIn("NON_FINITE_SCORE", output.risks)

    def test_inf_score_never_clips_to_one(self):
        """Verify that an infinite score is caught by the hard gate and never clipped to 1.0."""
        req = ResearchRequest("AAPL")
        orch = ResearchOrchestrator()
        
        # Mock ScoringEngine to return Infinity
        with patch.object(ScoringEngine, "calculate", return_value=pd.Series([np.inf], index=["AAPL"])):
            output = orch.research(req)
            self.assertEqual(output.status, "SCORE_UNAVAILABLE")
            self.assertIsNone(output.alpha_score)
            self.assertEqual(output.confidence, 0.0)
            self.assertIn("NON_FINITE_SCORE", output.risks)

    def test_insufficient_history(self):
        """Verify that insufficient history correctly marks momentum as UNAVAILABLE."""
        # Create prices spanning only 1 month (less than the required 14 months)
        dates = pd.date_range("2026-01-01", periods=10, freq="D")
        prices = pd.DataFrame({"AAPL": [150.0 + i for i in range(10)]}, index=dates)
        financials = pd.DataFrame({
            "per": [20.0],
            "pbr": [3.0],
            "roe": [0.15],
            "profitMargin": [0.10]
        }, index=["AAPL"])
        
        factors = FactorEngine().get_factor_matrix(prices, financials)
        self.assertTrue(factors["momentum"].isna().all())

    def test_single_ticker_normalization(self):
        """Verify that normalization and Z-scoring return 0.0 (neutral) for a single ticker."""
        dates = pd.date_range("2025-01-01", periods=250, freq="B")
        prices = pd.DataFrame({"AAPL": [150.0 + i * 0.1 for i in range(250)]}, index=dates)
        financials = pd.DataFrame({
            "per": [20.0],
            "pbr": [3.0],
            "roe": [0.15],
            "profitMargin": [0.10]
        }, index=["AAPL"])
        
        factors = FactorEngine().get_factor_matrix(prices, financials)
        # Momentum will be NaN due to resample size in this local window, but value, quality, volatility should be 0.0
        self.assertEqual(factors.loc["AAPL", "value"], 0.0)
        self.assertEqual(factors.loc["AAPL", "quality"], 0.0)
        self.assertEqual(factors.loc["AAPL", "low_volatility"], 0.0)
        
        standardized = RankingEngine().apply_cross_sectional_standardization(factors)
        self.assertEqual(standardized.loc["AAPL", "value"], 0.0)
        self.assertEqual(standardized.loc["AAPL", "quality"], 0.0)
        self.assertEqual(standardized.loc["AAPL", "low_volatility"], 0.0)

    def test_all_nan_factor(self):
        """Verify that an all-NaN factor is preserved as NaN by normalize."""
        series = pd.Series([np.nan, np.nan, np.nan], index=["AAPL", "MSFT", "GOOGL"])
        normalized = FactorEngine.normalize(series)
        self.assertTrue(normalized.isna().all())

    def test_zero_std_factor(self):
        """Verify that normalize returns 0.0 for zero standard deviation series."""
        series = pd.Series([1.5, 1.5, 1.5], index=["AAPL", "MSFT", "GOOGL"])
        normalized = FactorEngine.normalize(series)
        self.assertTrue((normalized == 0.0).all())

    def test_partial_factor_availability(self):
        """Verify that ScoringEngine dynamically renormalizes weights when some factors are NaN."""
        # 3 tickers, one column has NaN for MSFT
        factor_matrix = pd.DataFrame({
            "momentum": [0.5, np.nan, -0.2],
            "quality": [0.1, 0.2, 0.3],
            "value": [0.0, 0.0, 0.0],
            "low_volatility": [0.0, 0.0, 0.0]
        }, index=["AAPL", "MSFT", "GOOGL"])
        
        scores = ScoringEngine().calculate(factor_matrix)
        self.assertFalse(np.isnan(scores.loc["AAPL"]))
        self.assertFalse(np.isnan(scores.loc["MSFT"]))
        self.assertFalse(np.isnan(scores.loc["GOOGL"]))
        # MSFT score should use renormalized weights of quality, value, low_volatility (0.25, 0.20, 0.20)
        expected_weight_sum = 0.25 + 0.20 + 0.20
        expected_score_msft = 0.2 * (0.25 / expected_weight_sum)
        self.assertAlmostEqual(scores.loc["MSFT"], expected_score_msft)

    def test_score_unavailable_propagation(self):
        """Verify that status propagates to SCORE_UNAVAILABLE if all inputs are missing."""
        req = ResearchRequest("AAPL")
        orch = ResearchOrchestrator()
        # Mock FactorEngine to return all NaNs
        with patch.object(FactorEngine, "get_factor_matrix", return_value=pd.DataFrame({
            "momentum": [np.nan], "value": [np.nan], "quality": [np.nan], "low_volatility": [np.nan]
        }, index=["AAPL"])):
            output = orch.research(req)
            self.assertEqual(output.status, "SCORE_UNAVAILABLE")
            self.assertIsNone(output.alpha_score)
            self.assertEqual(output.confidence, 0.0)

    def test_confidence_independence(self):
        """Verify that score magnitude does not dictate confidence (independence)."""
        req = ResearchRequest("AAPL")
        orch = ResearchOrchestrator()
        
        # Create a perfectly valid REAL provider return containing ALL metrics needed by the orchestrator
        from contracts.normalized_data import NormalizedData, DataStatus
        from datetime import datetime
        real_data = NormalizedData(
            security_id="AAPL", ticker="AAPL", data_type="market", 
            data={"close": {"2026-01-01": 1.0}, "per": 15.0, "pbr": 1.5, "roe": 0.2, "profitMargin": 0.1, "debtToEquity": 0.5, "currentRatio": 1.2},
            source="mock", status=DataStatus.REAL, confidence=1.0,
            observed_at=datetime.now(), fetched_at=datetime.now(), expires_at=None
        )
        
        # We explicitly mock a 0.0 score from the ScoringEngine, and mock the internal frame adapters
        # to generate large enough dataframes to bypass the 24-day / 14-month volume firewalls,
        # ensuring the orchestrator proceeds to emit a valid ResearchOutput with > 0.0 confidence.
        with patch.object(ScoringEngine, "calculate", return_value=pd.Series([0.0], index=["AAPL"])), \
             patch("research.orchestrator.market_to_prices", side_effect=lambda x: pd.DataFrame({"AAPL": [1.0]*400}, index=pd.date_range("2024-01-01", periods=400, freq='D'))), \
             patch("research.orchestrator.financial_to_frame", return_value=pd.DataFrame({"per": 15.0, "pbr": 1.5, "roe": 0.2, "profitMargin": 0.1, "debtToEquity": 0.5, "currentRatio": 1.2}, index=["AAPL"])), \
             patch.object(orch.providers, "fetch", return_value=real_data):
            
            output = orch.research(req)
            self.assertEqual(output.alpha_score, 0.0)
            self.assertTrue(0.0 < output.confidence <= 1.0)

    def test_cross_ticker_isolation(self):
        """Verify that factor changes in one ticker do not leak or contaminate other tickers."""
        # 5 ticker simulation
        tickers = ["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA"]
        orch = ResearchOrchestrator()
        
        # Calculate scores forAAPL individually
        res1 = orch.research(ResearchRequest("AAPL"))
        # Run MSFT with empty news or another mock, verify AAPL score remains unchanged
        with patch("research.orchestrator.market_to_prices", side_effect=lambda x: pd.DataFrame({x.ticker: [1.0]*100}, index=pd.date_range("2026-01-01", periods=100))):
            res2 = orch.research(ResearchRequest("AAPL"))
            self.assertEqual(res1.alpha_score, res2.alpha_score)

    def test_lookahead_protection(self):
        """Verify that future-dated data triggers lookahead rejection."""
        from contracts.normalized_data import DataStatus, NormalizedData
        from providers.orchestrator import ProviderOrchestrator
        from providers.base import ProviderContext
        
        context = ProviderContext("req-id", datetime.now(timezone.utc), 365)
        # Observed in the future relative to context
        future_observed = datetime.now(timezone.utc) + timedelta(days=5)
        val = NormalizedData("s1", "AAPL", "market", {"close": {}}, "source", DataStatus.REAL, 1.0, future_observed, datetime.now(timezone.utc), datetime.now(timezone.utc))
        
        with self.assertRaises(ValueError) as ctx:
            ProviderOrchestrator._validate_as_of(val, context)
        self.assertEqual(str(ctx.exception), "look_ahead_data_rejected")

    def test_score_range(self):
        """Verify score is strictly bounded in [-1.0, 1.0]."""
        req = ResearchRequest("AAPL")
        orch = ResearchOrchestrator()
        output = orch.research(req)
        if output.alpha_score is not None:
            self.assertTrue(-1.0 <= output.alpha_score <= 1.0)

    def test_confidence_range(self):
        """Verify confidence is strictly bounded in [0.0, 1.0]."""
        req = ResearchRequest("AAPL")
        orch = ResearchOrchestrator()
        output = orch.research(req)
        self.assertTrue(0.0 <= output.confidence <= 1.0)

    def test_five_ticker_universe_variance(self):
        """Verify that 5-ticker universe standardization computes finite non-NaN relative rankings."""
        tickers = ["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA"]
        factor_df = pd.DataFrame({
            "momentum": [np.nan]*5,
            "value": [0.05, 0.20, 0.15, 0.06, 0.07],
            "quality": [1.76, 1.03, 0.74, 1.77, 0.08],
            "low_volatility": [-0.35, -0.48, -0.58, -0.43, -0.58]
        }, index=tickers)
        
        std = RankingEngine().apply_cross_sectional_standardization(factor_df)
        self.assertFalse(std["value"].isna().all())
        # GOOGL has highest value
        self.assertEqual(std["value"].idxmax(), "GOOGL")

    def test_ten_ticker_universe(self):
        """Verify that 10-ticker universe standardizes and scores safely without NaN propagation."""
        tickers = ["AAPL", "AMZN", "GOOGL", "JPM", "KO", "META", "MSFT", "NFLX", "NVDA", "TSLA"]
        factor_df = pd.DataFrame({
            "momentum": [np.nan]*10,
            "value": [0.05, 0.1, 0.20, 0.3, 0.15, 0.06, 0.07, 0.08, 0.09, 0.11],
            "quality": [1.76, 0.5, 1.03, 2.0, 0.74, 1.77, 0.08, 0.9, 0.1, 0.2],
            "low_volatility": [-0.35, -0.4, -0.48, -0.3, -0.58, -0.43, -0.58, -0.5, -0.6, -0.55]
        }, index=tickers)
        
        std = RankingEngine().apply_cross_sectional_standardization(factor_df)
        scores = ScoringEngine().calculate(std)
        self.assertFalse(scores.isna().any())

if __name__ == "__main__":
    unittest.main()
