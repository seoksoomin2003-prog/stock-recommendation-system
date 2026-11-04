import unittest
from datetime import datetime, timezone, timedelta
from core.decision_engine import DecisionEngine
from contracts.decision import LifecycleState, ActionEnum

class TestP611BTradingLogic(unittest.TestCase):
    
    def setUp(self):
        self.engine = DecisionEngine()
        self.today = datetime.now(timezone.utc)
        
    def test_alpha_entry_separation(self):
        """Test #1: Alpha / Entry Separation"""
        c1 = {"security_id": "S1", "ticker": "T1", "close": 100, "volume": 1e6, "alpha": 1.0, "atr": 2, "ema20": 90, "entry_readiness": 1.0}
        c2 = {"security_id": "S2", "ticker": "T2", "close": 100, "volume": 1e6, "alpha": 1.0, "atr": 2, "ema20": 110, "entry_readiness": 0.0}
        
        # Alpha is identical, but readiness differs. The ranker should treat them differently based on readiness.
        portfolio = self.engine.evaluate_portfolio(self.today, 100000, "BULL", [c1, c2])
        self.assertEqual(portfolio.top5[0].ticker, "T1")
        
    def test_exit_hierarchy_hard_stop_priority(self):
        """Test #16, #17: Hard stop beats thesis invalidation."""
        pos = {
            "security_id": "S1", "ticker": "T1", "lifecycle_state": LifecycleState.FULL_POSITION,
            "entry_1_weight": 0.4, "entry_2_weight": 0.6, "hard_stop": 90, "trailing_stop": 85,
            "entry_date": self.today.isoformat()
        }
        
        mkt = {"close": 89, "ema20": 95, "atr": 2, "alpha": 0.5, "volatility": 0.02} # Close < Hard Stop, Close < EMA20
        
        decision = self.engine.evaluate_existing_position(self.today, pos, mkt)
        self.assertEqual(decision.action, ActionEnum.EXIT_CANDIDATE)
        self.assertEqual(decision.exit_reason, "HARD_STOP")

    def test_exit_hierarchy_thesis_invalidation(self):
        """Test #17: Thesis Invalidation triggers before trailing stop."""
        pos = {
            "security_id": "S1", "ticker": "T1", "lifecycle_state": LifecycleState.FULL_POSITION,
            "entry_1_weight": 0.4, "entry_2_weight": 0.6, "hard_stop": 80, "trailing_stop": 85,
            "entry_date": self.today.isoformat()
        }
        
        mkt = {"close": 88, "ema20": 90, "atr": 2, "alpha": 0.5, "volatility": 0.02} # Close > Hard/Trailing, Close < EMA20
        
        decision = self.engine.evaluate_existing_position(self.today, pos, mkt)
        self.assertEqual(decision.action, ActionEnum.EXIT_CANDIDATE)
        self.assertEqual(decision.exit_reason, "THESIS_INVALIDATION")

    def test_entry_2_ema_wait(self):
        """Test #4, #5: Entry #2 waits for EMA20."""
        pos = {
            "security_id": "S1", "ticker": "T1", "lifecycle_state": LifecycleState.ENTRY_1_EXECUTED,
            "entry_1_weight": 0.4, "entry_2_weight": 0.6, "hard_stop": 80, "trailing_stop": 85,
            "entry_date": self.today.isoformat()
        }
        
        # EMA20 > Close, should wait
        mkt = {"close": 100, "ema20": 105, "atr": 2, "alpha": 0.5, "volatility": 0.02} 
        
        decision = self.engine.evaluate_existing_position(self.today, pos, mkt)
        self.assertEqual(decision.action, ActionEnum.HOLD)
        self.assertEqual(decision.entry_stage, LifecycleState.ENTRY_2_PENDING)

    def test_entry_2_ema_trigger(self):
        """Test #3: Entry #2 confirmed."""
        pos = {
            "security_id": "S1", "ticker": "T1", "lifecycle_state": LifecycleState.ENTRY_2_PENDING,
            "entry_1_weight": 0.4, "entry_2_weight": 0.6, "hard_stop": 80, "trailing_stop": 85,
            "entry_date": self.today.isoformat()
        }
        
        # EMA20 < Close, should trigger
        mkt = {"close": 100, "ema20": 95, "atr": 2, "alpha": 0.5, "volatility": 0.02} 
        
        decision = self.engine.evaluate_existing_position(self.today, pos, mkt)
        self.assertEqual(decision.action, ActionEnum.BUY_CANDIDATE)
        self.assertEqual(decision.entry_stage, LifecycleState.FULL_POSITION)

    def test_reentry_cooldown(self):
        """Test #21: Re-entry cooldown applies."""
        cooldown_until = self.today + timedelta(days=2)
        c1 = {"security_id": "S1", "ticker": "T1", "close": 100, "volume": 1e6, "alpha": 1.0, "atr": 2, "ema20": 90, "entry_readiness": 1.0, "reentry_cooldown_until": cooldown_until}
        
        portfolio = self.engine.evaluate_portfolio(self.today, 100000, "BULL", [c1])
        
        self.assertEqual(len(portfolio.top5), 0)
        self.assertEqual(len(portfolio.watchlist5), 1)
        self.assertIn("COOLDOWN_ACTIVE", portfolio.watchlist5[0].reason_codes)

if __name__ == "__main__":
    unittest.main()
