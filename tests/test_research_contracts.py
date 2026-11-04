import unittest
from datetime import datetime, timezone

from contracts.normalized_data import DataStatus, NormalizedData
from contracts.research import ResearchOutput, ResearchRequest
from contracts.security import IdentityStatus, SecurityIdentity


class TestResearchContracts(unittest.TestCase):
    def test_resolved_identity_requires_id(self):
        with self.assertRaises(ValueError):
            SecurityIdentity(None, identity_status=IdentityStatus.RESOLVED, resolution_confidence=1.0)

    def test_normalized_status_invariants(self):
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValueError):
            NormalizedData("s", "AAPL", "market", {}, "x", DataStatus.STALE, 0.5, now, now, now)

    def test_request_and_output_ranges(self):
        request = ResearchRequest("AAPL", horizon="20D")
        security = SecurityIdentity("s", ticker="AAPL", identity_status=IdentityStatus.RESOLVED, resolution_confidence=1.0)
        output = ResearchOutput(request.request_id, security, 0.25, 0.75, request.horizon, request.as_of)
        self.assertEqual(output.alpha_score, 0.25)
        with self.assertRaises(ValueError):
            ResearchOutput(request.request_id, security, 1.1, 0.75, request.horizon, request.as_of)

