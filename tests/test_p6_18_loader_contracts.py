"""P6-18 DataLoader contracts: SEC period alignment, missing vs zero, single download, cache, provenance."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data.loader import DataLoader, _finite_or_nan

YEAR = datetime.now(timezone.utc).year


def facts_fixture():
    """A 10-K files three fiscal years on the same date plus quarterly 10-Q values."""
    fy = lambda y, v, form="10-K", filed=None: {"start": f"{y}-01-01", "end": f"{y}-12-31", "val": v, "fy": YEAR - 1,
                                                 "fp": "FY", "form": form, "filed": filed or f"{YEAR}-02-15"}
    q = lambda v: {"start": f"{YEAR}-04-01", "end": f"{YEAR}-06-30", "val": v, "fp": "Q2", "form": "10-Q",
                   "filed": f"{YEAR}-08-01"}
    return {"facts": {"us-gaap": {
        "NetIncomeLoss": {"units": {"USD": [fy(YEAR - 3, 10.0), fy(YEAR - 2, 20.0), fy(YEAR - 1, 30.0), q(9.0)]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [fy(YEAR - 2, 180.0), fy(YEAR - 1, 200.0), q(55.0)]}},
        "StockholdersEquity": {"units": {"USD": [
            {"end": f"{YEAR - 2}-12-31", "val": 100.0, "form": "10-K", "filed": f"{YEAR}-02-15"},
            {"end": f"{YEAR - 1}-12-31", "val": 150.0, "form": "10-K", "filed": f"{YEAR}-02-15"},
            {"end": f"{YEAR}-06-30", "val": 170.0, "form": "10-Q", "filed": f"{YEAR}-08-01"}]}},
    }}}



# P6-20-A3: a Yahoo profitMargins fallback is used only when its latest quarter is fresh.
FRESH_MRQ = int(pd.Timestamp.now(tz="UTC").normalize().timestamp()) - 30 * 86400

class TestSecExtraction(unittest.TestCase):
    def test_annual_period_alignment(self):
        m = DataLoader(use_cache=False)._sec_metrics(facts_fixture())
        self.assertEqual(m["detail"]["fiscal_period_end"], f"{YEAR - 1}-12-31")
        self.assertAlmostEqual(m["roe"], 30.0 / 150.0)          # FY NI / equity at the same FY end
        self.assertAlmostEqual(m["profitMargin"], 30.0 / 200.0)  # same-period ASC 606 revenue
        self.assertEqual(m["detail"]["revenue"]["concept"], "RevenueFromContractWithCustomerExcludingAssessedTax")

    def test_misaligned_revenue_is_not_combined(self):
        f = facts_fixture()
        f["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"] = [
            {"start": f"{YEAR - 3}-01-01", "end": f"{YEAR - 3}-12-31", "val": 1.0, "fp": "FY", "form": "10-K", "filed": f"{YEAR - 2}-02-01"}]
        m = DataLoader(use_cache=False)._sec_metrics(f)
        self.assertTrue(np.isnan(m["profitMargin"]))
        self.assertAlmostEqual(m["roe"], 0.2)

    def test_stale_annual_period_not_used(self):
        f = {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
            {"start": "2019-01-01", "end": "2019-12-31", "val": 5.0, "fp": "FY", "form": "10-K", "filed": "2020-02-01"}]}}}}}
        m = DataLoader(use_cache=False)._sec_metrics(f)
        self.assertEqual(m["detail"]["status"], "STALE")
        self.assertTrue(np.isnan(m["roe"]))

    def test_no_facts_is_unavailable_not_zero(self):
        m = DataLoader(use_cache=False)._sec_metrics({})
        self.assertTrue(np.isnan(m["roe"]) and np.isnan(m["profitMargin"]))


class TestMissingVersusZero(unittest.TestCase):
    def test_finite_or_nan(self):
        self.assertEqual(_finite_or_nan(0), 0.0)
        self.assertEqual(_finite_or_nan("0.5"), 0.5)
        for bad in (None, "Infinity", float("inf"), float("nan"), "abc", True):
            self.assertTrue(np.isnan(_finite_or_nan(bad)), bad)

    def test_financial_frame_status_and_provenance(self):
        loader = DataLoader(use_cache=False)
        infos = {"AAA": {"trailingPE": 20.0, "priceToBook": 3.0, "returnOnEquity": 0.0, "profitMargins": 0.1,
                         "sector": "Technology", "quoteType": "EQUITY", "longName": "AAA Inc",
                         "mostRecentQuarter": FRESH_MRQ},
                 "BBB": {"trailingPE": None, "priceToBook": 2.0, "returnOnEquity": 0.2, "profitMargins": 0.05,
                         "sector": "Energy", "quoteType": "EQUITY", "mostRecentQuarter": FRESH_MRQ},
                 "CCC": {}}
        with patch.object(DataLoader, "_fetch_yf_info", lambda self, t: infos[t]):
            frame = loader.get_financial_data(["AAA", "BBB", "CCC"], ciks={})
        st = frame.attrs["provider_status"]
        self.assertEqual(st, {"AAA": "REAL", "BBB": "PARTIAL", "CCC": "UNAVAILABLE"})
        self.assertEqual(frame.loc["AAA", "roe"], 0.0)  # genuine zero preserved
        prov = frame.attrs["field_provenance"]
        self.assertEqual(prov["AAA"]["roe"]["source"], "yfinance")
        self.assertIsNone(prov["BBB"]["per"]["source"])
        self.assertEqual(frame.attrs["security_meta"]["AAA"]["sector"], "Technology")
        self.assertFalse(frame.attrs["security_meta"]["CCC"]["yf_info_ok"])

    def test_sec_preferred_over_yfinance_with_field_provenance(self):
        loader = DataLoader(use_cache=False)
        info = {"trailingPE": 20.0, "priceToBook": 3.0, "returnOnEquity": 0.9, "profitMargins": 0.9}
        with patch.object(DataLoader, "_fetch_yf_info", lambda self, t: info), \
             patch.object(DataLoader, "_fetch_sec_facts", lambda self, cik: facts_fixture()):
            frame = loader.get_financial_data(["AAA"], ciks={"AAA": "1"})
        self.assertAlmostEqual(frame.loc["AAA", "roe"], 0.2)
        self.assertEqual(frame.attrs["field_provenance"]["AAA"]["roe"]["source"], "sec_edgar")
        self.assertEqual(frame.attrs["field_provenance"]["AAA"]["per"]["source"], "yfinance")


class TestMarketDownload(unittest.TestCase):
    def _frame(self, tickers, periods=300):
        dates = pd.bdate_range(end=pd.Timestamp.now().normalize() - pd.Timedelta(days=1), periods=periods)
        cols = pd.MultiIndex.from_product([["Close", "Volume"], tickers])
        return pd.DataFrame(1.0, index=dates, columns=cols)

    def test_price_and_volume_share_one_download(self):
        loader = DataLoader(use_cache=False)
        with patch("yfinance.download", side_effect=lambda t, **k: self._frame(list(t))) as dl:
            loader.get_price_data(["AAA", "BBB"], "2025-01-01", "2026-01-01")
            loader.get_volume_data(["AAA", "BBB"], "2025-01-01", "2026-01-01")
        self.assertEqual(dl.call_count, 1)

    def test_chunking_and_bounded_retry(self):
        loader = DataLoader(use_cache=False)
        calls = []

        def fake(t, **k):
            calls.append(list(t))
            if len(calls) == 1:
                return pd.DataFrame()  # transient empty response -> retried
            return self._frame(list(t))
        with patch("utils.config.MARKET_DOWNLOAD_CHUNK", 2), patch("time.sleep"), patch("yfinance.download", side_effect=fake):
            prices = loader.get_price_data(["A", "B", "C"], "2025-01-01", "2026-01-01")
        self.assertEqual([len(c) for c in calls], [2, 2, 1])
        self.assertEqual(set(prices.columns), {"A", "B", "C"})
        self.assertTrue(any(e["event"] == "retry" for e in loader.provider_events))

    def test_total_failure_is_unavailable_never_fabricated(self):
        loader = DataLoader(use_cache=False)
        with patch("time.sleep"), patch("yfinance.download", return_value=pd.DataFrame()):
            prices = loader.get_price_data(["AAA"], "2025-01-01", "2026-01-01")
        self.assertTrue(prices["AAA"].isna().all())
        self.assertEqual(prices.attrs["provider_status"]["AAA"], "UNAVAILABLE")

    def test_missing_symbol_in_chunk_is_unavailable(self):
        loader = DataLoader(use_cache=False)
        frame = self._frame(["AAA", "ZZZ"])
        frame[("Close", "ZZZ")] = np.nan
        with patch("yfinance.download", return_value=frame):
            prices = loader.get_price_data(["AAA", "ZZZ"], "2025-01-01", "2026-01-01")
        self.assertEqual(prices.attrs["provider_status"]["ZZZ"], "UNAVAILABLE")

    def test_failed_symbol_adj_close_artifact_does_not_blank_prices(self):
        loader = DataLoader(use_cache=False)
        dates = pd.bdate_range(end=pd.Timestamp.now().normalize() - pd.Timedelta(days=1), periods=300)
        good = pd.DataFrame(1.0, index=dates, columns=pd.MultiIndex.from_product([["Close", "Volume"], ["AAA"]]))
        bad = pd.DataFrame(np.nan, index=dates, columns=pd.MultiIndex.from_product([["Adj Close", "Close", "Volume"], ["ZZZ"]]))
        frames = iter([good, bad])
        with patch("utils.config.MARKET_DOWNLOAD_CHUNK", 1), patch("yfinance.download", side_effect=lambda *a, **k: next(frames)):
            prices = loader.get_price_data(["AAA", "ZZZ"], "2025-01-01", "2026-01-01")
        self.assertEqual(prices.attrs["provider_status"]["AAA"], "REAL")
        self.assertEqual(prices.attrs["provider_status"]["ZZZ"], "UNAVAILABLE")


class TestFundamentalCache(unittest.TestCase):
    def test_cache_roundtrip_and_ttl(self):
        with tempfile.TemporaryDirectory() as tmp:
            loader = DataLoader(cache_dir=tmp)
            n = {"calls": 0}

            def info(self, t):
                n["calls"] += 1
                return {"trailingPE": 10.0, "priceToBook": 2.0, "returnOnEquity": 0.1, "profitMargins": 0.1}
            with patch.object(DataLoader, "_fetch_yf_info", info):
                loader.get_financial_data(["AAA"])
                frame = DataLoader(cache_dir=tmp).get_financial_data(["AAA"])
                self.assertEqual(n["calls"], 1)
                self.assertTrue(frame.attrs["field_provenance"]["AAA"]["_cache_hit"])
                path = Path(tmp) / "fundamentals" / "AAA.json"
                payload = json.loads(path.read_text())
                payload["retrieved_at"] = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
                path.write_text(json.dumps(payload))
                DataLoader(cache_dir=tmp).get_financial_data(["AAA"])
                self.assertEqual(n["calls"], 2)  # expired -> refetched

    def test_failed_provider_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(DataLoader, "_fetch_yf_info", lambda self, t: {}):
                DataLoader(cache_dir=tmp).get_financial_data(["AAA"])
            self.assertFalse((Path(tmp) / "fundamentals" / "AAA.json").exists())


if __name__ == "__main__":
    unittest.main()
