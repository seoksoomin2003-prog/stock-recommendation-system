"""SEC CIK hydration (P6-19: isolated temp DB + fixture cache; no network, no production writes)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from entity.security_master import SecurityMaster

ROOT = Path(__file__).resolve().parents[1]
# Public SEC CIKs (company_tickers.json format) for the five tickers checked below.
FIXTURE = {"0": {"cik_str": 1652044, "ticker": "GOOGL", "title": "Alphabet Inc."},
           "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
           "2": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
           "3": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
           "4": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc."}}


class TestSecSecurityMaster(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "tickers.db"
        shutil.copy2(ROOT / "data" / "tickers.db", self.db)
        self.cache = Path(self.tmp.name) / "sec_cache"
        self.cache.mkdir()
        (self.cache / "company_tickers.json").write_text(json.dumps(FIXTURE))

    def tearDown(self):
        self.tmp.cleanup()

    def test_cached_official_ciks_are_hydrated(self):
        master = SecurityMaster(str(self.db))
        master.migrate_additively()
        master.hydrate_ciks_from_sec_cache(str(self.cache))
        for ticker in ("GOOGL", "AAPL", "MSFT", "NVDA", "TSLA"):
            value = master.candidates(ticker)[0]
            self.assertTrue(value.cik and value.cik.isdigit(), ticker)
            self.assertEqual(int(value.cik), next(v["cik_str"] for v in FIXTURE.values() if v["ticker"] == ticker))


if __name__ == "__main__":
    unittest.main()
