import unittest
import sqlite3
import tempfile
import ast
import pathlib
import datetime
from datetime import timezone, timedelta
from unittest.mock import Mock, patch
import pandas as pd

from application.query_service import QueryService
from research.orchestrator import ResearchOrchestrator
from entity.security_master import SecurityMaster
from entity.resolver_service import EntityResolutionService
from contracts.security import IdentityStatus, SecurityIdentity
from contracts.normalized_data import DataStatus, NormalizedData
from contracts.research import ResearchRequest, ResearchOutput
from providers.base import ProviderContext, ProviderKind
from providers.orchestrator import ProviderOrchestrator
from providers.registry import ProviderRegistry
from cache.repository import CacheRepository


class FixtureMarketProvider:
    name = "fixture_market"
    kind = ProviderKind.MARKET
    ttl_seconds = 60
    def fetch(self, security, context):
        return NormalizedData(security.security_id, security.ticker, "market", {"close": {"2026-03-20": 150.0}}, self.name,
            DataStatus.REAL, 0.9, context.as_of, datetime.datetime.now(timezone.utc),
            datetime.datetime.now(timezone.utc) + timedelta(seconds=60), request_id=context.request_id)


class FixtureFinancialProvider:
    name = "fixture_financial"
    kind = ProviderKind.FINANCIAL
    ttl_seconds = 60
    def fetch(self, security, context):
        return NormalizedData(security.security_id, security.ticker, "financial", {"per": 25.0, "pbr": 3.0, "roe": 0.2, "profitMargin": 0.15}, self.name,
            DataStatus.REAL, 0.8, context.as_of, datetime.datetime.now(timezone.utc),
            datetime.datetime.now(timezone.utc) + timedelta(seconds=60), request_id=context.request_id)


class TestCanonicalCutover(unittest.TestCase):
    def setUp(self):
        # We will use the production tickers.db for entity resolution tests
        # as it already has "구글", "테슬라", "AAPL", "MSFT", "GOOGL", "TSLA" populated.
        self.master = SecurityMaster()
        self.resolver = EntityResolutionService(self.master)
        
        # Build registry with fixtures for E2E tests
        self.registry = ProviderRegistry()
        self.registry.register(FixtureMarketProvider())
        self.registry.register(FixtureFinancialProvider())
        
        # Build temp orchestrator
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        
        self.providers = ProviderOrchestrator(self.registry, CacheRepository(self.temp_db.name))
        self.orchestrator = ResearchOrchestrator(resolver=self.resolver, providers=self.providers)
        self.query_service = QueryService(self.orchestrator)

    def tearDown(self):
        import os
        try:
            os.unlink(self.temp_db.name)
        except Exception:
            pass

    def test_user_query_google_korean(self):
        """test_user_query_google_korean: '구글 분석해줘' -> GOOGL"""
        res = self.query_service.query("구글 분석해줘")
        self.assertEqual(res.security.ticker, "GOOGL")
        self.assertEqual(res.security.identity_status, IdentityStatus.RESOLVED)

    def test_user_query_google_english(self):
        """test_user_query_google_english: 'Google 분석해줘' -> GOOGL"""
        res = self.query_service.query("Google 분석해줘")
        self.assertEqual(res.security.ticker, "GOOGL")
        self.assertEqual(res.security.identity_status, IdentityStatus.RESOLVED)

    def test_user_query_google_typo(self):
        """test_user_query_google_typo: 'gogle 분석해줘' -> GOOGL"""
        res = self.query_service.query("gogle 분석해줘")
        self.assertEqual(res.security.ticker, "GOOGL")
        self.assertEqual(res.security.identity_status, IdentityStatus.RESOLVED)

    def test_user_query_apple(self):
        """test_user_query_apple: 'Apple 분석해줘' -> AAPL"""
        res = self.query_service.query("Apple 분석해줘")
        self.assertEqual(res.security.ticker, "AAPL")
        self.assertEqual(res.security.identity_status, IdentityStatus.RESOLVED)

    def test_unknown_security(self):
        """test_unknown_security: unknown -> UNRESOLVED"""
        res = self.query_service.query("unknown_nonexistent_security")
        self.assertEqual(res.status, "UNRESOLVED")
        self.assertIsNone(res.alpha_score)

    def test_ambiguous_security(self):
        """test_ambiguous_security: ambiguous issuer -> AMBIGUOUS"""
        # Create a temp duplicate alias mapping
        with sqlite3.connect(self.master.db_path) as conn:
            aapl_id = conn.execute("SELECT security_id FROM securities WHERE ticker='AAPL'").fetchone()[0]
            msft_id = conn.execute("SELECT security_id FROM securities WHERE ticker='MSFT'").fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO security_aliases (security_id, alias, source, confidence) VALUES (?, 'ambiguous_alias', 'manual', 1.0)", (aapl_id,))
            conn.execute("INSERT OR IGNORE INTO security_aliases (security_id, alias, source, confidence) VALUES (?, 'ambiguous_alias', 'manual', 1.0)", (msft_id,))
            conn.commit()

        try:
            res = self.query_service.query("ambiguous_alias")
            self.assertEqual(res.status, "AMBIGUOUS")
            self.assertIsNone(res.alpha_score)
        finally:
            with sqlite3.connect(self.master.db_path) as conn:
                conn.execute("DELETE FROM security_aliases WHERE alias='ambiguous_alias'")
                conn.commit()

    def test_full_research_pipeline(self):
        """test_full_research_pipeline: resolution -> provider -> normalized -> quant -> score -> output"""
        # Mock FactorEngine run so it doesn't crash on simple prices
        idx = pd.date_range("2025-01-01", "2026-03-20")
        mock_prices = pd.DataFrame(150.0, index=idx, columns=["AAPL"])
        mock_financials = pd.DataFrame([{"ticker": "AAPL", "per": 25.0, "pbr": 3.0, "roe": 0.2, "profitMargin": 0.15}]).set_index("ticker")
        
        with patch('research.orchestrator.market_to_prices', return_value=mock_prices), \
             patch('research.orchestrator.financial_to_frame', return_value=mock_financials):
            res = self.query_service.query("Apple 분석해줘")
            self.assertEqual(res.status, "OK")
            self.assertIsNotNone(res.alpha_score)
            self.assertTrue(-1.0 <= res.alpha_score <= 1.0)
            self.assertTrue(0.0 <= res.confidence <= 1.0)
            self.assertIn("volatility", res.components)
            self.assertIn("news", res.components)

    def test_provider_provenance(self):
        """test_provider_provenance: REAL/CACHED/FALLBACK/UNAVAILABLE status preserved"""
        res = self.query_service.query("Apple 분석해줘")
        self.assertEqual(res.data_quality["market"]["status"], "REAL")
        self.assertEqual(res.data_quality["financial"]["status"], "REAL")
        self.assertEqual(res.data_quality["social"]["status"], "UNAVAILABLE")

    def test_score_range(self):
        """test_score_range: [-1,1]"""
        idx = pd.date_range("2025-01-01", "2026-03-20")
        mock_prices = pd.DataFrame(150.0, index=idx, columns=["AAPL"])
        mock_financials = pd.DataFrame([{"ticker": "AAPL", "per": 25.0, "pbr": 3.0, "roe": 0.2, "profitMargin": 0.15}]).set_index("ticker")
        
        with patch('research.orchestrator.market_to_prices', return_value=mock_prices), \
             patch('research.orchestrator.financial_to_frame', return_value=mock_financials):
            res = self.query_service.query("Apple 분석해줘")
            self.assertTrue(-1.0 <= res.alpha_score <= 1.0)

    def test_confidence_range(self):
        """test_confidence_range: [0,1]"""
        res = self.query_service.query("Apple 분석해줘")
        self.assertTrue(0.0 <= res.confidence <= 1.0)

    def test_no_execution_import(self):
        """test_no_execution_import: Verifies no execution modules imported"""
        root = pathlib.Path(__file__).resolve().parents[1]
        for path in [root / "research" / "orchestrator.py", root / "application" / "query_service.py"]:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [x.name for x in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                self.assertFalse(any(name.startswith("execution") or "portfolio" in name for name in names), path)

    def test_no_lookahead(self):
        """test_no_lookahead: Future dates are strictly rejected"""
        future_dt = datetime.datetime.now(timezone.utc) + timedelta(days=1)
        security = SecurityIdentity("s1", "AAPL", identity_status=IdentityStatus.RESOLVED)
        future_data = NormalizedData(security.security_id, "AAPL", "market", {}, "test",
                                     DataStatus.REAL, 0.9, future_dt, datetime.datetime.now(timezone.utc), None)
        with self.assertRaises(ValueError):
            ProviderOrchestrator._validate_as_of(future_data, ProviderContext("r1", datetime.datetime.now(timezone.utc), 365))

    def test_cross_ticker_isolation(self):
        """test_cross_ticker_isolation: Multi-ticker runs are isolated"""
        # Verifies that separate calls return unique results
        idx = pd.date_range("2025-01-01", "2026-03-20")
        mock_prices = pd.DataFrame(150.0, index=idx, columns=["AAPL"])
        mock_financials_aapl = pd.DataFrame([{"ticker": "AAPL", "per": 25.0, "pbr": 3.0, "roe": 0.2, "profitMargin": 0.15}]).set_index("ticker")
        mock_financials_msft = pd.DataFrame([{"ticker": "MSFT", "per": 35.0, "pbr": 8.0, "roe": 0.3, "profitMargin": 0.20}]).set_index("ticker")

        with patch('research.orchestrator.market_to_prices', return_value=mock_prices):
            with patch('research.orchestrator.financial_to_frame', return_value=mock_financials_aapl):
                res_aapl = self.query_service.query("Apple 분석해줘")
            with patch('research.orchestrator.financial_to_frame', return_value=mock_financials_msft):
                res_msft = self.query_service.query("Microsoft 분석해줘")
                
            self.assertEqual(res_aapl.security.ticker, "AAPL")
            self.assertEqual(res_msft.security.ticker, "MSFT")
            # Verify drivers are distinct
            self.assertNotEqual(res_aapl.security.security_id, res_msft.security.security_id)
