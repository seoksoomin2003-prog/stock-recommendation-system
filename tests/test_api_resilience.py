#!/usr/bin/env python3
import sys
import os
import requests
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # P6-19: was a hardcoded Desktop path

from utils.resilience import resilient_request, TimeoutHTTPAdapter
from utils.config import API_CONNECT_TIMEOUT, API_READ_TIMEOUT, API_MAX_RETRIES

class TestApiResilience(unittest.TestCase):

    def setUp(self):
        # Enforce short backoffs in unit tests to make it run fast
        import utils.resilience
        utils.resilience.API_BACKOFF_BASE = 0.01
        utils.resilience.API_BACKOFF_MAX = 0.05

    def test_mock_timeout_retry_success(self):
        """Test 5: attempt 1 -> timeout, attempt 2 -> timeout, attempt 3 -> success"""
        print("Testing mock timeout retry-to-success...")
        calls = []
        
        def mock_request():
            calls.append(1)
            if len(calls) < 3:
                raise requests.exceptions.ReadTimeout("Mocked read timeout")
            response = Mock()
            response.status_code = 200
            return response

        res = resilient_request(
            mock_request,
            provider="TestTimeoutSuccessProvider",
            max_retries=2
        )
        print(f"- Total call attempts: {len(calls)}, Result is: {res}")
        self.assertEqual(len(calls), 3) # 1 initial + 2 retries
        self.assertIsNotNone(res)
        self.assertEqual(res.status_code, 200)
        print("[PASS] Retry to success behaves correctly.")

    def test_http_429_retry(self):
        """Test 6: HTTP 429 -> retry occurs"""
        print("\nTesting HTTP 429 rate-limit retries...")
        calls = []

        def mock_request():
            calls.append(1)
            response = Mock()
            response.status_code = 429
            return response

        res = resilient_request(
            mock_request,
            provider="Test429Provider",
            fallback_value="NEUTRAL_FALLBACK",
            max_retries=2
        )
        print(f"- Total call attempts: {len(calls)}, Result is: {res}")
        self.assertEqual(len(calls), 3) # 1 initial + 2 retries
        self.assertEqual(res, "NEUTRAL_FALLBACK")
        print("[PASS] HTTP 429 retry triggered correctly.")

    def test_http_401_no_retry(self):
        """Test 7: HTTP 401 -> retry does NOT occur"""
        print("\nTesting HTTP 401 unauthorized (no retry)...")
        calls = []

        def mock_request():
            calls.append(1)
            response = Mock()
            response.status_code = 401
            return response

        res = resilient_request(
            mock_request,
            provider="Test401Provider",
            fallback_value="NEUTRAL_FALLBACK",
            max_retries=2
        )
        print(f"- Total call attempts: {len(calls)}, Result is: {res}")
        self.assertEqual(len(calls), 1) # Fails on first attempt without retrying
        self.assertEqual(res, "NEUTRAL_FALLBACK")
        print("[PASS] HTTP 401 bypasses retries successfully.")

    def test_all_retries_fail_fallback(self):
        """Test 8 & 9: All retries fail -> fallback returned, no crash, no loop, max attempts validated"""
        print("\nTesting terminal failure fallback and retry bounds...")
        calls = []

        def mock_request():
            calls.append(1)
            raise requests.exceptions.ConnectTimeout("Mocked connect timeout")

        res = resilient_request(
            mock_request,
            provider="TestTerminalFailProvider",
            fallback_value="FALLBACK_VAL",
            max_retries=2
        )
        print(f"- Total call attempts: {len(calls)}, Result is: {res}")
        self.assertEqual(len(calls), 3) # 1 initial + 2 retries
        self.assertEqual(res, "FALLBACK_VAL")
        print("[PASS] Terminal failure returns fallback cleanly and adheres to max_retries boundary.")

    def test_timeout_parameters_passed(self):
        """Test 10: Verify timeout is passed to every audited network provider"""
        print("\nTesting centralized timeout adapter parameter enforcement...")
        
        # Instantiate adapter
        adapter = TimeoutHTTPAdapter(timeout=(99, 88))
        req = requests.Request('GET', 'http://example.com').prepare()
        
        # Mocking the send method of HTTPAdapter to assert kwargs
        with patch('requests.adapters.HTTPAdapter.send') as mock_send:
            adapter.send(req)
            _, kwargs = mock_send.call_args
            print(f"- Enforced timeout arguments: {kwargs.get('timeout')}")
            self.assertEqual(kwargs.get('timeout'), (99, 88))

        print("[PASS] Timeout parameters successfully bound and passed via Adapter.")

if __name__ == "__main__":
    unittest.main()
