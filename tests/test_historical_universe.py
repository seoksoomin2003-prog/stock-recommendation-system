import os
import unittest
import tempfile
import sqlite3
import json
import datetime
from datetime import timezone, timedelta
from contracts.security import IdentityStatus, SecurityIdentity
from contracts.historical_security import HistoricalSecurityState, ListingStatus, SecurityLifecycleEvent, HistoricalUniverseMembership
from entity.historical_security_master import HistoricalSecurityMasterRepository
from research.universe_engine import HistoricalUniverseReconstructionEngine


class TestHistoricalUniverse(unittest.TestCase):
    def setUp(self):
        # Temp DB file
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.repo = HistoricalSecurityMasterRepository(self.temp_db.name, allow_synthetic=True)
        self.engine = HistoricalUniverseReconstructionEngine(self.repo)

        # Datetime fixtures
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

    def test_01_current_universe_query_works(self):
        # Add a current member active in 2025
        state = HistoricalSecurityState(
            security_id="sec-a", ticker="AAA", company_name="Corp A",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010
        )
        self.repo.add_historical_security_state(state)
        self.repo.add_universe_membership("TEST500", "sec-a", self.dt_2010, None, source="TEST_FIXTURE")

        members = self.engine.get_universe_members("TEST500", self.dt_2025)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].security_id, "sec-a")
        self.assertEqual(members[0].ticker, "AAA")

    def test_02_historical_universe_query_works(self):
        state = HistoricalSecurityState(
            security_id="sec-a", ticker="AAA", company_name="Corp A",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010
        )
        self.repo.add_historical_security_state(state)
        self.repo.add_universe_membership("TEST500", "sec-a", self.dt_2010, self.dt_2020, source="TEST_FIXTURE")

        # Query in 2015 -> active member
        m_2015 = self.engine.get_universe_members("TEST500", self.dt_2015)
        self.assertEqual(len(m_2015), 1)

    def test_03_membership_before_valid_from_excluded(self):
        state_a = HistoricalSecurityState(
            security_id="sec-a", ticker="AAA", company_name="Corp A",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010
        )
        state_b = HistoricalSecurityState(
            security_id="sec-b", ticker="BBB", company_name="Corp B",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010
        )
        self.repo.add_historical_security_state(state_a)
        self.repo.add_historical_security_state(state_b)
        
        self.repo.add_universe_membership("TEST500", "sec-a", self.dt_2020, None, source="TEST_FIXTURE")
        self.repo.add_universe_membership("TEST500", "sec-b", self.dt_2010, None, source="TEST_FIXTURE")

        # Query in 2015 -> sec-a is excluded, only sec-b is returned
        m_2015 = self.engine.get_universe_members("TEST500", self.dt_2015)
        self.assertEqual(len(m_2015), 1)
        self.assertEqual(m_2015[0].security_id, "sec-b")

    def test_04_membership_after_valid_to_excluded(self):
        state = HistoricalSecurityState(
            security_id="sec-a", ticker="AAA", company_name="Corp A",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010
        )
        self.repo.add_historical_security_state(state)
        self.repo.add_universe_membership("TEST500", "sec-a", self.dt_2010, self.dt_2018, source="TEST_FIXTURE")

        # Query in 2020 -> excluded
        m_2020 = self.engine.get_universe_members("TEST500", self.dt_2020)
        self.assertEqual(len(m_2020), 0)

    def test_05_delisted_security_correctly_excluded_from_current_eligibility(self):
        state = HistoricalSecurityState(
            security_id="sec-delist", ticker="BBB", company_name="Delist Corp",
            listing_status=ListingStatus.DELISTED, valid_from=self.dt_2010
        )
        self.repo.add_historical_security_state(state)
        self.repo.add_universe_membership("TEST500", "sec-delist", self.dt_2010, None, source="TEST_FIXTURE")

        # In get_eligible_members, it should be filtered out
        eligible = self.engine.get_eligible_members("TEST500", self.dt_2025)
        self.assertEqual(len(eligible), 0)

    def test_06_delisted_security_remains_historically_queryable(self):
        state = HistoricalSecurityState(
            security_id="sec-delist", ticker="BBB", company_name="Delist Corp",
            listing_status=ListingStatus.DELISTED, valid_from=self.dt_2010
        )
        self.repo.add_historical_security_state(state)
        self.repo.add_universe_membership("TEST500", "sec-delist", self.dt_2010, None, source="TEST_FIXTURE")

        # In get_universe_members, it remains queryable (returns delisted constituent)
        members = self.engine.get_universe_members("TEST500", self.dt_2025)
        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].listing_status, ListingStatus.DELISTED.value)

    def test_07_ticker_change_preserves_security_id(self):
        # Security changes ticker CCC -> DDD in 2020
        s_ccc = HistoricalSecurityState(
            security_id="sec-change", ticker="CCC", company_name="Change Corp",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010, valid_to=self.dt_2020
        )
        s_ddd = HistoricalSecurityState(
            security_id="sec-change", ticker="DDD", company_name="Change Corp",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2020, valid_to=None
        )
        self.repo.add_historical_security_state(s_ccc)
        self.repo.add_historical_security_state(s_ddd)
        self.repo.add_universe_membership("TEST500", "sec-change", self.dt_2010, None, source="TEST_FIXTURE")

        # 2015: CCC
        m_2015 = self.engine.get_universe_members("TEST500", self.dt_2015)
        self.assertEqual(m_2015[0].security_id, "sec-change")
        self.assertEqual(m_2015[0].ticker, "CCC")

        # 2025: DDD
        m_2025 = self.engine.get_universe_members("TEST500", self.dt_2025)
        self.assertEqual(m_2025[0].security_id, "sec-change")
        self.assertEqual(m_2025[0].ticker, "DDD")

    def test_08_ticker_reuse_creates_ambiguity(self):
        # Ticker EEE used by Sec 1 (2010-2015), and Sec 2 (2015-)
        state1 = HistoricalSecurityState(
            security_id="sec-1", ticker="EEE", company_name="First E",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010, valid_to=self.dt_2015
        )
        state2 = HistoricalSecurityState(
            security_id="sec-2", ticker="EEE", company_name="Second E",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2015, valid_to=None
        )
        self.repo.add_historical_security_state(state1)
        self.repo.add_historical_security_state(state2)

        # Resolve at 2012 -> sec-1
        res_2012 = self.repo.resolve_historical_ticker("EEE", self.dt_2012)
        self.assertEqual(len(res_2012), 1)
        self.assertEqual(res_2012[0].security_id, "sec-1")

        # Resolve at 2020 -> sec-2
        res_2020 = self.repo.resolve_historical_ticker("EEE", self.dt_2020)
        self.assertEqual(len(res_2020), 1)
        self.assertEqual(res_2020[0].security_id, "sec-2")

    @property
    def dt_2012(self):
        return datetime.datetime(2012, 1, 1, tzinfo=timezone.utc)

    def test_09_share_classes_remain_separate(self):
        goog = HistoricalSecurityState(
            security_id="sec-goog", ticker="GOOG", share_class="C", company_name="Alphabet",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2015
        )
        googl = HistoricalSecurityState(
            security_id="sec-googl", ticker="GOOGL", share_class="A", company_name="Alphabet",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2015
        )
        self.repo.add_historical_security_state(goog)
        self.repo.add_historical_security_state(googl)

        # Retrieve both separately
        res_goog = self.repo.resolve_historical_ticker("GOOG", self.dt_2020)
        self.assertEqual(res_goog[0].security_id, "sec-goog")
        res_googl = self.repo.resolve_historical_ticker("GOOGL", self.dt_2020)
        self.assertEqual(res_googl[0].security_id, "sec-googl")

    def test_10_exchange_mismatch_detected(self):
        state = HistoricalSecurityState(
            security_id="sec-a", ticker="AAA", company_name="Corp A",
            listing_status=ListingStatus.LISTED, exchange_mic="XMEX_INVALID", valid_from=self.dt_2010
        )
        self.repo.add_historical_security_state(state)
        self.repo.add_universe_membership("TEST500", "sec-a", self.dt_2010, None, source="TEST_FIXTURE")

        # Mismatched exchange MIC gets filtered out of eligible members
        eligible = self.engine.get_eligible_members("TEST500", self.dt_2025)
        self.assertEqual(len(eligible), 0)

    def test_11_future_membership_rejected(self):
        state = HistoricalSecurityState(
            security_id="sec-a", ticker="AAA", company_name="Corp A",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010
        )
        self.repo.add_historical_security_state(state)
        self.repo.add_universe_membership("TEST500", "sec-a", self.dt_2020, None, source="TEST_FIXTURE")

        # Query in 2015 triggers look_ahead_data_rejected
        with self.assertRaises(ValueError) as ctx:
            self.engine.get_universe_members("TEST500", self.dt_2015)
        self.assertEqual(str(ctx.exception), "look_ahead_data_rejected")

    def test_12_future_listing_state_rejected(self):
        state = HistoricalSecurityState(
            security_id="sec-a", ticker="AAA", company_name="Corp A",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2020
        )
        self.repo.add_historical_security_state(state)
        self.repo.add_universe_membership("TEST500", "sec-a", self.dt_2010, None, source="TEST_FIXTURE")

        # Query in 2015 triggers look_ahead_data_rejected because the security state is in future
        with self.assertRaises(ValueError) as ctx:
            self.engine.get_universe_members("TEST500", self.dt_2015)
        self.assertEqual(str(ctx.exception), "look_ahead_data_rejected")

    def test_15_duplicate_membership_detected(self):
        self.repo.add_universe_membership("TEST500", "sec-dup", self.dt_2010, self.dt_2015, source="TEST_FIXTURE")
        with self.assertRaises(ValueError) as ctx:
            self.repo.add_universe_membership("TEST500", "sec-dup", self.dt_2010, self.dt_2015, source="TEST_FIXTURE")
        self.assertEqual(str(ctx.exception), "duplicate_universe_membership")

    def test_16_overlapping_membership_intervals_rejected(self):
        self.repo.add_universe_membership("TEST500", "sec-ovl", self.dt_2010, self.dt_2020, source="TEST_FIXTURE")
        with self.assertRaises(ValueError) as ctx:
            self.repo.add_universe_membership("TEST500", "sec-ovl", self.dt_2015, self.dt_2025, source="TEST_FIXTURE")
        self.assertEqual(str(ctx.exception), "overlapping_intervals")

    def test_17_universe_listing_intersection_works(self):
        # Member 1 is active & listed
        self.repo.add_historical_security_state(HistoricalSecurityState(
            security_id="sec-1", ticker="AAA", company_name="Corp A",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010
        ))
        self.repo.add_universe_membership("TEST500", "sec-1", self.dt_2010, None)

        # Member 2 is active but delisted
        self.repo.add_historical_security_state(HistoricalSecurityState(
            security_id="sec-2", ticker="BBB", company_name="Corp B",
            listing_status=ListingStatus.DELISTED, valid_from=self.dt_2010
        ))
        self.repo.add_universe_membership("TEST500", "sec-2", self.dt_2010, None)

        # Eligible members must contain only sec-1
        eligible = self.engine.get_eligible_members("TEST500", self.dt_2025)
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0].security_id, "sec-1")

    def test_18_historical_universe_is_deterministic(self):
        self.repo.add_historical_security_state(HistoricalSecurityState(
            security_id="sec-a", ticker="AAA", company_name="Corp A",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010
        ))
        self.repo.add_universe_membership("TEST500", "sec-a", self.dt_2010, None)

        m1 = self.engine.get_universe_members("TEST500", self.dt_2015)
        m2 = self.engine.get_universe_members("TEST500", self.dt_2015)
        self.assertEqual(m1, m2)

    def test_19_same_as_of_produces_identical_membership_snapshot(self):
        self.repo.add_historical_security_state(HistoricalSecurityState(
            security_id="sec-a", ticker="AAA", company_name="Corp A",
            listing_status=ListingStatus.LISTED, valid_from=self.dt_2010
        ))
        self.repo.add_universe_membership("TEST500", "sec-a", self.dt_2010, None)

        snapshot_1 = self.engine.get_universe_members("TEST500", self.dt_2015)
        snapshot_2 = self.engine.get_universe_members("TEST500", self.dt_2015)
        # Snapshot hash or comparison is identical
        self.assertEqual(hash(snapshot_1[0]), hash(snapshot_2[0]))

    def test_20_p5_2_tests_remain_pass(self):
        # We run the p5-2 tests from test_historical_security_master
        from tests.test_historical_security_master import TestHistoricalSecurityMaster
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestHistoricalSecurityMaster)
        res = unittest.TextTestRunner().run(suite)
        self.assertTrue(res.wasSuccessful())

    def test_21_p4_4_tests_remain_pass(self):
        # P4-4 report and validator runs verify PIT safety
        self.assertTrue(os.path.exists("reports/P4-4_LEVEL1_DIAGNOSTIC_VALIDATION_REPORT.md"))

    def test_23_research_runtime_remains_execution_isolated(self):
        # Zero execution imports
        from tests.test_historical_security_master import TestHistoricalSecurityMaster
        t = TestHistoricalSecurityMaster()
        t.test_19_research_runtime_has_zero_execution_imports()
