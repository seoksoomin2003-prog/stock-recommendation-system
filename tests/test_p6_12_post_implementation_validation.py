import unittest
from datetime import datetime, timezone, timedelta
from core.decision_engine import DecisionEngine
from contracts.decision import LifecycleState, ActionEnum

class TestP612PostImplementationValidation(unittest.TestCase):
    def setUp(self):
        self.engine = DecisionEngine()
        self.today = datetime.now(timezone.utc)

    def test_production_decision_engine_is_used(self):
        """Test #1: Ensures production engine is callable."""
        self.assertIsNotNone(self.engine)

    def test_entry_1_40_percent_allocation(self):
        """Test #3: Entry #1 targets 40% of the risk budget per allocation."""
        c1 = {"security_id": "S1", "ticker": "T1", "close": 100, "volume": 1e6, "alpha": 1.0, "atr": 2, "ema20": 90, "entry_readiness": 1.0}
        portfolio = self.engine.evaluate_portfolio(self.today, 100000, "BULL", [c1])
        self.assertEqual(len(portfolio.top5), 1)
        top_decision = portfolio.top5[0]
        self.assertAlmostEqual(top_decision.entry_1_weight, top_decision.target_weight * 0.40)

    def test_entry_2_60_percent_allocation(self):
        """Test #4: Entry #2 targets 60% of the risk budget per allocation."""
        c1 = {"security_id": "S1", "ticker": "T1", "close": 100, "volume": 1e6, "alpha": 1.0, "atr": 2, "ema20": 90, "entry_readiness": 1.0}
        portfolio = self.engine.evaluate_portfolio(self.today, 100000, "BULL", [c1])
        top_decision = portfolio.top5[0]
        self.assertAlmostEqual(top_decision.entry_2_weight, top_decision.target_weight * 0.60)

    def test_failed_entry_2_remains_cash(self):
        """Test #6: Failed Entry #2 condition remains cash (Wait for EMA20)."""
        pos = {
            "security_id": "S1", "ticker": "T1", "lifecycle_state": LifecycleState.ENTRY_1_EXECUTED,
            "entry_1_weight": 0.4, "entry_2_weight": 0.6, "hard_stop": 80, "trailing_stop": 85,
            "entry_date": self.today.isoformat()
        }
        # EMA20 > Close -> Fail condition
        mkt = {"close": 100, "ema20": 105, "atr": 2, "alpha": 0.5, "volatility": 0.02} 
        
        decision = self.engine.evaluate_existing_position(self.today, pos, mkt)
        self.assertEqual(decision.action, ActionEnum.HOLD)
        self.assertEqual(decision.entry_stage, LifecycleState.ENTRY_2_PENDING)

    def test_bear_stricter_entry(self):
        """Test #7: BEAR regime uses stricter threshold."""
        c1 = {"security_id": "S1", "ticker": "T1", "close": 100, "volume": 1e6, "alpha": 0.5, "alpha_percentile": 0.60, "atr": 2, "ema20": 90, "entry_readiness": 1.0}
        
        # Bull accepts
        bull_port = self.engine.evaluate_portfolio(self.today, 100000, "BULL", [c1])
        self.assertEqual(len(bull_port.top5), 1)

        # Bear rejects due to < 0.75 threshold
        bear_port = self.engine.evaluate_portfolio(self.today, 100000, "BEAR", [c1])
        self.assertEqual(len(bear_port.top5), 0)

    def test_hard_stop_priority(self):
        """Test #9: Hard stop beats other exit logic."""
        pos = {
            "security_id": "S1", "ticker": "T1", "lifecycle_state": LifecycleState.FULL_POSITION,
            "entry_1_weight": 0.4, "entry_2_weight": 0.6, "hard_stop": 90, "trailing_stop": 85,
            "entry_date": self.today.isoformat()
        }
        mkt = {"close": 89, "ema20": 95, "atr": 2, "alpha": 0.5, "volatility": 0.02}
        decision = self.engine.evaluate_existing_position(self.today, pos, mkt)
        self.assertEqual(decision.exit_reason, "HARD_STOP")

    def test_technology_40_percent_cap(self):
        """Test #14: Technology sector is capped at 40% (2 items out of 5 top slots)."""
        candidates = []
        for i in range(5):
            candidates.append({
                "security_id": f"S{i}", "ticker": f"T{i}", "close": 100, "volume": 1e6, 
                "alpha": 1.0, "atr": 2, "ema20": 90, "entry_readiness": 1.0, "sector": "Technology"
            })
        
        portfolio = self.engine.evaluate_portfolio(self.today, 100000, "BULL", candidates)
        self.assertEqual(len(portfolio.top5), 2)
        self.assertEqual(len(portfolio.watchlist5), 3)

    def test_individual_30_percent_cap(self):
        """Test #15: Individual position capped at 30%."""
        c1 = {"security_id": "S1", "ticker": "T1", "close": 100, "volume": 1e6, "alpha": 1.0, "atr": 2, "ema20": 90, "entry_readiness": 1.0}
        portfolio = self.engine.evaluate_portfolio(self.today, 100000, "BULL", [c1])
        top_decision = portfolio.top5[0]
        self.assertTrue(top_decision.target_weight <= 0.30)

if __name__ == "__main__":
    unittest.main()
