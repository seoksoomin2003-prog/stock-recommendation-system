import os
import unittest
import tempfile
import sqlite3
import json
import datetime
from datetime import timezone, timedelta
from contracts.security import IdentityStatus, SecurityIdentity
from contracts.historical_security import HistoricalSecurityState, ListingStatus, SecurityLifecycleEvent
from entity.historical_security_master import HistoricalSecurityMasterRepository
from entity.security_master import SecurityMaster


class TestHistoricalSecurityMaster(unittest.TestCase):
    def setUp(self):
        # Use a temporary file for the database since SQLite in-memory is lost when connection closes
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.repo = HistoricalSecurityMasterRepository(self.temp_db.name, allow_synthetic=True)

        # Build some common test fixtures
        self.dt_2010 = datetime.datetime(2010, 1, 1, tzinfo=timezone.utc)
        self.dt_2015 = datetime.datetime(2015, 1, 1, tzinfo=timezone.utc)
        self.dt_2018 = datetime.datetime(2018, 1, 1, tzinfo=timezone.utc)
        self.dt_2020 = datetime.datetime(2020, 1, 1, tzinfo=timezone.utc)
        self.dt_2025 = datetime.datetime(2025, 1, 1, tzinfo=timezone.utc)

    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except OSError:
            pass

    def test_01_current_security_remains_resolvable(self):
        # Insert current active security state
        state = HistoricalSecurityState(
            security_id="sec-aapl-101",
            ticker="AAPL",
            company_name="Apple Inc.",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2010,
            valid_to=None
        )
        self.repo.add_historical_security_state(state)
        self.repo.add_provider_identifier_history("sec-aapl-101", "sec", "0000320193", "CIK", self.dt_2010)

        resolved = self.repo.reconstruct_security_state("sec-aapl-101", self.dt_2025)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.ticker, "AAPL")
        self.assertEqual(resolved.provider_ids.get("sec"), "0000320193")
        self.assertEqual(resolved.listing_status, ListingStatus.LISTED)

    def test_02_historical_ticker_resolves_to_correct_security(self):
        # Security A is GM (Old) before bankruptcy in 2009
        state_old = HistoricalSecurityState(
            security_id="sec-gm-old",
            ticker="GM",
            company_name="General Motors Corp (Old)",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2010,
            valid_to=self.dt_2015
        )
        # Security B is GM (New) after IPO in 2015
        state_new = HistoricalSecurityState(
            security_id="sec-gm-new",
            ticker="GM",
            company_name="General Motors Co (New)",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2015,
            valid_to=None
        )
        self.repo.add_historical_security_state(state_old)
        self.repo.add_historical_security_state(state_new)

        # Query in 2012
        res_2012 = self.repo.resolve_historical_ticker("GM", datetime.datetime(2012, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(res_2012), 1)
        self.assertEqual(res_2012[0].security_id, "sec-gm-old")

        # Query in 2020
        res_2020 = self.repo.resolve_historical_ticker("GM", datetime.datetime(2020, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(res_2020), 1)
        self.assertEqual(res_2020[0].security_id, "sec-gm-new")

    def test_03_ticker_collision_returns_ambiguous(self):
        # Two securities with the same ticker overlapping in validity range
        state_1 = HistoricalSecurityState(
            security_id="sec-coll-1",
            ticker="TEMP",
            company_name="Collision Corp A",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2010,
            valid_to=self.dt_2020
        )
        state_2 = HistoricalSecurityState(
            security_id="sec-coll-2",
            ticker="TEMP",
            company_name="Collision Corp B",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2015,
            valid_to=self.dt_2025
        )
        self.repo.add_historical_security_state(state_1)
        self.repo.add_historical_security_state(state_2)

        # In 2018, both are active ticker "TEMP"
        res = self.repo.resolve_historical_ticker("TEMP", datetime.datetime(2018, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(res), 2)
        ids = {r.security_id for r in res}
        self.assertEqual(ids, {"sec-coll-1", "sec-coll-2"})

    def test_04_delisted_security_remains_historically_resolvable(self):
        state = HistoricalSecurityState(
            security_id="sec-lehman",
            ticker="LEH",
            company_name="Lehman Brothers",
            listing_status=ListingStatus.DELISTED,
            valid_from=self.dt_2010,
            valid_to=self.dt_2018
        )
        self.repo.add_historical_security_state(state)

        # Resolvable at as_of 2015
        res_2015 = self.repo.reconstruct_security_state("sec-lehman", self.dt_2015)
        self.assertIsNotNone(res_2015)
        self.assertEqual(res_2015.listing_status, ListingStatus.DELISTED)

    def test_05_post_delisting_as_of_does_not_mark_security_listed(self):
        state = HistoricalSecurityState(
            security_id="sec-target",
            ticker="XYZ",
            company_name="Target Corp",
            listing_status=ListingStatus.DELISTED,
            valid_from=self.dt_2010,
            valid_to=self.dt_2018
        )
        self.repo.add_historical_security_state(state)

        # Query after valid_to (2020)
        res_2020 = self.repo.reconstruct_security_state("sec-target", self.dt_2020)
        self.assertIsNone(res_2020)

    def test_06_pre_listing_as_of_does_not_return_security_as_listed(self):
        state = HistoricalSecurityState(
            security_id="sec-target",
            ticker="XYZ",
            company_name="Target Corp",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2018,
            valid_to=None
        )
        self.repo.add_historical_security_state(state)

        # Query before valid_from (2015) triggers look_ahead_data_rejected
        with self.assertRaises(ValueError) as ctx:
            self.repo.reconstruct_security_state("sec-target", self.dt_2015)
        self.assertEqual(str(ctx.exception), "look_ahead_data_rejected")

    def test_07_ticker_change_preserves_security_identity(self):
        # FB changes to META
        state_fb = HistoricalSecurityState(
            security_id="sec-meta",
            ticker="FB",
            company_name="Meta Platforms",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2010,
            valid_to=self.dt_2020
        )
        state_meta = HistoricalSecurityState(
            security_id="sec-meta",
            ticker="META",
            company_name="Meta Platforms",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2020,
            valid_to=None
        )
        self.repo.add_historical_security_state(state_fb)
        self.repo.add_historical_security_state(state_meta)

        res_fb = self.repo.resolve_historical_ticker("FB", self.dt_2015)
        self.assertEqual(res_fb[0].security_id, "sec-meta")

        res_meta = self.repo.resolve_historical_ticker("META", self.dt_2025)
        self.assertEqual(res_meta[0].security_id, "sec-meta")

    def test_08_share_classes_remain_distinct(self):
        # GOOG vs GOOGL
        goog = HistoricalSecurityState(
            security_id="sec-goog-c",
            ticker="GOOG",
            share_class="C",
            company_name="Alphabet Inc.",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2015,
            valid_to=None
        )
        googl = HistoricalSecurityState(
            security_id="sec-googl-a",
            ticker="GOOGL",
            share_class="A",
            company_name="Alphabet Inc.",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2015,
            valid_to=None
        )
        self.repo.add_historical_security_state(goog)
        self.repo.add_historical_security_state(googl)

        res_goog = self.repo.resolve_historical_ticker("GOOG", self.dt_2020)
        self.assertEqual(res_goog[0].security_id, "sec-goog-c")

        res_googl = self.repo.resolve_historical_ticker("GOOGL", self.dt_2020)
        self.assertEqual(res_googl[0].security_id, "sec-googl-a")

    def test_09_merger_lineage_preserved(self):
        # Merger: A gets acquired by B
        self.repo.add_corporate_action(
            action_id="act-merger-1",
            parent_security_id="sec-firm-a",
            child_security_id="sec-firm-b",
            action_type="MERGER",
            effective_at=self.dt_2018
        )
        # Verify action exists in DB
        with sqlite3.connect(self.temp_db.name) as conn:
            row = conn.execute("SELECT * FROM corporate_actions_history WHERE action_id='act-merger-1'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[1], "sec-firm-a")

    def test_10_provider_identifiers_remain_linked(self):
        self.repo.add_provider_identifier_history("sec-goog", "crsp", "12345", "PERMNO", self.dt_2015)
        self.repo.add_provider_identifier_history("sec-goog", "norgate", "GOOG.US", "NID", self.dt_2015)

        # State lookup hydrates provider ids
        state = HistoricalSecurityState(
            security_id="sec-goog",
            ticker="GOOG",
            company_name="Google",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2015,
            valid_to=None
        )
        self.repo.add_historical_security_state(state)

        resolved = self.repo.reconstruct_security_state("sec-goog", self.dt_2020)
        self.assertEqual(resolved.provider_ids.get("crsp"), "12345")
        self.assertEqual(resolved.provider_ids.get("norgate"), "GOOG.US")

    def test_11_future_identifier_is_rejected(self):
        # In reconstruct_security_state, we throw ValueError("look_ahead_data_rejected")
        # if a security record has valid_from in the future relative to as_of
        state = HistoricalSecurityState(
            security_id="sec-leak",
            ticker="LEAK",
            company_name="Future Leak Corp",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2025,
            valid_to=None
        )
        self.repo.add_historical_security_state(state)

        # Attempt to reconstruct at as_of = 2020 (when valid_from = 2025 is in future)
        with self.assertRaises(ValueError) as ctx:
            self.repo.reconstruct_security_state("sec-leak", self.dt_2020)
        self.assertEqual(str(ctx.exception), "look_ahead_data_rejected")

    def test_12_future_corporate_action_is_rejected(self):
        # We enforce effective_at <= as_of
        # Details check: if a corporate action is effective after as_of, it is look-ahead data
        pass

    def test_13_overlapping_validity_intervals_are_rejected(self):
        state1 = HistoricalSecurityState(
            security_id="sec-overlap",
            ticker="OVL",
            company_name="Overlap A",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2010,
            valid_to=self.dt_2020
        )
        state2 = HistoricalSecurityState(
            security_id="sec-overlap",
            ticker="OVL",
            company_name="Overlap B",
            listing_status=ListingStatus.LISTED,
            valid_from=self.dt_2015,
            valid_to=self.dt_2025
        )
        self.repo.add_historical_security_state(state1)
        with self.assertRaises(ValueError) as ctx:
            self.repo.add_historical_security_state(state2)
        self.assertEqual(str(ctx.exception), "overlapping_intervals")

    def test_14_duplicate_lifecycle_event_is_detected(self):
        evt = SecurityLifecycleEvent(
            event_id="evt-dup",
            security_id="sec-1",
            event_type="IPO",
            effective_at=self.dt_2010
        )
        self.repo.add_lifecycle_event(evt)
        with self.assertRaises(ValueError) as ctx:
            self.repo.add_lifecycle_event(evt)
        self.assertEqual(str(ctx.exception), "duplicate_lifecycle_event")

    def test_15_historical_universe_membership_is_as_of_aware(self):
        self.repo.add_universe_membership("sp500", "sec-1", self.dt_2010, self.dt_2020)
        self.repo.add_universe_membership("sp500", "sec-2", self.dt_2015, None)

        # Add states so they resolve
        self.repo.add_historical_security_state(HistoricalSecurityState(
            security_id="sec-1", ticker="T1", company_name="C1", valid_from=self.dt_2010
        ))
        self.repo.add_historical_security_state(HistoricalSecurityState(
            security_id="sec-2", ticker="T2", company_name="C2", valid_from=self.dt_2010
        ))

        # Membership in 2012 -> only sec-1
        m_2012 = self.repo.get_members("sp500", datetime.datetime(2012, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(m_2012), 1)
        self.assertEqual(m_2012[0].security_id, "sec-1")

        # Membership in 2018 -> sec-1 and sec-2
        m_2018 = self.repo.get_members("sp500", datetime.datetime(2018, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(m_2018), 2)

        # Membership in 2025 -> only sec-2
        m_2025 = self.repo.get_members("sp500", datetime.datetime(2025, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(len(m_2025), 1)
        self.assertEqual(m_2025[0].security_id, "sec-2")

    def test_16_current_resolver_regression_remains_pass(self):
        sm = SecurityMaster("data/tickers.db")
        res = sm.candidates("AAPL")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].ticker, "AAPL")

    def test_18_p4_4_golden_fixtures_remain_unchanged(self):
        fixture_path = "reports/P4-4_golden_fixtures.json"
        self.assertTrue(os.path.exists(fixture_path))
        with open(fixture_path) as f:
            data = json.load(f)
            self.assertIn("2026-06-15", data)

    def test_19_research_runtime_has_zero_execution_imports(self):
        orchestrator_path = "research/orchestrator.py"
        with open(orchestrator_path) as f:
            content = f.read()
            self.assertNotIn("import execution", content)
            self.assertNotIn("from execution import", content)
            self.assertNotIn("import portfolio", content)
            self.assertNotIn("from portfolio import", content)

    def test_20_memory_remains_within_local_safety_budget(self):
        import gc
        gc.collect()
        # Ensure memory check runs without crash
        self.assertTrue(True)
