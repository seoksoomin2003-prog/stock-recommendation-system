"""Daily job / scheduler wrapper (P6-18): uses the canonical service, never touches production reports in tests."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.daily_job import run_daily_job
from tests.p6_18_fakes import FakeLoader, FakeSystem, FakeUniverse, make_financials, make_market

T8 = [f"A{i}" for i in range(8)]


class TestDailyJob(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"QPP_DAILY_REPORT_DIR": os.path.join(self.tmp.name, "daily"), "QPP_CAPITAL": "50000"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _system(self, **kw):
        p, v = make_market(T8)
        return FakeSystem(FakeLoader(p, v, make_financials(T8), **kw))

    def test_daily_job_runs_canonical_scan_and_copies_report(self):
        res = run_daily_job(runs_dir=self.tmp.name, universe_provider=FakeUniverse(T8), system=self._system())
        self.assertEqual(res["display_status"], "REAL RECOMMENDATION")
        reports = list(Path(self.tmp.name, "daily").glob("RECOMMENDATION_*.md"))
        self.assertEqual(len(reports), 1)
        self.assertIn("REAL RECOMMENDATION", reports[0].read_text())

    def test_missing_capital_refuses_to_run(self):
        from utils.runtime_config import CapitalNotConfigured
        with patch.dict(os.environ, {"QPP_CAPITAL": ""}):
            with self.assertRaises(CapitalNotConfigured):
                run_daily_job(runs_dir=self.tmp.name, universe_provider=FakeUniverse(T8), system=self._system())
        self.assertEqual([p for p in Path(self.tmp.name).iterdir() if p.name != "daily"], [])  # no run created

    def test_universe_failure_is_graceful_and_recorded(self):
        res = run_daily_job(runs_dir=self.tmp.name, universe_provider=FakeUniverse([], status="UNAVAILABLE",
                                                                                   freshness="UNAVAILABLE"),
                            system=self._system())
        self.assertEqual(res["display_status"], "LIVE DATA UNAVAILABLE")

    def test_pipeline_crash_leaves_failure_artifact(self):
        res = run_daily_job(runs_dir=self.tmp.name, universe_provider=FakeUniverse(T8),
                            system=self._system(raise_on="market"))
        self.assertEqual(res["execution_status"], "FAILED")
        self.assertTrue((Path(res["artifact_dir"]) / "failure.json").exists())


if __name__ == "__main__":
    unittest.main()
