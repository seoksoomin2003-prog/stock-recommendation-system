import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import QuantTradingSystemV2
from data.loader import DataLoader
from core.llm_fundamental_engine import LLMFundamentalEngine
from utils.config import DECISION_SETTINGS, EXECUTION_SETTINGS

class TestP612CLiveDataPath(unittest.TestCase):
    def setUp(self):
        self.system = QuantTradingSystemV2(mode="live", initial_capital=100000000)
    
    @patch('yfinance.download')
    def test_nan_firewall_handles_missing_data(self, mock_yf):
        # Mock yfinance to return empty or NaN data
        mock_yf.return_value = pd.DataFrame()
        
        # We expect the system to hit NO_VALID_RECOMMENDATION
        result = self.system.run_live_cycle(["INVALID1", "INVALID2"])
        
        # It should exit gracefully with "LIVE DATA UNAVAILABLE" instead of propagating NaNs
        self.assertEqual(result["status"], "LIVE DATA UNAVAILABLE")
    
    def test_live_mode_does_not_bootstrap_llm_fundamental_engine(self):
        # P6-17.4's canonical route must not require an LLM/RAG service at
        # startup; fundamental provider completeness is handled by DataLoader.
        self.assertFalse(hasattr(self.system, "fundamental_engine"))
    
    def test_capital_override(self):
        # Initial capital 1B
        sys_1b = QuantTradingSystemV2(mode="live", initial_capital=1e9)
        self.assertEqual(sys_1b.portfolio_state.cash, 1e9)

    def test_frozen_parameters_immutability(self):
        # Traceability test
        # 500k liquidity
        self.assertEqual(EXECUTION_SETTINGS.get("min_volume_threshold"), 500000)
        
        # 75th percentile BEAR threshold
        self.assertEqual(DECISION_SETTINGS.get("bear_alpha_threshold"), 0.75)

if __name__ == '__main__':
    unittest.main()
