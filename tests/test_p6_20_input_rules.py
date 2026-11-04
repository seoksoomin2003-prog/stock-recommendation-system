"""P6-20 addendum A1-A6: approved data-input rules (regression tests).

Every case listed in the addendum has a test here.  The frozen P6-11B core is not touched; these rules
only decide which provider observations are fed into it.
"""
import os
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from data.loader import (DATA_INPUT_SPEC_VERSION, FUNDAMENTALS_CACHE_SCHEMA, PBR_EQUITY_MAX_AGE_DAYS,
                         DataLoader)
from tests.p6_18_fakes import FakeLoader, make_financials, make_market, pipeline_for

AS_OF = pd.Timestamp("2026-11-04T15:00:00Z")
FRESH_MRQ = int(pd.Timestamp("2026-09-30").timestamp())
VALID_UA = "QuantStockEngine/1.0 someone@realmail.org"


def fy(val, start="2025-01-01", end="2025-12-31", filed="2026-02-20", form="10-K", accn="A-FY25"):
    return {"start": start, "end": end, "val": val, "fy": 2025, "fp": "FY", "form": form,
            "filed": filed, "accn": accn}


def inst(val, end="2026-09-30", filed="2026-10-30", form="10-Q", accn="A-Q3"):
    return {"end": end, "val": val, "fy": 2026, "fp": "Q3", "form": form, "filed": filed, "accn": accn}


def facts(**concepts):
    return {"facts": {"us-gaap": {c: {"units": {"USD": rows}} for c, rows in concepts.items()}}}


def base_facts(**extra):
    c = {"NetIncomeLoss": [fy(100.0)], "Revenues": [fy(1000.0)],
         "StockholdersEquity": [inst(500.0, end="2025-12-31", filed="2026-02-20", form="10-K", accn="A-FY25"),
                                inst(500.0)]}
    c.update(extra)
    return facts(**c)


def info(**kw):
    out = {"priceToBook": 2.0, "marketCap": 1000.0, "currentPrice": 10.0, "sharesOutstanding": 100.0,
           "impliedSharesOutstanding": 100.0, "currency": "USD", "financialCurrency": "USD",
           "profitMargins": 0.08, "mostRecentQuarter": FRESH_MRQ, "trailingPE": 15.0}
    out.update(kw)
    return out


def check(sec_facts, yahoo, accepted=None):
    dl = DataLoader(use_cache=False)
    m = dl._sec_metrics(sec_facts, as_of=AS_OF, accepted=accepted)
    pbr = yahoo.get("priceToBook")
    return dl._pbr_cross_check(float("nan") if pbr is None else float(pbr), yahoo, m["detail"]), m


class TestA1PriceToBook(unittest.TestCase):
    def test_normal_agreement(self):
        c, _ = check(base_facts(), info(priceToBook=2.05))
        self.assertEqual(c["status"], "CONSISTENT")
        self.assertAlmostEqual(c["diagnostic_pbr"], 1000.0 / 500.0)
        self.assertEqual(c["sec_equity_filing"]["accn"], "A-Q3")          # latest eligible balance sheet
        self.assertEqual(c["share_scope"]["status"], "COMPATIBLE")

    def test_more_than_10x_difference_is_unavailable_with_original_value(self):
        c, _ = check(base_facts(), info(priceToBook=0.00107))
        self.assertEqual(c["status"], "INCONSISTENT")
        self.assertAlmostEqual(c["provider_value"], 0.00107)
        c_hi, _ = check(base_facts(), info(priceToBook=25.0))           # >10x on the high side
        self.assertEqual(c_hi["status"], "INCONSISTENT")
        c_edge, _ = check(base_facts(), info(priceToBook=20.0))         # exactly 10x -> not ">10x"
        self.assertEqual(c_edge["status"], "CONSISTENT")

    def test_loader_never_replaces_inconsistent_value(self):
        with patch.object(DataLoader, "_fetch_yf_info", lambda self, t: info(priceToBook=0.00107)), \
                patch.object(DataLoader, "_fetch_sec_facts", lambda self, cik: base_facts()), \
                patch.dict(os.environ, {"SEC_USER_AGENT": VALID_UA}):
            frame = DataLoader(use_cache=False).get_financial_data(["X"], ciks={"X": "1"})
        prov = frame.attrs["field_provenance"]["X"]["pbr"]
        self.assertTrue(np.isnan(frame.loc["X", "pbr"]))                 # not the diagnostic 2.0
        self.assertEqual(prov["status"], "UNAVAILABLE")
        self.assertEqual(prov["reason"], "PBR_INCONSISTENT_WITH_SEC_COMMON_EQUITY")
        self.assertAlmostEqual(prov["rejected_provider_value"]["provider_value"], 0.00107)

    def test_zero_or_negative_equity_not_verifiable(self):
        for eq in (0.0, -50.0):
            c, _ = check(base_facts(StockholdersEquity=[inst(eq)]), info())
            self.assertEqual(c["status"], "NOT_VERIFIABLE")
            self.assertIn("NON_POSITIVE_COMMON_EQUITY", c["reasons"])
            self.assertIsNone(c["diagnostic_pbr"])

    def test_preferred_stock_subtracted_and_can_make_common_equity_non_positive(self):
        c, m = check(base_facts(PreferredStockValue=[inst(100.0)]), info(priceToBook=2.5))
        self.assertAlmostEqual(m["detail"]["pb_equity"]["common_equity"], 400.0)
        self.assertEqual(m["detail"]["pb_equity"]["preferred_treatment"], "SUBTRACTED_SAME_INSTANT")
        self.assertAlmostEqual(c["diagnostic_pbr"], 2.5)
        c2, _ = check(base_facts(PreferredStockValue=[inst(500.0)]), info())
        self.assertIn("NON_POSITIVE_COMMON_EQUITY", c2["reasons"])

    def test_missing_market_cap_not_verifiable_and_value_kept(self):
        c, _ = check(base_facts(), info(marketCap=None, priceToBook=0.00107))
        self.assertEqual(c["status"], "NOT_VERIFIABLE")
        self.assertIn("MARKET_CAP_UNAVAILABLE", c["reasons"])

    def test_stale_sec_balance_sheet_not_verifiable(self):
        old = facts(NetIncomeLoss=[fy(100.0)], Revenues=[fy(1000.0)],
                    StockholdersEquity=[inst(500.0, end="2026-03-31", filed="2026-04-30")])
        c, m = check(old, info())
        self.assertGreater(m["detail"]["pb_equity"]["age_days"], PBR_EQUITY_MAX_AGE_DAYS)
        self.assertEqual(c["status"], "NOT_VERIFIABLE")
        self.assertIn("SEC_BALANCE_SHEET_OLDER_THAN_MAX_AGE", c["reasons"])

    def test_filing_after_timestamp_is_never_used(self):
        later = base_facts(StockholdersEquity=[inst(500.0), inst(5.0, end="2026-10-31", filed="2026-11-05",
                                                                 accn="A-FUT")])
        c, _ = check(later, info())
        self.assertEqual(c["sec_equity_filing"]["accn"], "A-Q3")
        # same-day filing: accepted after the timestamp -> excluded; accepted before -> eligible
        same_day = base_facts(StockholdersEquity=[inst(500.0), inst(5.0, end="2026-10-31", filed="2026-11-04",
                                                                    accn="A-TODAY")])
        c_unknown, _ = check(same_day, info())
        self.assertEqual(c_unknown["sec_equity_filing"]["accn"], "A-Q3")   # acceptance time unknown -> excluded
        c_late, _ = check(same_day, info(), accepted={"A-TODAY": "2026-11-04T16:30:00.000Z"})  # 21:30 UTC
        self.assertEqual(c_late["sec_equity_filing"]["accn"], "A-Q3")
        c_early, _ = check(same_day, info(), accepted={"A-TODAY": "2026-11-04T07:00:00.000Z"})  # 12:00 UTC
        self.assertEqual(c_early["sec_equity_filing"]["accn"], "A-TODAY")
        self.assertEqual(c_early["sec_equity_filing"]["accepted"], "2026-11-04T07:00:00.000Z")

    def test_incompatible_share_class_scope_not_verifiable(self):
        # Market cap of ONE class (price x class shares) against entity-wide equity.
        c, _ = check(base_facts(), info(marketCap=1000.0, sharesOutstanding=100.0, impliedSharesOutstanding=180.0))
        self.assertEqual(c["status"], "NOT_VERIFIABLE")
        self.assertIn("SINGLE_CLASS_MARKET_CAP_VS_ENTITY_EQUITY", c["reasons"])
        c2, _ = check(base_facts(), info(marketCap=1000.0, sharesOutstanding=60.0, impliedSharesOutstanding=60.0))
        self.assertIn("MARKET_CAP_SHARE_COUNT_UNRECONCILED", c2["reasons"])
        c3, _ = check(base_facts(), info(currency="EUR"))
        self.assertIn("CURRENCY_NOT_USD_currency", c3["reasons"])

    def test_multi_class_all_class_market_cap_is_compatible(self):
        # BRK-B / GOOGL / FOX pattern: marketCap = price x all-class (implied) shares.
        c, _ = check(base_facts(), info(marketCap=1800.0, sharesOutstanding=100.0, impliedSharesOutstanding=180.0,
                                        priceToBook=0.002))
        self.assertEqual(c["share_scope"]["status"], "COMPATIBLE")
        self.assertEqual(c["status"], "INCONSISTENT")                    # the BRK-B defect is still caught

    def test_unavailable_yahoo_pbr(self):
        c, _ = check(base_facts(), info(priceToBook=None))
        self.assertEqual(c["status"], "PROVIDER_VALUE_UNAVAILABLE")
        self.assertAlmostEqual(c["diagnostic_pbr"], 2.0)                 # computed for diagnostics only
        with patch.object(DataLoader, "_fetch_yf_info", lambda self, t: info(priceToBook=None)), \
                patch.object(DataLoader, "_fetch_sec_facts", lambda self, cik: base_facts()), \
                patch.dict(os.environ, {"SEC_USER_AGENT": VALID_UA}):
            frame = DataLoader(use_cache=False).get_financial_data(["X"], ciks={"X": "1"})
        self.assertTrue(np.isnan(frame.loc["X", "pbr"]))                 # never substituted
        self.assertEqual(frame.attrs["field_provenance"]["X"]["pbr"]["status"], "UNAVAILABLE")

    def test_sec_not_configured_is_not_verifiable(self):
        with patch.object(DataLoader, "_fetch_yf_info", lambda self, t: info(priceToBook=0.00107)), \
                patch.dict(os.environ, {"SEC_USER_AGENT": ""}):
            frame = DataLoader(use_cache=False).get_financial_data(["X"], ciks={"X": "1"})
        chk = frame.attrs["field_provenance"]["X"]["pbr"]["consistency_check"]
        self.assertEqual(chk["status"], "NOT_VERIFIABLE")
        self.assertAlmostEqual(frame.loc["X", "pbr"], 0.00107)


class TestA2TotalRevenue(unittest.TestCase):
    def metrics(self, **concepts):
        concepts.setdefault("NetIncomeLoss", [fy(100.0)])
        return DataLoader(use_cache=False)._sec_metrics(facts(**concepts), as_of=AS_OF)

    def test_tier1_total_revenue_preferred_over_larger_component(self):
        m = self.metrics(Revenues=[fy(1000.0)], InterestAndDividendIncomeOperating=[fy(1500.0)])
        sel = m["detail"]["revenue_selection"]
        self.assertEqual((sel["status"], sel["tier"]), ("SELECTED", 1))
        self.assertEqual(m["detail"]["revenue"]["concept"], "Revenues")
        self.assertAlmostEqual(m["profitMargin"], 0.1)

    def test_largest_only_among_compatible_total_concepts(self):
        m = self.metrics(Revenues=[fy(900.0)], RevenuesNetOfInterestExpense=[fy(1000.0)],
                         RevenueFromContractWithCustomerExcludingAssessedTax=[fy(5000.0)])
        self.assertEqual(m["detail"]["revenue"]["concept"], "RevenuesNetOfInterestExpense")

    def test_single_stream_concept_accepted_only_without_other_streams(self):
        m = self.metrics(RevenueFromContractWithCustomerExcludingAssessedTax=[fy(800.0)])
        self.assertEqual(m["detail"]["revenue_selection"]["tier"], 2)
        self.assertAlmostEqual(m["profitMargin"], 100.0 / 800.0)
        m2 = self.metrics(RevenueFromContractWithCustomerExcludingAssessedTax=[fy(800.0)],
                          OperatingLeaseLeaseIncome=[fy(30.0)])
        self.assertTrue(np.isnan(m2["profitMargin"]))
        self.assertEqual(m2["detail"]["revenue_selection"]["status"], "UNAVAILABLE")

    def test_components_alone_or_together_never_total(self):
        m = self.metrics(InterestAndDividendIncomeOperating=[fy(900.0)], NoninterestIncome=[fy(300.0)])
        self.assertTrue(np.isnan(m["profitMargin"]))                    # never 900 + 300
        self.assertEqual(m["detail"]["revenue_rejected"]["reason"], "NO_RELIABLE_TOTAL_REVENUE")
        self.assertEqual({r["reason"] for r in m["detail"]["revenue_rejected"]["rejected_facts"]},
                         {"COMPONENT_NOT_TOTAL_REVENUE"})

    def test_quarterly_ytd_and_other_periods_never_combined(self):
        q = fy(250.0, start="2025-10-01", end="2025-12-31")
        ytd = fy(750.0, start="2025-01-01", end="2025-09-30", form="10-Q")
        shifted = fy(1000.0, start="2024-12-01", end="2025-11-30")      # annual but a different period
        m = self.metrics(Revenues=[q, ytd, shifted])
        self.assertEqual(m["detail"]["revenue_selection"]["status"], "UNAVAILABLE")
        self.assertTrue(np.isnan(m["profitMargin"]))

    def test_other_units_and_currencies_ignored(self):
        f = facts(NetIncomeLoss=[fy(100.0)])
        f["facts"]["us-gaap"]["Revenues"] = {"units": {"EUR": [fy(1000.0)]}}
        m = DataLoader(use_cache=False)._sec_metrics(f, as_of=AS_OF)
        self.assertEqual(m["detail"]["revenue_selection"]["status"], "UNAVAILABLE")

    def test_same_filing_preferred_and_future_filings_excluded(self):
        restated = fy(1100.0, filed="2026-05-01", form="10-K/A", accn="A-AMEND")
        future = fy(1200.0, filed="2026-11-10", form="10-K/A", accn="A-FUTURE")
        m = self.metrics(Revenues=[fy(1000.0), restated, future])
        self.assertEqual(m["detail"]["revenue"]["accn"], "A-FY25")       # same filing as net income
        self.assertTrue(m["detail"]["revenue_selection"]["same_filing_as_net_income"])
        m2 = self.metrics(Revenues=[restated, future])                   # only other filings
        self.assertEqual(m2["detail"]["revenue"]["accn"], "A-AMEND")
        self.assertFalse(m2["detail"]["revenue_selection"]["same_filing_as_net_income"])

    def test_provenance_fields_preserved(self):
        m = self.metrics(Revenues=[fy(1000.0)])
        r = m["detail"]["revenue"]
        for k in ("concept", "taxonomy", "unit", "start", "end", "duration_days", "filed", "accepted", "form",
                  "accn", "fy", "fp"):
            self.assertIn(k, r)
        self.assertEqual((r["taxonomy"], r["unit"]), ("us-gaap", "USD"))


class TestA3NetMargin(unittest.TestCase):
    def frame(self, sec_facts, yahoo):
        with patch.object(DataLoader, "_fetch_yf_info", lambda self, t: dict(yahoo)), \
                patch.object(DataLoader, "_fetch_sec_facts", lambda self, cik: sec_facts), \
                patch.dict(os.environ, {"SEC_USER_AGENT": VALID_UA}):
            return DataLoader(use_cache=False).get_financial_data(["X"], ciks={"X": "1"})

    def test_margin_above_100pct_reviewed_and_accepted_when_explained(self):
        m = DataLoader(use_cache=False)._sec_metrics(facts(
            NetIncomeLoss=[fy(1500.0)], Revenues=[fy(1000.0)],
            IncomeLossFromContinuingOperations=[fy(200.0)]), as_of=AS_OF)
        self.assertAlmostEqual(m["profitMargin"], 1.5)                   # not declared impossible
        self.assertEqual(m["detail"]["margin_anomaly_review"]["decision"], "ACCEPTED")

    def test_margin_above_100pct_unexplained_rejected_then_validated_yahoo(self):
        sec = facts(NetIncomeLoss=[fy(1500.0)], Revenues=[fy(1000.0)])
        frame = self.frame(sec, info(profitMargins=0.12, totalRevenue=99999.0))
        prov = frame.attrs["field_provenance"]["X"]["profitMargin"]
        self.assertAlmostEqual(frame.loc["X", "profitMargin"], 0.12)
        self.assertEqual(prov["source"], "yfinance")
        self.assertEqual(prov["sec_rejected"]["reason"], "NET_MARGIN_ABOVE_100PCT_UNEXPLAINED")
        self.assertEqual(prov["anomaly_review"]["decision"], "REJECTED")
        self.assertNotAlmostEqual(frame.loc["X", "profitMargin"], 1500.0 / 99999.0)  # never SEC NI / Yahoo rev

    def test_failed_revenue_rejects_sec_margin(self):
        sec = facts(NetIncomeLoss=[fy(2500.0)], OperatingLeaseLeaseIncome=[fy(80.0)])
        frame = self.frame(sec, info(profitMargins=0.25))
        prov = frame.attrs["field_provenance"]["X"]["profitMargin"]
        self.assertEqual(prov["source"], "yfinance")
        self.assertEqual(prov["yahoo_validation"]["status"], "VALID")
        self.assertEqual(prov["sec_rejected"]["rejected_facts"][0]["concept"], "OperatingLeaseLeaseIncome")

    def test_yahoo_margin_unvalidated_is_unavailable(self):
        sec = facts(NetIncomeLoss=[fy(2500.0)], OperatingLeaseLeaseIncome=[fy(80.0)])
        cases = {"PROVIDER_PERIOD_STALE": info(mostRecentQuarter=int(pd.Timestamp("2025-12-31").timestamp())),
                 "FRESHNESS_UNVERIFIABLE_NO_MOST_RECENT_QUARTER": info(mostRecentQuarter=None),
                 "ABOVE_100PCT_NOT_REVIEWABLE_FROM_PROVIDER": info(profitMargins=1.4),
                 "PROVIDER_VALUE_MISSING": info(profitMargins=None)}
        for reason, yahoo in cases.items():
            frame = self.frame(sec, yahoo)
            prov = frame.attrs["field_provenance"]["X"]["profitMargin"]
            self.assertTrue(np.isnan(frame.loc["X", "profitMargin"]), reason)
            self.assertEqual(prov["status"], "UNAVAILABLE")
            self.assertEqual(prov["yahoo_rejected"]["reason"], reason)
            self.assertEqual(frame.attrs["provider_status"]["X"], "PARTIAL")

    def test_sec_margin_kept_when_valid(self):
        frame = self.frame(base_facts(), info(profitMargins=0.5))
        self.assertAlmostEqual(frame.loc["X", "profitMargin"], 0.1)
        self.assertEqual(frame.attrs["field_provenance"]["X"]["profitMargin"]["source"], "sec_edgar")


T8 = [f"A{i}" for i in range(8)]


class TestA4A5A6Pipeline(unittest.TestCase):
    def test_adv20_provenance_and_missing_is_not_zero(self):
        prices, volumes = make_market(T8)
        volumes.loc[:, "A2"] = np.nan
        volumes.loc[volumes.index[-10]:, "A2"] = 1_000_000.0             # only 10 valid observations
        res = pipeline_for(FakeLoader(prices, volumes, make_financials(T8))).evaluate(T8, {})
        flow = res["candidate_flow"]
        w = flow["A0"]["adv20_window"]
        self.assertEqual(w["observations"], 20)
        self.assertIn("source", w)
        self.assertIn("retrieved_at", w)
        self.assertIsNone(flow["A2"]["adv20"])                           # missing, never 0
        self.assertIn("REQUIRED_NUMERIC_DATA_MISSING", flow["A2"]["reasons"])

    def test_sector_raw_and_normalised_preserved_and_missing_recorded(self):
        prices, volumes = make_market(T8)
        meta = {"A0": {"sector": "Technology", "sector_raw": " Technology ", "sector_status": "REAL",
                       "sector_observed_at": "2026-11-04T12:00:00+00:00"},
                "A1": {"sector": None, "sector_raw": None, "sector_status": "MISSING"}}
        res = pipeline_for(FakeLoader(prices, volumes, make_financials(T8), meta=meta)).evaluate(T8, {})
        flow = res["candidate_flow"]
        self.assertEqual((flow["A0"]["sector"], flow["A0"]["sector_raw"]), ("Technology", " Technology "))
        self.assertEqual(flow["A0"]["sector_observed_at"], "2026-11-04T12:00:00+00:00")
        self.assertEqual(flow["A1"]["sector"], "Unknown")                # never invented
        self.assertEqual(flow["A1"]["sector_status"], "MISSING")
        self.assertIn("SECTOR_UNKNOWN_CAP_NOT_APPLICABLE", flow["A1"]["reasons"])

    def test_loader_sector_normalisation(self):
        with patch.object(DataLoader, "_fetch_yf_info",
                          lambda self, t: {"A": info(sector=" Healthcare "), "B": info(sector=""), "C": info()}[t]):
            frame = DataLoader(use_cache=False).get_financial_data(["A", "B", "C"], ciks={})
        meta = frame.attrs["security_meta"]
        self.assertEqual((meta["A"]["sector"], meta["A"]["sector_raw"]), ("Healthcare", " Healthcare "))
        self.assertEqual(meta["B"]["sector_status"], "MISSING")
        self.assertIsNone(meta["C"]["sector"])
        self.assertIsNotNone(meta["A"]["sector_observed_at"])

    def test_rejected_pbr_quarantines_before_normalisation(self):
        prices, volumes = make_market(T8)
        fin = make_financials(T8)
        fin.loc["A0", "pbr"] = np.nan

        class L(FakeLoader):
            def get_financial_data(self, tickers, ciks=None):
                frame = super().get_financial_data(tickers, ciks)
                frame.attrs["field_provenance"]["A0"]["pbr"] = {
                    "source": None, "status": "UNAVAILABLE", "reason": "PBR_INCONSISTENT_WITH_SEC_COMMON_EQUITY",
                    "rejected_provider_value": {"provider_value": 0.001}}
                return frame
        flow = pipeline_for(L(prices, volumes, fin)).evaluate(T8, {})["candidate_flow"]
        self.assertEqual(flow["A0"]["final_status"], "QUARANTINED")
        self.assertEqual(flow["A0"]["stage_reached"], "PROVENANCE_GATE")
        self.assertIn("PROVIDER_VALUE_REJECTED_PBR", flow["A0"]["reasons"])
        self.assertIsNone(flow["A0"].get("alpha"))                       # excluded before any score exists


class TestVersioning(unittest.TestCase):
    def test_spec_and_cache_schema_bumped(self):
        self.assertEqual(DATA_INPUT_SPEC_VERSION, "P6-20-A")
        self.assertEqual(FUNDAMENTALS_CACHE_SCHEMA, 5)


if __name__ == "__main__":
    unittest.main()
