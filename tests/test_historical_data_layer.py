"""TEST FIXTURE / SYNTHETIC: adversarial PIT tests only; never production data."""

from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from contracts.historical_data import CorporateActionEvent, CorporateActionType, FactPeriodType, HistoricalFinancialFact, HistoricalPriceBar
from contracts.normalized_data import DataStatus
from entity.historical_data_repository import HistoricalDataRepository
from providers.historical import ConnectivityStatus, OfficialSecHistoricalFinancialProvider, SecUserAgentConfig, diagnose_connectivity

UTC = timezone.utc
SID_A, SID_B = "sec-a", "sec-b"


def dt(value): return datetime.fromisoformat(value).replace(tzinfo=UTC)


def fact(metric, value, filed, *, period_end="2024-12-31", accepted=None, accession="0001", amended=False, restated=False, sid=SID_A, period_type=None):
    return HistoricalFinancialFact(sid, "fixture", "TEST FIXTURE / SYNTHETIC", accession, "us-gaap", metric, metric,
        None if period_type == FactPeriodType.INSTANT else date(2024, 1, 1), date.fromisoformat(period_end), dt(filed),
        dt(accepted) if accepted else None, value, "USD", "10-K/A" if amended else "10-K", is_amended=amended,
        is_restated=restated, period_type=period_type or (FactPeriodType.INSTANT if metric in {"total_assets", "shareholders_equity"} else FactPeriodType.DURATION), source_id=accession)


class TestHistoricalDataLayer(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.repo = HistoricalDataRepository(str(Path(self.directory.name) / "synthetic_p5_fixture.db"), allow_synthetic=True)

    def tearDown(self):
        self.directory.cleanup()

    def test_future_filing_and_future_sec_filing_are_rejected(self):
        self.repo.add_financial_fact(fact("revenue", 10, "2025-02-15", accession="future"))
        snap = self.repo.financial_snapshot(SID_A, dt("2025-01-01"))
        self.assertEqual(snap.availability_status, DataStatus.UNAVAILABLE)
        self.assertIsNone(snap.metrics["revenue"])

    def test_amendment_and_restatement_only_apply_when_available(self):
        self.repo.add_financial_fact(fact("revenue", 10, "2025-02-15", accession="orig"))
        self.repo.add_financial_fact(fact("revenue", 12, "2025-04-01", accession="amend", amended=True, restated=True))
        self.assertEqual(self.repo.financial_snapshot(SID_A, dt("2025-03-01")).metrics["revenue"], 10)
        self.assertEqual(self.repo.financial_snapshot(SID_A, dt("2025-04-02")).metrics["revenue"], 12)

    def test_same_period_selection_is_deterministic_and_accepted_at_is_enforced(self):
        self.repo.add_financial_fact(fact("net_income", 1, "2025-02-15", accepted="2025-02-16", accession="a"))
        self.repo.add_financial_fact(fact("net_income", 2, "2025-02-15", accepted="2025-02-17", accession="b"))
        self.assertEqual(self.repo.financial_snapshot(SID_A, dt("2025-02-16T12:00:00")).metrics["net_income"], 1)
        self.assertEqual(self.repo.financial_snapshot(SID_A, dt("2025-02-18")).metrics["net_income"], 2)

    def test_unit_period_type_and_missing_values_are_safe(self):
        with self.assertRaisesRegex(ValueError, "metric_period_type_mismatch"):
            self.repo.add_financial_fact(fact("total_assets", 1, "2025-02-15", period_type=FactPeriodType.DURATION))
        snap = self.repo.financial_snapshot(SID_A, dt("2025-03-01"))
        self.assertIsNone(snap.metrics["cash"])
        self.assertEqual(snap.availability_status, DataStatus.UNAVAILABLE)

    def test_delisted_price_ticker_reuse_security_isolation_and_raw_adjusted_separation(self):
        self.repo.add_price_bar(HistoricalPriceBar(SID_A, "fixture", date(2020, 1, 2), 10, 12, 9, 11, 5.5, 100, "TEST FIXTURE / SYNTHETIC", source_id="a"))
        self.repo.add_price_bar(HistoricalPriceBar(SID_B, "fixture", date(2020, 1, 2), 30, 32, 29, 31, 31, 100, "TEST FIXTURE / SYNTHETIC", source_id="b"))
        bars = self.repo.price_bars(SID_A, dt("2020-01-03"))
        self.assertEqual((len(bars), bars[0].close, bars[0].adjusted_close), (1, 11, 5.5))
        self.assertEqual(self.repo.price_bars(SID_A, dt("2020-01-01")), [])

    def test_corporate_action_announcement_timing_and_future_events(self):
        event = CorporateActionEvent(SID_A, "split-1", CorporateActionType.SPLIT, dt("2025-06-15"), dt("2025-06-01"),
            None, None, 2.0, None, None, "TEST FIXTURE / SYNTHETIC", None, dt("2025-06-01"), True)
        self.repo.add_corporate_action(event)
        self.assertEqual(self.repo.corporate_actions(SID_A, dt("2025-05-01")), [])
        self.assertEqual(self.repo.corporate_actions(SID_A, dt("2025-06-10"))[0].information_available_at(), dt("2025-06-01"))

    def test_information_set_hash_is_reproducible(self):
        self.repo.add_financial_fact(fact("revenue", 10, "2025-02-15"))
        self.repo.add_price_bar(HistoricalPriceBar(SID_A, "fixture", date(2025, 2, 16), 10, 10, 10, 10, 10, 1, "TEST FIXTURE / SYNTHETIC", source_id="p"))
        self.assertEqual(self.repo.information_set(SID_A, dt("2025-02-20")).snapshot_hash,
                         self.repo.information_set(SID_A, dt("2025-02-20")).snapshot_hash)

    def test_production_repository_rejects_synthetic_records(self):
        production = HistoricalDataRepository(str(Path(self.directory.name) / "production.db"))
        with self.assertRaisesRegex(ValueError, "synthetic_records_forbidden"):
            production.add_financial_fact(fact("revenue", 10, "2025-02-15"))
        self.assertTrue(production.production_historical_repository_contains_no_synthetic_records())

    def test_duplicate_source_record_is_idempotent_but_conflict_rejected(self):
        original = fact("revenue", 10, "2025-02-15", accession="same")
        self.repo.add_financial_fact(original)
        self.repo.add_financial_fact(original)
        with self.assertRaisesRegex(ValueError, "duplicate_historical_financial_record_conflict"):
            self.repo.add_financial_fact(fact("revenue", 11, "2025-02-15", accession="same"))

    def test_pit_derived_factor_integrity_and_lineage(self):
        self.repo.add_financial_fact(fact("net_income", 20, "2025-02-15", accession="income"))
        self.repo.add_financial_fact(fact("revenue", 100, "2025-02-15", accession="revenue"))
        self.repo.add_financial_fact(fact("shareholders_equity", 200, "2025-02-15", accession="equity", period_type=FactPeriodType.INSTANT))
        snapshot = self.repo.financial_snapshot(SID_A, dt("2025-03-01"))
        self.assertEqual(snapshot.metrics["profit_margin"], 0.2)
        self.assertEqual(snapshot.metrics["roe"], 0.1)
        self.assertEqual(snapshot.provenance["derived_metrics"]["roe"]["accession_numbers"], ["income", "equity"])

    def test_official_sec_provider_is_unavailable_without_configured_user_agent(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"SEC_USER_AGENT": ""}, clear=True):
            probe = OfficialSecHistoricalFinancialProvider(user_agent="").probe("320193")
            self.assertEqual(probe.status, DataStatus.UNAVAILABLE)
            self.assertFalse(probe.sample_record_retrieved)

    def test_official_sec_parser_preserves_pit_provenance(self):
        payload = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [{"start": "2024-01-01", "end": "2024-12-31", "filed": "2025-02-15", "val": 100, "accn": "0001", "form": "10-K", "fy": 2024, "fp": "FY"}]}}}}}
        facts = OfficialSecHistoricalFinancialProvider(user_agent="test@example.com").parse_companyfacts(SID_A, "320193", payload, fetched_at=dt("2025-02-16"))
        self.assertEqual(len(facts), 1)
        self.assertEqual((facts[0].normalized_metric, facts[0].accession_number, facts[0].filed_at), ("revenue", "0001", dt("2025-02-15")))

    def test_sec_configuration_fails_closed_without_exposing_value(self):
        config = SecUserAgentConfig(None)
        self.assertFalse(config.configured)
        with self.assertRaisesRegex(ValueError, "SEC_USER_AGENT_not_configured"):
            config.headers()

    def test_dns_diagnostic_stops_before_provider_acquisition(self):
        import socket
        original = socket.getaddrinfo
        try:
            socket.getaddrinfo = lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror("offline"))
            diagnostic = diagnose_connectivity("sec_edgar", "data.sec.gov", credentials_configured=True)
        finally:
            socket.getaddrinfo = original
        self.assertEqual(diagnostic.status, ConnectivityStatus.DNS_UNAVAILABLE)
        self.assertEqual(diagnostic.sample_request, "NOT_ATTEMPTED")

    def test_production_repository_rejects_missing_provenance(self):
        production = HistoricalDataRepository(str(Path(self.directory.name) / "missing_provenance.db"))
        real = HistoricalFinancialFact(SID_A, "sec", "SEC EDGAR", None, "us-gaap", "Revenues", "revenue",
            date(2024, 1, 1), date(2024, 12, 31), dt("2025-02-15"), None, 1, "USD", "10-K", source_id=None)
        with self.assertRaisesRegex(ValueError, "historical_provenance_incomplete"):
            production.add_financial_fact(real)
