"""P6-19 independent verification & operational hardening (offline, deterministic).

Covers: configuration (SEC_USER_AGENT, explicit capital, .env), the four
approved input definitions (ADV20 boundaries/hygiene, provider sector + cap,
exclusion before normalisation, SEC fiscal-period selection), cache status,
frozen-source pinning, direct single-ticker evaluation, CLI refusal paths,
secret hygiene and the forward-tracking foundation.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.loader import DataLoader
from pipeline.run_recorder import frozen_source_hashes
from pipeline.service import run_direct_evaluation, run_market_scan
from tests.p6_18_fakes import FakeLoader, FakeSystem, FakeUniverse, make_financials, make_market, pipeline_for
from utils import runtime_config
from utils.runtime_config import CapitalNotConfigured

T8 = [f"A{i}" for i in range(8)]
VALID_UA = "QuantStockEngine/1.0 someone@realmail.org"
# P6-20-A3: a Yahoo profitMargins fallback is used only when its latest quarter is fresh.
FRESH_MRQ = int(pd.Timestamp.now(tz="UTC").normalize().timestamp()) - 30 * 86400


# --------------------------------------------------------------- configuration
class TestSecUserAgent(unittest.TestCase):
    def test_statuses(self):
        f = runtime_config.sec_user_agent_status
        self.assertEqual(f("")["status"], "MISSING")
        self.assertEqual(f("   ")["status"], "MISSING")
        self.assertEqual(f("AntigravityIDE/1.0 (soominseok@example.com)")["status"], "INVALID")  # former default
        self.assertEqual(f("App/1.0 contact@example.org")["status"], "INVALID")
        self.assertEqual(f("App/1.0 <your e-mail>")["status"], "INVALID")
        self.assertEqual(f("App/1.0 no-email-here")["status"], "INVALID")
        self.assertEqual(f("me@realmail.org")["status"], "INVALID")  # needs an app name too
        self.assertEqual(f(VALID_UA)["status"], "CONFIGURED")

    def test_config_has_no_fabricated_default(self):
        src = (ROOT / "utils" / "config.py").read_text()
        self.assertRegex(src, r'SEC_USER_AGENT = os\.getenv\("SEC_USER_AGENT", ""\)')
        self.assertNotIn("@example.com)\")", src)


class TestCapital(unittest.TestCase):
    def test_no_default_capital(self):
        with patch.dict(os.environ, {"QPP_CAPITAL": ""}):
            with self.assertRaises(CapitalNotConfigured):
                runtime_config.resolve_capital(None)

    def test_parse_and_sources(self):
        self.assertEqual(runtime_config.parse_capital("50,000"), 50_000.0)
        self.assertEqual(runtime_config.parse_capital("$12_500.5"), 12_500.5)
        for bad in (0, -1, "0", "abc", float("nan"), float("inf"), "", None, True):
            with self.assertRaises(CapitalNotConfigured, msg=repr(bad)):
                runtime_config.parse_capital(bad)
        with patch.dict(os.environ, {"QPP_CAPITAL": "75000"}):
            self.assertEqual(runtime_config.resolve_capital(None), (75_000.0, "QPP_CAPITAL (environment / .env)"))
            self.assertEqual(runtime_config.resolve_capital("1000")[0], 1000.0)  # CLI wins

    def test_service_refuses_missing_capital_without_creating_a_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, v = make_market(T8)
            system = FakeSystem(FakeLoader(p, v, make_financials(T8)))
            for fn in (lambda: run_market_scan(None, runs_dir=tmp, universe_provider=FakeUniverse(T8), system=system),
                       lambda: run_direct_evaluation(["A1"], None, runs_dir=tmp, universe_provider=FakeUniverse(T8),
                                                     system=system)):
                with self.assertRaises(CapitalNotConfigured):
                    fn()
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_capital_and_source_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, v = make_market(T8)
            res = run_market_scan(25_000, runs_dir=tmp, universe_provider=FakeUniverse(T8),
                                  system=FakeSystem(FakeLoader(p, v, make_financials(T8)), capital=25_000),
                                  capital_source="test")
            val = json.loads((Path(res["artifact_dir"]) / "validation_result.json").read_text())
            self.assertEqual(val["capital"], 25_000)
            self.assertEqual(val["capital_source"], "test")
            self.assertIn("does NOT mean", val["disclaimer"])
            notional = sum(r["target_notional"] for r in val["recommendations"])
            self.assertLessEqual(notional, 25_000 + 1e-6)


class TestEnvFile(unittest.TestCase):
    def test_env_file_does_not_override_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = Path(tmp) / ".env"
            env.write_text('# comment\nQPP_TEST_A="from file"\nexport QPP_TEST_B=2 # trailing\nQPP_TEST_C=x\n')
            with patch.dict(os.environ, {"QPP_TEST_C": "shell"}, clear=False):
                loaded = runtime_config.load_local_env(env)
                self.assertEqual(os.environ["QPP_TEST_A"], "from file")
                self.assertEqual(os.environ["QPP_TEST_B"], "2")
                self.assertEqual(os.environ["QPP_TEST_C"], "shell")
                self.assertNotIn("QPP_TEST_C", loaded)
            for k in ("QPP_TEST_A", "QPP_TEST_B"):
                os.environ.pop(k, None)

    def test_env_is_git_ignored_and_example_has_no_values(self):
        gi = (ROOT / ".gitignore").read_text().splitlines()
        self.assertIn(".env", gi)
        ex = (ROOT / ".env.example").read_text()
        for line in ex.splitlines():
            if line and not line.startswith("#") and "=" in line and not line.startswith(" "):
                key, value = line.split("=", 1)
                if key in ("SEC_USER_AGENT", "QPP_CAPITAL", "NEWS_API_KEY"):
                    self.assertEqual(value.strip(), "", key)


class TestSecretHygiene(unittest.TestCase):
    def test_no_hardcoded_newsapi_key_in_active_source(self):
        pattern = re.compile(r"NEWS_API_KEY\s*=\s*os\.getenv\(\s*['\"]NEWS_API_KEY['\"]\s*,\s*['\"][A-Za-z0-9]{20,}")
        offenders = []
        for p in ROOT.rglob("*.py"):
            if ".venv" in p.parts or "tests" in p.parts:
                continue
            try:
                if pattern.search(p.read_text(errors="ignore")):
                    offenders.append(str(p))
            except OSError:
                continue
        self.assertEqual(offenders, [])

    def test_no_hardcoded_sec_contacts_in_source(self):
        offenders = []
        for p in list((ROOT / "scripts").glob("*.py")) + list((ROOT / "providers").glob("*.py")) + \
                list((ROOT / "alpha_engine").rglob("*.py")) + [ROOT / "data" / "loader.py", ROOT / "utils" / "config.py"]:
            text = p.read_text(errors="ignore")
            if re.search(r"User-Agent[\"']?\s*:\s*[\"'][^\"']*@", text) or \
                    re.search(r"getenv\(\s*[\"']SEC_USER_AGENT[\"']\s*,\s*[\"'][^\"']*@", text):
                offenders.append(str(p.relative_to(ROOT)))
        self.assertEqual(offenders, [])


# ----------------------------------------------------- B1 average daily volume
class TestADV20(unittest.TestCase):
    def _run(self, adv_by_ticker, mutate=None):
        prices, volumes = make_market(T8)
        for t, adv in adv_by_ticker.items():
            volumes[t] = float(adv)
        if mutate:
            prices, volumes = mutate(prices, volumes)
        return pipeline_for(FakeLoader(prices, volumes, make_financials(T8))).evaluate(T8, {})["candidate_flow"]

    def test_frozen_threshold_boundaries(self):
        flow = self._run({"A0": 499_999, "A1": 500_000, "A2": 500_001})
        self.assertEqual(flow["A0"]["liquidity"], "FAIL")
        self.assertEqual(flow["A1"]["liquidity"], "PASS")   # frozen rule: volume >= 500,000
        self.assertEqual(flow["A2"]["liquidity"], "PASS")

    def test_share_volume_not_dollar_volume(self):
        # price ~100 and 6,000 shares/day = ~$600k/day dollar volume: must FAIL a 500k *share* threshold.
        flow = self._run({"A0": 6_000})
        self.assertEqual(flow["A0"]["liquidity"], "FAIL")
        self.assertAlmostEqual(flow["A0"]["adv20"], 6_000)
        self.assertIn("shares/day", flow["A0"]["adv20_window"]["unit"])

    def test_uses_20_valid_observations_and_ignores_nan_sessions(self):
        def mutate(p, v):
            v["A0"] = 1_000_000.0
            v.iloc[-5:, v.columns.get_loc("A0")] = np.nan     # 5 missing sessions are not observations
            v.iloc[-25:-5, v.columns.get_loc("A0")] = 400_000.0
            return p, v
        flow = self._run({}, mutate)
        self.assertAlmostEqual(flow["A0"]["adv20"], 400_000.0)
        self.assertEqual(flow["A0"]["adv20_window"]["observations"], 20)
        self.assertEqual(flow["A0"]["liquidity"], "FAIL")

    def test_duplicate_sessions_cannot_distort(self):
        def mutate(p, v):
            v["A0"] = 400_000.0
            dup = v.iloc[[-1] * 10].copy()
            dup["A0"] = 10_000_000.0
            v = pd.concat([v, dup])          # ten duplicated copies of the last session with huge volume
            return p, v
        flow = self._run({}, mutate)
        # one observation per session (last value kept) => window = 19 x 400k + 1 x 10M
        self.assertAlmostEqual(flow["A0"]["adv20"], (19 * 400_000 + 10_000_000) / 20)

    def test_insufficient_history_is_missing_not_zero(self):
        def mutate(p, v):
            v["A0"] = np.nan
            v.iloc[-10:, v.columns.get_loc("A0")] = 2_000_000.0
            return p, v
        flow = self._run({}, mutate)
        self.assertIsNone(flow["A0"]["adv20"])
        self.assertIn("REQUIRED_NUMERIC_DATA_MISSING", flow["A0"]["reasons"])


# ---------------------------------------------------------------- B2 sector
class TestSector(unittest.TestCase):
    def test_tech_cap_counts_same_sector_together(self):
        prices, volumes = make_market(T8)
        meta = {t: {"sector": "Technology"} for t in T8}  # every candidate Technology
        res = pipeline_for(FakeLoader(prices, volumes, make_financials(T8), meta=meta)).evaluate(T8, {})
        top = [r for r in res["candidate_flow"].values() if r["final_status"] == "TOP5"]
        self.assertEqual(len(top), 2)                      # frozen 40% cap = 2 of 5 slots
        self.assertEqual(res["recommendation_status"], "DATA-INCOMPLETE / NO VALID RECOMMENDATION")
        watch = [r for r in res["candidate_flow"].values() if r["final_status"] == "WATCHLIST"]
        self.assertTrue(all("SECTOR_CAP_CONSTRAINT" in r["reason_codes"] for r in watch))
        self.assertAlmostEqual(res["portfolio_decision"].sector_exposure["Technology"], 0.40)

    def test_missing_sector_is_unknown_and_flagged_never_invented(self):
        prices, volumes = make_market(T8)
        meta = {"A0": {"sector": None}}
        res = pipeline_for(FakeLoader(prices, volumes, make_financials(T8), meta=meta)).evaluate(T8, {})
        rec = res["candidate_flow"]["A0"]
        self.assertEqual(rec["sector"], "Unknown")
        self.assertIsNone(rec["sector_source"])
        self.assertIn("SECTOR_UNKNOWN_CAP_NOT_APPLICABLE", rec["reasons"])

    def test_non_tech_concentration_is_reported_not_enforced(self):
        from pipeline.service import _sector_cap_warnings
        self.assertTrue(_sector_cap_warnings({"Energy": 1.0})[0].startswith("Energy exposure 100%"))
        self.assertEqual(_sector_cap_warnings({"Technology": 0.4, "Energy": 0.4, "Utilities": 0.2}), [])

    def test_sector_survives_into_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, v = make_market(T8)
            meta = {t: {"sector": "Technology" if t in ("A0", "A1") else "Healthcare"} for t in T8}
            res = run_market_scan(50_000, runs_dir=tmp, universe_provider=FakeUniverse(T8),
                                  system=FakeSystem(FakeLoader(p, v, make_financials(T8), meta=meta)))
            flow = json.loads((Path(res["artifact_dir"]) / "candidate_flow.json").read_text())["candidates"]
            self.assertEqual({t: flow[t]["sector"] for t in T8}, {t: meta[t]["sector"] for t in T8})


# ------------------------------------------- B3 exclusion before normalisation
class TestExclusionBeforeNormalisation(unittest.TestCase):
    def test_excluded_candidate_values_cannot_change_valid_scores(self):
        prices, volumes = make_market(T8)
        fin = make_financials(T8)
        fin.loc["A7", "per"] = np.nan                     # PARTIAL -> excluded by the frozen data-quality rule
        a = pipeline_for(FakeLoader(prices, volumes, fin.copy())).evaluate(T8, {})["candidate_flow"]
        fin2, prices2 = fin.copy(), prices.copy()
        fin2.loc["A7", ["pbr", "roe", "profitMargin"]] = [999.0, -50.0, 40.0]  # extreme values on the excluded name
        prices2["A7"] = np.linspace(1, 5000, len(prices2))
        b = pipeline_for(FakeLoader(prices2, volumes, fin2)).evaluate(T8, {})["candidate_flow"]
        self.assertEqual(a["A7"]["final_status"], "QUARANTINED")
        for t in T8[:7]:
            self.assertEqual(a[t]["alpha"], b[t]["alpha"], t)
            self.assertEqual(a[t]["alpha_percentile"], b[t]["alpha_percentile"], t)
            self.assertEqual(a[t]["factors"], b[t]["factors"], t)
            self.assertEqual(a[t].get("model_rank_e_rank"), b[t].get("model_rank_e_rank"), t)

    def test_partial_rejection_is_the_frozen_rule_itself(self):
        """The frozen DecisionEngine rejects PARTIAL; the canonical gate only moves the same rule earlier."""
        from core.decision_engine import DecisionEngine
        c = {"ticker": "X", "close": 10.0, "volume": 1e6, "alpha": 1.0, "atr": 1.0, "ema20": 9.0,
             "data_status": "REAL", "price_status": "REAL", "volume_status": "REAL", "fundamental_status": "PARTIAL"}
        self.assertFalse(DecisionEngine()._check_data_quality(c))
        c["fundamental_status"] = "CACHED"
        self.assertTrue(DecisionEngine()._check_data_quality(c))


# --------------------------------------------------- B4 SEC fiscal periods
_now = pd.Timestamp.now().normalize()
RECENT_QE = str((_now - pd.offsets.QuarterEnd(1)).date()) if (_now - (_now - pd.offsets.QuarterEnd(1))).days > 3 \
    else str((_now - pd.offsets.QuarterEnd(2)).date())
RECENT_QE_FILED = str((pd.Timestamp(RECENT_QE) + pd.Timedelta(days=2)).date())


def _fy(year, val, filed, form="10-K", accn=None, start=None):
    return {"start": start or f"{year}-01-01", "end": f"{year}-12-31", "val": val, "fy": year, "fp": "FY",
            "form": form, "filed": filed, "accn": accn or f"0000-{year}-{filed}"}


class TestSecFiscalPeriods(unittest.TestCase):
    Y = pd.Timestamp.now().year

    def facts(self, ni, rev, eq):
        return {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": ni}},
                                      "Revenues": {"units": {"USD": rev}},
                                      "StockholdersEquity": {"units": {"USD": eq}}}}}

    def test_restatement_for_same_period_wins_and_keeps_accession(self):
        y = self.Y - 1
        ni = [_fy(y, 100.0, f"{y + 1}-02-10", accn="orig"), _fy(y, 90.0, f"{y + 1}-05-01", form="10-K/A", accn="amend")]
        rev = [_fy(y, 1000.0, f"{y + 1}-02-10")]
        eq = [{"end": f"{y}-12-31", "val": 500.0, "form": "10-K", "filed": f"{y + 1}-02-10", "accn": "orig"}]
        m = DataLoader(use_cache=False)._sec_metrics(self.facts(ni, rev, eq))
        self.assertAlmostEqual(m["roe"], 90.0 / 500.0)
        self.assertEqual(m["detail"]["net_income"]["accn"], "amend")
        self.assertEqual(m["detail"]["net_income"]["form"], "10-K/A")

    def test_prior_year_comparative_in_later_filing_is_not_the_latest_period(self):
        y = self.Y - 1
        # The FY(y) 10-K also re-reports FY(y-1) (comparative) with a LATER filed date than FY(y-1)'s own 10-K.
        ni = [_fy(y - 1, 50.0, f"{y}-02-10"), _fy(y - 1, 51.0, f"{y + 1}-02-10"), _fy(y, 70.0, f"{y + 1}-02-10")]
        rev = [_fy(y - 1, 600.0, f"{y + 1}-02-10"), _fy(y, 700.0, f"{y + 1}-02-10")]
        eq = [{"end": f"{y - 1}-12-31", "val": 300.0, "form": "10-K", "filed": f"{y + 1}-02-10"},
              {"end": f"{y}-12-31", "val": 350.0, "form": "10-K", "filed": f"{y + 1}-02-10"}]
        m = DataLoader(use_cache=False)._sec_metrics(self.facts(ni, rev, eq))
        self.assertEqual(m["detail"]["fiscal_period_end"], f"{y}-12-31")
        self.assertAlmostEqual(m["roe"], 70.0 / 350.0)
        self.assertAlmostEqual(m["profitMargin"], 70.0 / 700.0)

    def test_quarterly_and_ytd_durations_ignored_and_52_53_week_years_accepted(self):
        y = self.Y - 1
        q = {"start": f"{y}-10-01", "end": f"{y}-12-31", "val": 25.0, "fp": "Q4", "form": "10-K", "filed": f"{y + 1}-02-10"}
        week53 = _fy(y, 80.0, f"{y + 1}-02-10", start=f"{y - 1}-12-25")  # 371-day fiscal year
        rev = [_fy(y, 800.0, f"{y + 1}-02-10", start=f"{y - 1}-12-25")]
        eq = [{"end": f"{y}-12-31", "val": 400.0, "form": "10-K", "filed": f"{y + 1}-02-10"}]
        m = DataLoader(use_cache=False)._sec_metrics(self.facts([q, week53], rev, eq))
        self.assertAlmostEqual(m["roe"], 80.0 / 400.0)

    def test_metrics_never_mix_periods_and_provenance_is_per_field(self):
        y = self.Y - 1
        ni = [_fy(y, 70.0, f"{y + 1}-02-10")]
        rev = [_fy(y - 1, 600.0, f"{y}-02-10")]            # revenue only for an older period
        eq = [{"end": f"{y - 1}-12-31", "val": 350.0, "form": "10-K", "filed": f"{y}-02-10"}]  # equity only older
        m = DataLoader(use_cache=False)._sec_metrics(self.facts(ni, rev, eq))
        self.assertTrue(np.isnan(m["roe"]) and np.isnan(m["profitMargin"]))
        loader = DataLoader(use_cache=False)
        info = {"trailingPE": 20.0, "priceToBook": 3.0, "returnOnEquity": 0.11, "profitMargins": 0.07,
                "mostRecentQuarter": FRESH_MRQ}
        with patch.object(DataLoader, "_fetch_yf_info", lambda self, t: info), \
                patch.object(DataLoader, "_fetch_sec_facts", lambda self, cik: self_facts), \
                patch.dict(os.environ, {"SEC_USER_AGENT": VALID_UA}):
            self_facts = self.facts([_fy(y, 70.0, f"{y + 1}-02-10", accn="A1")], [],
                                    [{"end": f"{y}-12-31", "val": 350.0, "form": "10-K", "filed": f"{y + 1}-02-10",
                                      "accn": "A1"}])
            frame = loader.get_financial_data(["AAA"], ciks={"AAA": "1"})
        prov = frame.attrs["field_provenance"]["AAA"]
        self.assertEqual(prov["roe"]["source"], "sec_edgar")            # SEC ROE (aligned)
        self.assertEqual(prov["profitMargin"]["source"], "yfinance")    # no aligned SEC revenue -> Yahoo
        self.assertEqual(prov["_sec_filings"]["net_income"]["accn"], "A1")


class TestP619LiveDefectRegressions(unittest.TestCase):
    """Defects found in the P6-19 full live run (CPT revenue concept, BRK-B Yahoo priceToBook)."""
    Y = pd.Timestamp.now().year

    # P6-20-A supersedes the P6-19 "largest revenue concept" and REJECTED_INCONSISTENT rules for these
    # same live defect cases (CPT, FITB/DTE/HBAN/MTB, BRK-B); see docs/DATA_INPUT_SPECIFICATION.md.
    def test_reit_revenue_component_is_never_total_revenue(self):
        """CPT: only ASC 606 ($13M) and lease income ($1,573M) tagged -> no reliable total -> UNAVAILABLE."""
        y = self.Y - 1
        facts = {"facts": {"us-gaap": {
            "NetIncomeLoss": {"units": {"USD": [_fy(y, 384.0, f"{y + 1}-02-12")]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [_fy(y, 13.0, f"{y + 1}-02-12")]}},
            "OperatingLeaseLeaseIncome": {"units": {"USD": [_fy(y, 1573.0, f"{y + 1}-02-12")]}},
            "StockholdersEquity": {"units": {"USD": [{"end": f"{y}-12-31", "val": 4362.0, "form": "10-K",
                                                      "filed": f"{y + 1}-02-12"}]}}}}}
        m = DataLoader(use_cache=False)._sec_metrics(facts)
        self.assertTrue(np.isnan(m["profitMargin"]))          # neither 384/13 nor 384/1573
        sel = m["detail"]["revenue_selection"]
        self.assertEqual(sel["status"], "UNAVAILABLE")
        reasons = {r["concept"]: r["reason"] for r in sel["rejected"]}
        self.assertEqual(reasons["RevenueFromContractWithCustomerExcludingAssessedTax"],
                         "SINGLE_STREAM_CONCEPT_WITH_OTHER_REVENUE_STREAMS")
        self.assertEqual(reasons["OperatingLeaseLeaseIncome"], "COMPONENT_NOT_TOTAL_REVENUE")
        self.assertAlmostEqual(m["roe"], 384.0 / 4362.0)

    def test_partial_revenue_line_is_rejected_and_validated_yahoo_margin_used(self):
        """FITB/DTE case: only a slice (lease income) is tagged -> no SEC margin -> validated Yahoo margin."""
        y = self.Y - 1
        facts = {"facts": {"us-gaap": {
            "NetIncomeLoss": {"units": {"USD": [_fy(y, 2500.0, f"{y + 1}-02-24")]}},
            "OperatingLeaseLeaseIncome": {"units": {"USD": [_fy(y, 80.0, f"{y + 1}-02-24")]}},
            "StockholdersEquity": {"units": {"USD": [{"end": f"{y}-12-31", "val": 21000.0, "form": "10-K",
                                                      "filed": f"{y + 1}-02-24"}]}}}}}
        m = DataLoader(use_cache=False)._sec_metrics(facts)
        self.assertTrue(np.isnan(m["profitMargin"]))
        self.assertEqual(m["detail"]["revenue_rejected"]["reason"], "NO_RELIABLE_TOTAL_REVENUE")
        self.assertAlmostEqual(m["roe"], 2500.0 / 21000.0)            # ROE is unaffected
        info = {"trailingPE": 12.0, "priceToBook": 1.5, "profitMargins": 0.27, "quoteType": "EQUITY",
                "mostRecentQuarter": FRESH_MRQ}
        with patch.object(DataLoader, "_fetch_yf_info", lambda self, t: dict(info)), \
                patch.object(DataLoader, "_fetch_sec_facts", lambda self, cik: facts), \
                patch.dict(os.environ, {"SEC_USER_AGENT": VALID_UA}):
            frame = DataLoader(use_cache=False).get_financial_data(["BANK"], ciks={"BANK": "1"})
        prov = frame.attrs["field_provenance"]["BANK"]["profitMargin"]
        self.assertEqual(frame.loc["BANK", "profitMargin"], 0.27)
        self.assertEqual(prov["source"], "yfinance")
        self.assertEqual(prov["yahoo_validation"]["status"], "VALID")
        self.assertEqual(prov["sec_rejected"]["rejected_facts"][0]["concept"], "OperatingLeaseLeaseIncome")

    def test_yahoo_pbr_inconsistent_with_sec_equity_is_unavailable_not_replaced(self):
        y = self.Y - 1
        facts = {"facts": {"us-gaap": {
            "NetIncomeLoss": {"units": {"USD": [_fy(y, 67.0, f"{y + 1}-03-02")]}},
            "Revenues": {"units": {"USD": [_fy(y, 371.0, f"{y + 1}-03-02")]}},
            "StockholdersEquity": {"units": {"USD": [{"end": RECENT_QE, "val": 717.0, "form": "10-Q",
                                                      "filed": RECENT_QE_FILED}]}}}}}
        base = {"trailingPE": 14.0, "marketCap": 1000.0, "currentPrice": 10.0, "sharesOutstanding": 100.0,
                "quoteType": "EQUITY", "currency": "USD"}
        infos = {"BRKB": {**base, "priceToBook": 0.00107}, "OK": {**base, "priceToBook": 1.5},
                 "NOCAP": {"trailingPE": 14.0, "priceToBook": 0.00107, "quoteType": "EQUITY"}}
        with patch.object(DataLoader, "_fetch_yf_info", lambda self, t: dict(infos[t])), \
                patch.object(DataLoader, "_fetch_sec_facts", lambda self, cik: facts), \
                patch.dict(os.environ, {"SEC_USER_AGENT": VALID_UA}):
            frame = DataLoader(use_cache=False).get_financial_data(["BRKB", "OK", "NOCAP"],
                                                                  ciks={"BRKB": "1", "OK": "2", "NOCAP": "3"})
        prov = frame.attrs["field_provenance"]
        self.assertTrue(np.isnan(frame.loc["BRKB", "pbr"]))
        self.assertEqual(prov["BRKB"]["pbr"]["status"], "UNAVAILABLE")
        self.assertEqual(prov["BRKB"]["pbr"]["reason"], "PBR_INCONSISTENT_WITH_SEC_COMMON_EQUITY")
        self.assertAlmostEqual(prov["BRKB"]["pbr"]["rejected_provider_value"]["provider_value"], 0.00107)
        self.assertEqual(frame.attrs["provider_status"]["BRKB"], "PARTIAL")
        self.assertEqual(frame.loc["OK", "pbr"], 1.5)
        self.assertEqual(prov["OK"]["pbr"]["consistency_check"]["status"], "CONSISTENT")
        self.assertEqual(frame.loc["NOCAP", "pbr"], 0.00107)   # cannot verify -> unchanged, labelled
        self.assertEqual(prov["NOCAP"]["pbr"]["consistency_check"]["status"], "NOT_VERIFIABLE")
        self.assertIn("MARKET_CAP_UNAVAILABLE", prov["NOCAP"]["pbr"]["consistency_check"]["reasons"])

    def test_rejected_provider_value_surfaces_as_reason(self):
        prices, volumes = make_market(T8)
        fin = make_financials(T8)
        fin.loc["A0", "pbr"] = np.nan

        class L(FakeLoader):
            def get_financial_data(self, tickers, ciks=None):
                frame = super().get_financial_data(tickers, ciks)
                frame.attrs["field_provenance"]["A0"]["pbr"] = {"source": None, "status": "REJECTED_INCONSISTENT"}
                return frame
        res = pipeline_for(L(prices, volumes, fin)).evaluate(T8, {})
        self.assertIn("PROVIDER_VALUE_REJECTED_PBR", res["candidate_flow"]["A0"]["reasons"])
        self.assertEqual(res["candidate_flow"]["A0"]["final_status"], "QUARANTINED")


# -------------------------------------------------- loader / SEC gating / cache
class TestSecGatingAndCache(unittest.TestCase):
    INFO = {"trailingPE": 10.0, "priceToBook": 2.0, "returnOnEquity": 0.1, "profitMargins": 0.1,
            "sector": "Energy", "quoteType": "EQUITY", "mostRecentQuarter": FRESH_MRQ}

    def test_sec_never_queried_without_valid_user_agent(self):
        def boom(self, cik):
            raise AssertionError("SEC must not be queried without SEC_USER_AGENT")
        with patch.dict(os.environ, {"SEC_USER_AGENT": ""}), \
                patch.object(DataLoader, "_fetch_sec_facts", boom), \
                patch.object(DataLoader, "_fetch_yf_info", lambda self, t: dict(TestSecGatingAndCache.INFO)):
            frame = DataLoader(use_cache=False).get_financial_data(["AAA"], ciks={"AAA": "320193"})
        self.assertEqual(frame.attrs["field_provenance"]["AAA"]["_sec_status"], "SEC_NOT_CONFIGURED")
        self.assertEqual(frame.attrs["field_provenance"]["AAA"]["roe"]["source"], "yfinance")

    def test_sec_ticker_map_not_fetched_without_user_agent(self):
        from core.universe_provider import SecTickerMap
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"SEC_USER_AGENT": ""}), \
                patch("requests.get", side_effect=AssertionError("no SEC request allowed")):
            m = SecTickerMap(cache_file=str(Path(tmp) / "none.json")).load()
        self.assertEqual(m.provenance["status"], "UNAVAILABLE")
        self.assertEqual(m.provenance["live_fetch"]["status"], "NOT_QUERIED")

    def test_cache_hit_is_labelled_cached_and_invalidated_when_sec_config_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = {"n": 0}

            def info(self, t):
                calls["n"] += 1
                return dict(TestSecGatingAndCache.INFO)
            with patch.object(DataLoader, "_fetch_yf_info", info), \
                    patch.object(DataLoader, "_fetch_sec_facts", lambda self, cik: {}), \
                    patch.dict(os.environ, {"SEC_USER_AGENT": ""}):
                first = DataLoader(cache_dir=tmp).get_financial_data(["AAA"], ciks={"AAA": "1"})
                second = DataLoader(cache_dir=tmp).get_financial_data(["AAA"], ciks={"AAA": "1"})
                self.assertEqual(first.attrs["provider_status"]["AAA"], "REAL")
                self.assertEqual(second.attrs["provider_status"]["AAA"], "CACHED")
                self.assertEqual(calls["n"], 1)
                with patch.dict(os.environ, {"SEC_USER_AGENT": VALID_UA}):
                    DataLoader(cache_dir=tmp).get_financial_data(["AAA"], ciks={"AAA": "1"})
                self.assertEqual(calls["n"], 2)  # SEC newly configured -> cache entry refreshed


# ------------------------------------------------------------- frozen source pin
class TestFrozenSourcePinned(unittest.TestCase):
    PINNED = json.loads((ROOT / "tests" / "fixtures" / "frozen_source_sha256_p6_19.json").read_text())

    def test_frozen_engine_sources_unchanged(self):
        self.assertEqual(frozen_source_hashes(), self.PINNED["sha256"])


# ------------------------------------------------- direct single-ticker evaluation
class TestDirectSingleTicker(unittest.TestCase):
    def test_single_ticker_evaluated_even_when_no_portfolio_recommendation(self):
        tickers = T8[:4]                          # only 4 eligible -> portfolio cannot be REAL
        with tempfile.TemporaryDirectory() as tmp:
            p, v = make_market(tickers)
            res = run_direct_evaluation(["A2"], 50_000, runs_dir=tmp, universe_provider=FakeUniverse(tickers),
                                        system=FakeSystem(FakeLoader(p, v, make_financials(tickers))))
        self.assertEqual(res["recommendation_status"], "DATA-INCOMPLETE / NO VALID RECOMMENDATION")
        ev = res["ticker_evaluations"][0]
        ind = ev["individual_evaluation"]
        self.assertIsNotNone(ind["alpha"])
        self.assertIsNotNone(ind["alpha_percentile"])
        self.assertIsNotNone(ind["model_rank_e_rank"])
        self.assertEqual(ind["cross_section_size"], 4)
        self.assertEqual(ev["portfolio_level"]["portfolio_recommendation_status"],
                         "DATA-INCOMPLETE / NO VALID RECOMMENDATION")
        self.assertEqual(ev["verdict"], "TOP5")   # selected, but the portfolio as a whole is not valid


# ------------------------------------------------------------------------ CLI
class TestCli(unittest.TestCase):
    def _run(self, *args, env=None):
        e = {k: v for k, v in os.environ.items() if k not in ("QPP_CAPITAL",)}
        e.update(env or {}, QPP_LOG_LEVEL="ERROR", QPP_RUNS_DIR=self.tmp.name)
        return subprocess.run([sys.executable, str(ROOT / "app.py"), *args], capture_output=True, text=True,
                              env=e, timeout=120)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_scan_without_capital_refuses_before_any_run(self):
        out = self._run("scan", "--limit", "3", env={"QPP_CAPITAL": ""})
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertIn("Capital is not configured", out.stderr)
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_invalid_capital_refused(self):
        out = self._run("evaluate", "AAPL", "--capital", "-5")
        self.assertEqual(out.returncode, 2)
        self.assertIn("positive", out.stderr)

    def test_help_and_doctor_offline(self):
        self.assertEqual(self._run("--help").returncode, 0)
        out = self._run("doctor")
        self.assertIn("SEC_USER_AGENT", out.stdout)
        self.assertIn("capital", out.stdout)
        self.assertNotIn("@", out.stdout.split("SEC_USER_AGENT", 1)[1].splitlines()[0])  # never prints the contact


if __name__ == "__main__":
    unittest.main()
