"""P6-18 canonical pipeline, operating modes and durable execution (offline, deterministic)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.run_recorder import STAGES
from pipeline.service import normalize_symbols, run_direct_evaluation, run_market_scan
from tests.p6_18_fakes import (FakeLoader, FakeSystem, FakeUniverse, make_financials, make_market,
                               pipeline_for)

T8 = [f"A{i}" for i in range(8)]


def loader_for(tickers=T8, **kw):
    prices, volumes = make_market(tickers)
    return FakeLoader(prices, volumes, make_financials(tickers), **kw)


class TestCanonicalPipeline(unittest.TestCase):
    def test_happy_path_real_recommendation_uses_model_rank_e(self):
        res = pipeline_for(loader_for()).evaluate(T8, {})
        self.assertEqual(res["pipeline_status"], "SUCCESS")
        self.assertEqual(res["recommendation_status"], "REAL RECOMMENDATION")
        self.assertEqual(res["model_version"], "MODEL_RANK_E")
        ranked = [r for r in res["candidate_flow"].values() if r.get("model_rank_e_rank")]
        self.assertGreaterEqual(len(ranked), 5)
        top = [r for r in res["candidate_flow"].values() if r["final_status"] == "TOP5"]
        self.assertEqual(len(top), 5)
        # TOP5 order follows MODEL_RANK_E order (sector cap inactive: all Energy)
        self.assertEqual(sorted(r["model_rank_e_rank"] for r in top), [1, 2, 3, 4, 5])

    def test_execution_success_is_not_recommendation_validity(self):
        res = pipeline_for(loader_for(T8[:4])).evaluate(T8[:4], {})
        self.assertEqual(res["pipeline_status"], "SUCCESS")
        self.assertEqual(res["recommendation_status"], "DATA-INCOMPLETE / NO VALID RECOMMENDATION")
        self.assertEqual(res["final_tradable_candidates_count"], 4)

    def test_stale_and_mock_excluded_before_scoring_and_do_not_influence_scores(self):
        base = pipeline_for(loader_for(T8[:6])).evaluate(T8[:6], {})
        prices, volumes = make_market(T8[:6])
        fin = make_financials(T8[:6])
        # Add two extra tickers with extreme data; mark them STALE / MOCK.
        extra_p = prices.copy()
        extra_p["STL"] = np.linspace(1, 1000, len(prices))
        extra_p["MCK"] = np.linspace(1000, 1, len(prices))
        extra_v = volumes.reindex(columns=list(extra_p.columns), fill_value=1e7)
        extra_f = pd.concat([fin, pd.DataFrame({"per": [1, 900], "pbr": [0.1, 90], "roe": [5, -5], "profitMargin": [3, -3]},
                                                index=["STL", "MCK"])])
        loader = FakeLoader(extra_p, extra_v, extra_f, price_status={"STL": "STALE"}, fin_status={"MCK": "MOCK"})
        res = pipeline_for(loader).evaluate(T8[:6] + ["STL", "MCK"], {})
        flow = res["candidate_flow"]
        self.assertEqual(flow["STL"]["final_status"], "QUARANTINED")
        self.assertEqual(flow["MCK"]["final_status"], "QUARANTINED")
        self.assertIn("PROVENANCE_STATUS_REJECTED", flow["STL"]["reasons"])
        for t in T8[:6]:  # identical alpha => quarantined data had zero influence
            self.assertAlmostEqual(flow[t]["alpha"], base["candidate_flow"][t]["alpha"], places=12)
        self.assertNotIn("STL", res["scores"].index)
        self.assertNotIn("MCK", res["scores"].index)

    def test_partial_fundamentals_quarantined_with_missing_fields(self):
        prices, volumes = make_market(T8)
        fin = make_financials(T8)
        fin.loc["A3", "per"] = np.nan  # e.g. negative earnings -> no trailing PE
        res = pipeline_for(FakeLoader(prices, volumes, fin)).evaluate(T8, {})
        rec = res["candidate_flow"]["A3"]
        self.assertEqual(rec["fundamental_status"], "PARTIAL")
        self.assertEqual(rec["final_status"], "QUARANTINED")
        self.assertEqual(rec["missing_fundamentals"], ["per"])

    def test_liquidity_uses_20_day_average_volume(self):
        prices, volumes = make_market(T8)
        volumes["A0"] = 400_000.0
        volumes.iloc[-1, volumes.columns.get_loc("A0")] = 50_000_000.0   # one huge day; ADV20 ~2.88M -> pass
        volumes["A1"] = 450_000.0
        volumes.iloc[-1, volumes.columns.get_loc("A1")] = 5_000_000.0    # ADV20 = 677,500 -> pass
        volumes["A2"] = 600_000.0
        volumes.iloc[-15:, volumes.columns.get_loc("A2")] = 300_000.0    # ADV20 = 375,000 -> reject, last day 300k
        volumes["A3"] = 300_000.0
        volumes.iloc[-1, volumes.columns.get_loc("A3")] = 900_000.0      # ADV20 = 330,000 -> reject despite 900k last day
        res = pipeline_for(FakeLoader(prices, volumes, make_financials(T8))).evaluate(T8, {})
        flow = res["candidate_flow"]
        self.assertAlmostEqual(flow["A1"]["adv20"], (450_000 * 19 + 5_000_000) / 20)
        self.assertEqual(flow["A1"]["liquidity"], "PASS")
        self.assertEqual(flow["A2"]["liquidity"], "FAIL")
        self.assertEqual(flow["A3"]["liquidity"], "FAIL")
        self.assertIn("LIQUIDITY_REJECTED", flow["A3"]["reasons"])
        self.assertEqual(flow["A3"]["last_volume"], 900_000.0)

    def test_market_data_unavailable_short_circuits_provider_calls(self):
        prices, volumes = make_market(T8)
        loader = FakeLoader(prices * np.nan, volumes * np.nan, make_financials(T8))
        res = pipeline_for(loader).evaluate(T8, {})
        self.assertEqual(res["pipeline_status"], "MARKET_DATA_UNAVAILABLE")
        self.assertEqual(res["status"], "LIVE DATA UNAVAILABLE")
        self.assertEqual(loader.calls["financial"], 0)

    def test_fundamentals_only_requested_for_tickers_with_market_data(self):
        prices, volumes = make_market(T8)
        prices["A7"] = np.nan
        loader = FakeLoader(prices, volumes, make_financials(T8))
        pipeline_for(loader).evaluate(T8, {})
        self.assertNotIn("A7", loader.financial_requested)

    def test_empty_universe(self):
        res = pipeline_for(loader_for()).evaluate([], {})
        self.assertEqual(res["recommendation_status"], "DATA-INCOMPLETE / NO VALID RECOMMENDATION")
        self.assertEqual(res["pipeline_status"], "UNIVERSE_UNAVAILABLE")

    def test_provenance_propagates_to_candidate_flow(self):
        res = pipeline_for(loader_for()).evaluate(T8, {})
        rec = res["candidate_flow"]["A0"]
        self.assertEqual(rec["price_status"], "REAL")
        self.assertEqual(rec["fundamental_provenance"]["per"]["source"], "fake")
        self.assertEqual(rec["last_bar"], "2026-01-15")
        self.assertIn("market", res["diagnostics"]["provenance"])

    def test_sector_cap_enforced_with_provider_sector(self):
        meta = {t: {"sector": "Technology"} for t in T8[:5]}
        res = pipeline_for(loader_for(meta=meta)).evaluate(T8, {})
        top = [r for r in res["candidate_flow"].values() if r["final_status"] == "TOP5"]
        self.assertLessEqual(sum(1 for r in top if r["sector"] == "Technology"), 2)

    def test_checkpoint_order(self):
        seen = []
        pipeline_for(loader_for(), checkpoint=lambda stage, **kw: seen.append(stage)).evaluate(T8, {})
        expected = [s for s in STAGES if s not in ("RUN_STARTED", "UNIVERSE_BOOTSTRAP_COMPLETED", "RUN_COMPLETED")]
        self.assertEqual(seen, expected)


class TestOperatingModesAndDurability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _read(self, result, name):
        return json.loads((Path(result["artifact_dir"]) / name).read_text())

    def test_market_scan_writes_all_artifacts_and_checkpoints(self):
        res = run_market_scan(capital=50_000, runs_dir=self.runs, universe_provider=FakeUniverse(T8),
                              system=FakeSystem(loader_for(), capital=50_000))
        self.assertEqual(res["display_status"], "REAL RECOMMENDATION")
        d = Path(res["artifact_dir"])
        for name in ("run_manifest.json", "validation_result.json", "provider_summary.json", "candidate_flow.json",
                     "execution_status.json", "report.html", "report.md", "checkpoints.jsonl"):
            self.assertTrue((d / name).exists(), name)
        self.assertFalse((d / "failure.json").exists())
        status = self._read(res, "execution_status.json")
        self.assertEqual(status["state"], "COMPLETED")
        self.assertEqual([c["stage"] for c in status["checkpoints"]], list(STAGES))
        manifest = self._read(res, "run_manifest.json")
        self.assertIn("sha256", manifest["frozen_core"])
        self.assertEqual(len(res["recommendations"]), 5)

    def test_failure_leaves_diagnostics_and_is_not_completed(self):
        res = run_market_scan(capital=50_000, runs_dir=self.runs, universe_provider=FakeUniverse(T8),
                              system=FakeSystem(loader_for(raise_on="financial")))
        self.assertEqual(res["execution_status"], "FAILED")
        failure = self._read(res, "failure.json")
        self.assertEqual(failure["failed_after_checkpoint"], "MARKET_DATA_ACQUISITION_COMPLETED")
        self.assertIn("simulated fundamentals crash", failure["error"])
        status = self._read(res, "execution_status.json")
        self.assertEqual(status["state"], "FAILED")
        self.assertNotIn("RUN_COMPLETED", [c["stage"] for c in status["checkpoints"]])

    def test_interrupt_marks_run_interrupted(self):
        class Boom(FakeLoader):
            def get_financial_data(self, *a, **k):
                raise KeyboardInterrupt()
        prices, volumes = make_market(T8)
        with self.assertRaises(KeyboardInterrupt):
            run_market_scan(capital=50_000, runs_dir=self.runs, universe_provider=FakeUniverse(T8),
                            system=FakeSystem(Boom(prices, volumes, make_financials(T8))))
        run_dir = next(p for p in Path(self.runs).iterdir() if p.is_dir())
        self.assertEqual(json.loads((run_dir / "execution_status.json").read_text())["state"], "INTERRUPTED")
        self.assertTrue((run_dir / "failure.json").exists())

    def test_stale_universe_yields_live_data_unavailable(self):
        res = run_market_scan(capital=50_000, runs_dir=self.runs, universe_provider=FakeUniverse(T8, status="STALE", freshness="STALE"),
                              system=FakeSystem(loader_for()))
        self.assertEqual(res["display_status"], "LIVE DATA UNAVAILABLE")
        self.assertEqual(res["recommendation_status"], "DATA-INCOMPLETE / NO VALID RECOMMENDATION")
        self.assertEqual(self._read(res, "execution_status.json")["state"], "COMPLETED")

    def test_bounded_scan_is_labelled_bounded(self):
        res = run_market_scan(capital=50_000, limit=6, runs_dir=self.runs, universe_provider=FakeUniverse(T8),
                              system=FakeSystem(loader_for()))
        self.assertEqual(res["validation_scope"], "bounded")
        self.assertEqual(res["evaluated_tickers"], 6)

    def test_direct_evaluation_same_pipeline_and_honest_verdicts(self):
        universe = T8
        extra = ["NEWCO", "BADSYM", "FUND"]
        all_t = universe + extra
        prices, volumes = make_market(all_t)
        prices["BADSYM"] = np.nan
        fin = make_financials(all_t)
        fin.loc["FUND", ["per", "pbr", "roe", "profitMargin"]] = np.nan
        meta = {"BADSYM": {"yf_info_ok": False, "quote_type": None, "sector": None},
                "FUND": {"quote_type": "ETF", "sector": None}}
        loader = FakeLoader(prices, volumes, fin, meta=meta)
        res = run_direct_evaluation(["newco, A2", "$fund", "badsym", "@@@!!"], capital=50_000, runs_dir=self.runs,
                                    universe_provider=FakeUniverse(universe, extra_ciks={"NEWCO": "999"}),
                                    system=FakeSystem(loader))
        evals = {e["input"]: e for e in res["ticker_evaluations"]}
        self.assertIn("!!", "".join(k for k in evals if evals[k]["verdict"] == "NOT_EVALUATED"))
        self.assertIn(evals["NEWCO"]["verdict"], {"TOP5", "WATCHLIST", "RANKED_NOT_SELECTED"})
        self.assertFalse(evals["NEWCO"]["in_sp500"])
        self.assertIsNotNone(evals["NEWCO"]["individual_evaluation"]["alpha"])
        ind = evals["NEWCO"]["individual_evaluation"]
        self.assertEqual(ind["requested_cross_section_size"], len(universe) + 3)
        self.assertEqual(ind["cross_section_size"], len(universe) + 1)  # BADSYM/FUND quarantined pre-scoring
        self.assertTrue(evals["A2"]["in_sp500"])
        self.assertEqual(evals["BADSYM"]["verdict"], "QUARANTINED")
        self.assertIn("SYMBOL_NOT_FOUND_OR_NO_PROVIDER_DATA", evals["BADSYM"]["reasons"])
        self.assertIsNone(evals["BADSYM"]["individual_evaluation"]["alpha"])  # no invented score
        self.assertEqual(evals["FUND"]["verdict"], "QUARANTINED")
        self.assertTrue(any("ETF" in l for l in evals["FUND"]["limitations"]))
        self.assertIn("portfolio_recommendation_status", evals["A2"]["portfolio_level"])
        # Same pipeline: fundamentals requested for the union, scored by the frozen route.
        self.assertIn("NEWCO", loader.financial_requested)
        self.assertEqual(res["model_version"], "MODEL_RANK_E")

    def test_direct_evaluation_without_universe_returns_limitation(self):
        res = run_direct_evaluation(["NVDA"], capital=50_000, runs_dir=self.runs,
                                    universe_provider=FakeUniverse([], status="UNAVAILABLE", freshness="UNAVAILABLE"),
                                    system=FakeSystem(loader_for()))
        self.assertEqual(res["display_status"], "LIVE DATA UNAVAILABLE")
        self.assertEqual(res["ticker_evaluations"][0]["reasons"], ["COMPARISON_UNIVERSE_UNAVAILABLE"])

    def test_symbol_normalization(self):
        n = normalize_symbols(["nvda, aapl", "BRK.B", "$TSLA", "nvda", "toolongsymbol", "1ABC"])
        self.assertEqual(n["valid"], ["NVDA", "AAPL", "BRK-B", "TSLA"])
        self.assertEqual(n["invalid"], ["toolongsymbol", "1ABC"])


class TestMockIsolation(unittest.TestCase):
    def test_canonical_route_never_imports_synthetic_or_adaptive_engines(self):
        import subprocess
        code = (
            "import sys; sys.path.insert(0, '.');"
            "from tests.p6_18_fakes import *; from main import QuantTradingSystemV2;"
            "s = QuantTradingSystemV2(mode='live', initial_capital=1e4);"
            "T=[f'A{i}' for i in range(8)]; p,v=make_market(T); s.data_loader=FakeLoader(p,v,make_financials(T));"
            "r = s.run_live_cycle(T); assert r['model_version']=='MODEL_RANK_E', r;"
            "bad=[m for m in ('core.alternative_data_engine','alpha_engine.data.fallback_engine','core.meta_alpha_engine',"
            "'core.factor_weight_optimizer','core.learning_engine','core.llm_fundamental_engine','core.news_engine',"
            "'core.rag_engine','alpha_engine.data.sentiment_engine') if m in sys.modules]; print('BAD', bad); assert not bad"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=str(Path(__file__).resolve().parents[1]),
                             capture_output=True, text=True, env={**__import__("os").environ, "QPP_LOG_LEVEL": "ERROR"})
        self.assertEqual(out.returncode, 0, out.stdout[-2000:] + out.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
