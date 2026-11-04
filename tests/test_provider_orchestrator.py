import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cache.repository import CacheRepository
from contracts.normalized_data import DataStatus, NormalizedData
from contracts.security import IdentityStatus, SecurityIdentity
from providers.base import ProviderContext, ProviderKind
from providers.orchestrator import ProviderOrchestrator
from providers.registry import ProviderRegistry


class FixtureMarketProvider:
    name = "fixture_market"
    kind = ProviderKind.MARKET
    ttl_seconds = 60

    def __init__(self, observed_at=None):
        self.calls = 0
        self.observed_at = observed_at

    def fetch(self, security, context):
        self.calls += 1
        return NormalizedData(security.security_id, security.ticker, "market", {"close": [1.0]}, self.name,
            DataStatus.REAL, 1.0, self.observed_at or context.as_of, datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(seconds=60), request_id=context.request_id)


class TestProviderOrchestrator(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.security = SecurityIdentity("s1", ticker="AAPL", identity_status=IdentityStatus.RESOLVED,
                                         resolution_confidence=1.0)
        self.context = ProviderContext("r1", datetime.now(timezone.utc), 365)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_cache_then_provider(self):
        registry = ProviderRegistry()
        provider = FixtureMarketProvider()
        registry.register(provider)
        engine = ProviderOrchestrator(registry, CacheRepository(str(Path(self.tempdir.name) / "cache.db")))
        self.assertEqual(engine.fetch(ProviderKind.MARKET, self.security, self.context).status, DataStatus.REAL)
        self.assertEqual(engine.fetch(ProviderKind.MARKET, self.security, self.context).status, DataStatus.CACHED)
        self.assertEqual(provider.calls, 1)

    def test_future_observation_is_rejected(self):
        registry = ProviderRegistry()
        registry.register(FixtureMarketProvider(self.context.as_of + timedelta(seconds=1)))
        engine = ProviderOrchestrator(registry, CacheRepository(str(Path(self.tempdir.name) / "cache.db")))
        result = engine.fetch(ProviderKind.MARKET, self.security, self.context)
        self.assertEqual(result.status, DataStatus.FALLBACK)

