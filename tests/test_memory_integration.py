#!/usr/bin/env python3
import sys
import os
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

import utils.config
from utils.memory_guard import MemoryGuard, MemoryProvider
from alpha_engine.system import AlphaScoringEngine

class MockMemoryProvider(MemoryProvider):
    def __init__(self, rss: float = 200.0, available: float = 4000.0):
        self.rss = rss
        self.available = available
        
    def get_process_rss(self) -> float:
        return self.rss
        
    def get_system_available(self) -> float:
        return self.available

class TestMemoryIntegration(unittest.TestCase):

    def setUp(self):
        utils.config.MEMORY_GUARD_ENABLED = True
        utils.config.APP_MODE = "local"
        utils.config.MEMORY_RECOVERY_CYCLES = 3
        
        # Populate resolver DB to make it work offline
        from alpha_engine.input.storage import TickerStorage
        storage = TickerStorage()
        try:
            aapl_id = storage.add_ticker("AAPL", "Apple Inc.")
            storage.add_alias(aapl_id, "aapl", "manual", 1.0)
        except Exception:
            pass

    def test_scenario_a_normal_memory(self):
        """Scenario A: Normal memory + AAPL -> full Alpha pipeline"""
        print("Testing Scenario A (Normal Memory)...")
        MemoryGuard.provider = MockMemoryProvider(rss=200.0)
        MemoryGuard.initialize()
        
        scoring_engine = AlphaScoringEngine()
        df = scoring_engine.run_research_pipeline("AAPL")
        
        self.assertEqual(MemoryGuard.current_state, "NORMAL")
        self.assertTrue("AAPL" in df.index)

    def test_scenario_b_warning_memory(self):
        """Scenario B: WARNING + AAPL -> Alpha pipeline continues"""
        print("Testing Scenario B (WARNING Memory)...")
        MemoryGuard.provider = MockMemoryProvider(rss=1100.0)
        MemoryGuard.initialize()
        
        # Check that memory guard starts in normal, then sampling warning moves to WARNING
        MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "WARNING")
        
        scoring_engine = AlphaScoringEngine()
        df = scoring_engine.run_research_pipeline("AAPL")
        
        self.assertTrue("AAPL" in df.index)

    def test_scenario_c_critical_memory(self):
        """Scenario C: CRITICAL + AAPL -> heavy tasks blocked -> fallback used -> final score generated"""
        print("Testing Scenario C (CRITICAL Memory)...")
        MemoryGuard.provider = MockMemoryProvider(rss=1600.0)
        MemoryGuard.initialize()
        
        MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "CRITICAL")
        
        scoring_engine = AlphaScoringEngine()
        
        # Gating must block heavy embedding, llm, and RAG
        self.assertFalse(MemoryGuard.allow("llm"))
        self.assertFalse(MemoryGuard.allow("rag"))
        self.assertFalse(MemoryGuard.allow("embedding"))
        
        # Verify pipeline still runs and produces final score
        df = scoring_engine.run_research_pipeline("AAPL")
        self.assertTrue("AAPL" in df.index)

    def test_scenario_d_emergency_memory(self):
        """Scenario D: EMERGENCY -> new heavy workload blocked"""
        print("Testing Scenario D (EMERGENCY Memory)...")
        MemoryGuard.provider = MockMemoryProvider(rss=1900.0)
        MemoryGuard.initialize()
        
        MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "EMERGENCY")
        
        # New heavy workloads blocked
        self.assertFalse(MemoryGuard.allow("llm"))
        self.assertFalse(MemoryGuard.allow("rag"))
        self.assertFalse(MemoryGuard.allow("embedding"))
        self.assertFalse(MemoryGuard.allow("new_ticker"))

    def test_scenario_e_and_f_recovery_to_normal(self):
        """Scenario E & F: memory recovered -> RECOVERY -> NORMAL"""
        print("Testing Scenario E & F (Recovery to Normal)...")
        MemoryGuard.provider = MockMemoryProvider(rss=1100.0)
        MemoryGuard.initialize()
        MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "WARNING")
        
        # Scenario E: Memory drops below recovery threshold
        MemoryGuard.provider = MockMemoryProvider(rss=700.0)
        MemoryGuard.check_and_cleanup()
        self.assertEqual(MemoryGuard.current_state, "RECOVERY")
        
        # Scenario F: Stable recovery cycles -> transitions to NORMAL
        MemoryGuard.check_and_cleanup() # cycle 2
        self.assertEqual(MemoryGuard.current_state, "RECOVERY")
        
        MemoryGuard.check_and_cleanup() # cycle 3 -> Normal
        self.assertEqual(MemoryGuard.current_state, "NORMAL")

if __name__ == "__main__":
    unittest.main()
