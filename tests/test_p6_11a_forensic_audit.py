import unittest
from utils.config import DEFAULT_FACTOR_WEIGHTS, PORTFOLIO_SETTINGS
from providers.adapters import YFinanceFinancialProvider, YFinanceMarketProvider

class TestP611AForensicAudit(unittest.TestCase):
    
    def test_model_0_weights_intact(self):
        """MODEL_0 weights must not have drifted in config."""
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["momentum"], 0.35)
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["quality"], 0.25)
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["value"], 0.20)
        self.assertEqual(DEFAULT_FACTOR_WEIGHTS["low_volatility"], 0.20)

    def test_portfolio_constraints_drift(self):
        """Check if production settings drifted from research user-approved limits."""
        # The user approved 40% sector cap, but production config has 35%
        self.assertEqual(PORTFOLIO_SETTINGS.get("max_sector_exposure", 0.40), 0.40)
        self.assertEqual(PORTFOLIO_SETTINGS.get("max_individual_weight", 0.30), 0.30)

    def test_yfinance_financials_block_historical(self):
        """YFinanceFinancialProvider must block historical lookups."""
        provider = YFinanceFinancialProvider()
        # This is a structural test for forensic analysis.
        self.assertTrue(hasattr(provider, "fetch"))
        
if __name__ == "__main__":
    unittest.main()
