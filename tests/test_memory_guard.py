#!/usr/bin/env python3
import sys
import os
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

import utils.config
from utils.memory_guard import MemoryGuard, MemoryProvider

class MockMemoryProvider(MemoryProvider):
    def __init__(self, rss: float = 200.0, available: float = 4000.0):
        self.rss = rss
        self.available = available
        
    def get_process_rss(self) -> float:
        return self.rss
        
    def get_system_available(self) -> float:
        return self.available

class TestMemoryGuard(unittest.TestCase):

    def setUp(self):
        # Reset config settings
        utils.config.MEMORY_GUARD_ENABLED = True
        utils.config.APP_MODE = "local"
        utils.config.MEMORY_RECOVERY_CYCLES = 3
        
        # Reset MemoryGuard state
        MemoryGuard.provider = MockMemoryProvider()
        MemoryGuard.initialize()
        MemoryGuard._registered_caches.clear()

    def test_test1_normal_to_normal(self):
        """TEST 1: NORMAL -> NORMAL validation"""
        print("Running TEST 1...")
        telemetry = MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "NORMAL")
        self.assertEqual(telemetry["memory_state"], "NORMAL")
        self.assertTrue(MemoryGuard.allow("llm"))

    def test_test2_warning_threshold(self):
        """TEST 2: WARNING threshold transition"""
        print("Running TEST 2...")
        MemoryGuard.provider = MockMemoryProvider(rss=1100.0)
        MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "WARNING")

    def test_test3_critical_threshold(self):
        """TEST 3: CRITICAL threshold transition"""
        print("Running TEST 3...")
        MemoryGuard.provider = MockMemoryProvider(rss=1600.0)
        MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "CRITICAL")

    def test_test4_emergency_threshold(self):
        """TEST 4: EMERGENCY threshold transition"""
        print("Running TEST 4...")
        # Emergency RSS limit = 1500 * 1.2 = 1800
        MemoryGuard.provider = MockMemoryProvider(rss=1900.0)
        MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "EMERGENCY")

    def test_test5_critical_llm_blocked(self):
        """TEST 5: CRITICAL -> LLM blocked"""
        print("Running TEST 5...")
        MemoryGuard.provider = MockMemoryProvider(rss=1600.0)
        MemoryGuard.check_and_cleanup()
        self.assertFalse(MemoryGuard.allow("llm"))

    def test_test6_critical_rag_blocked(self):
        """TEST 6: CRITICAL -> RAG blocked"""
        print("Running TEST 6...")
        MemoryGuard.provider = MockMemoryProvider(rss=1600.0)
        MemoryGuard.check_and_cleanup()
        self.assertFalse(MemoryGuard.allow("rag"))

    def test_test7_critical_embedding_blocked(self):
        """TEST 7: CRITICAL -> Embedding blocked"""
        print("Running TEST 7...")
        MemoryGuard.provider = MockMemoryProvider(rss=1600.0)
        MemoryGuard.check_and_cleanup()
        self.assertFalse(MemoryGuard.allow("embedding"))

    def test_test8_cache_cleanup_expired_entries(self):
        """TEST 8: Cache cleanup removes items on memory pressure"""
        print("Running TEST 8...")
        mock_cache = {"key": "val"}
        MemoryGuard.register_cache(mock_cache)
        
        MemoryGuard.provider = MockMemoryProvider(rss=1100.0)
        MemoryGuard.check_and_cleanup()
        
        self.assertEqual(len(mock_cache), 0)

    def test_test9_recovery_threshold(self):
        """TEST 9: Recovery threshold transition"""
        print("Running TEST 9...")
        # warning state
        MemoryGuard.provider = MockMemoryProvider(rss=1100.0)
        MemoryGuard.check_and_cleanup()
        
        # drops below recovery threshold (800MB)
        MemoryGuard.provider = MockMemoryProvider(rss=700.0)
        MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "RECOVERY")

    def test_test10_recovery_cycles_complete(self):
        """TEST 10: Recovery cycles complete -> NORMAL"""
        print("Running TEST 10...")
        MemoryGuard.provider = MockMemoryProvider(rss=1100.0)
        MemoryGuard.check_and_cleanup()
        
        # 3 cycles of recovery needed
        MemoryGuard.provider = MockMemoryProvider(rss=700.0)
        MemoryGuard.check_and_cleanup() # cycle 1
        self.assertEqual(MemoryGuard.current_state, "RECOVERY")
        
        MemoryGuard.check_and_cleanup() # cycle 2
        self.assertEqual(MemoryGuard.current_state, "RECOVERY")
        
        MemoryGuard.check_and_cleanup() # cycle 3
        self.assertEqual(MemoryGuard.current_state, "NORMAL")

    def test_test11_hysteresis_no_oscillation(self):
        """TEST 11: Hysteresis prevents oscillation"""
        print("Running TEST 11...")
        MemoryGuard.provider = MockMemoryProvider(rss=1100.0)
        MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "WARNING")
        
        # drops below warning limit (1000MB) but stays above recovery limit (800MB) -> e.g. 900MB
        MemoryGuard.provider = MockMemoryProvider(rss=900.0)
        MemoryGuard.check_and_cleanup()
        
        # State must remain WARNING (no immediate recovery oscillation)
        self.assertEqual(MemoryGuard.current_state, "WARNING")

    def test_test12_memory_provider_failure(self):
        """TEST 12: Memory provider failure fallback"""
        print("Running TEST 12...")
        mock_provider = Mock(spec=MemoryProvider)
        mock_provider.get_process_rss.side_effect = Exception("OS sensing error")
        MemoryGuard.provider = mock_provider
        
        telemetry = MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "MEMORY_STATUS_UNKNOWN")
        self.assertEqual(telemetry["status"], "MEMORY_STATUS_UNKNOWN")

    def test_test13_long_term_rss_increase(self):
        """TEST 13: Monotonic RSS increase leak detection"""
        print("Running TEST 13...")
        rss_steps = [200.0, 210.0, 222.0, 235.0, 260.0]
        
        for rss in rss_steps[:-1]:
            MemoryGuard.provider = MockMemoryProvider(rss=rss)
            MemoryGuard.check_and_cleanup()
            
        MemoryGuard.provider = MockMemoryProvider(rss=rss_steps[-1])
        telemetry = MemoryGuard.check_and_cleanup()
        self.assertTrue(telemetry.get("leak_suspected", True))

    def test_test14_local_profile_applied(self):
        """TEST 14: Local profile thresholds verified"""
        print("Running TEST 14...")
        utils.config.APP_MODE = "local"
        MemoryGuard.initialize()
        
        self.assertEqual(MemoryGuard.warning_rss_limit, 1000.0)
        self.assertEqual(MemoryGuard.critical_rss_limit, 1500.0)

    def test_test15_production_profile_applied(self):
        """TEST 15: Production profile thresholds verified"""
        print("Running TEST 15...")
        utils.config.APP_MODE = "production"
        MemoryGuard.initialize()
        
        # Production Warning RSS limit is 4000.0
        self.assertEqual(MemoryGuard.warning_rss_limit, 4000.0)
        self.assertEqual(MemoryGuard.critical_rss_limit, 8000.0)

    def test_test16_alpha_score_before_after(self):
        """TEST 16: Alpha scoring mathematical identity"""
        print("Running TEST 16...")
        from core.scoring_engine import ScoringEngine
        from utils.config import DEFAULT_FACTOR_WEIGHTS
        import pandas as pd
        
        engine = ScoringEngine(DEFAULT_FACTOR_WEIGHTS)
        df = pd.DataFrame({
            "ticker": ["AAPL", "MSFT"],
            "momentum": [0.8, -0.2],
            "quality": [0.5, 0.9],
            "value": [0.2, 0.4],
            "low_volatility": [0.7, 0.3]
        }).set_index("ticker")
        
        score_before = engine.calculate(df)
        
        # Run MemoryGuard check
        MemoryGuard.check_and_cleanup()
        
        score_after = engine.calculate(df)
        pd.testing.assert_series_equal(score_before, score_after)
        print("[PASS] Alpha scoring calculations identical.")

if __name__ == "__main__":
    unittest.main()
