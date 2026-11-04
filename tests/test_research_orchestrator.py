import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cache.repository import CacheRepository
from contracts.normalized_data import DataStatus, NormalizedData
from contracts.research import ResearchRequest
from contracts.security import IdentityStatus, SecurityIdentity
from entity.resolver_service import EntityResolutionService
from entity.security_master import SecurityMaster
from providers.base import ProviderKind
from providers.orchestrator import ProviderOrchestrator
from providers.registry import ProviderRegistry
from research.orchestrator import ResearchOrchestrator


class FixtureProvider:
    ttl_seconds = 60
    def __init__(self, kind, data):
        self.kind, self.name, self.data = kind, "fixture_" + kind.value, data
    def fetch(self, security, context):
        return NormalizedData(security.security_id, security.ticker, self.kind.value, self.data, self.name,
            DataStatus.REAL, 1.0, context.as_of - timedelta(days=1), datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(seconds=60), request_id=context.request_id)


class StubResolver:
    def resolve(self, query, request_id=""):
        return SecurityIdentity("aapl", ticker="AAPL", company_name="Apple Inc.",
            identity_status=IdentityStatus.RESOLVED, resolution_confidence=1.0)


class TestResearchOrchestrator(unittest.TestCase):
    def test_unknown_security_does_not_score(self):
        class Unknown:
            def resolve(self, *args): return SecurityIdentity.unresolved("bad")
        result = ResearchOrchestrator(resolver=Unknown()).research(ResearchRequest("bad"))
        self.assertEqual(result.status, "UNRESOLVED")
        self.assertIsNone(result.alpha_score)

    def test_market_failure_is_score_unavailable(self):
        registry = ProviderRegistry()
        for kind in ProviderKind:
            registry.register(FixtureProvider(kind, {}))
        with tempfile.TemporaryDirectory() as directory:
            engine = ResearchOrchestrator(StubResolver(), ProviderOrchestrator(registry, CacheRepository(str(Path(directory) / "c.db"))))
            result = engine.research(ResearchRequest("AAPL"))
        self.assertEqual(result.status, "SCORE_UNAVAILABLE")

