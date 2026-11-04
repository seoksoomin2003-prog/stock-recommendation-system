import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from contracts.security import IdentityStatus
from entity.resolver_service import EntityResolutionService
from entity.security_master import SecurityMaster


class TestSecurityMaster(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tempdir.name) / "tickers.db")
        with sqlite3.connect(self.path) as conn:
            conn.executescript("""
                CREATE TABLE tickers (id INTEGER PRIMARY KEY, ticker TEXT UNIQUE, company_name TEXT,
                    exchange TEXT, country TEXT, sector TEXT);
                CREATE TABLE aliases (id INTEGER PRIMARY KEY, ticker_id INTEGER, alias TEXT, source TEXT, confidence REAL);
            """)
            conn.execute("INSERT INTO tickers VALUES (1, 'GOOGL', 'Alphabet Inc.', 'NASDAQ', 'US', 'Technology')")
            conn.execute("INSERT INTO aliases VALUES (1, 1, 'google', 'manual', 1.0)")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_additive_migration_and_alias_resolution(self):
        master = SecurityMaster(self.path)
        master.migrate_additively()
        self.assertTrue(Path(self.path + ".pre_security_master.bak").exists())
        resolved = EntityResolutionService(master).resolve("Google")
        self.assertEqual(resolved.identity_status, IdentityStatus.RESOLVED)
        self.assertEqual(resolved.ticker, "GOOGL")

    def test_unknown_is_not_forced(self):
        master = SecurityMaster(self.path)
        master.migrate_additively()
        result = EntityResolutionService(master).resolve("not-a-security")
        self.assertEqual(result.identity_status, IdentityStatus.UNRESOLVED)

