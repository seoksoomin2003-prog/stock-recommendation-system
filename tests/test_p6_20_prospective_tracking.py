"""P6-20 prospective tracking: ledger immutability, entry timing, outcomes, paper portfolio,
cohorts, diagnostics and safe updates.  Offline, deterministic, isolated temp directories."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.decision_engine import DecisionEngine  # noqa: E402
from pipeline import prospective_diagnostics as diag  # noqa: E402
from pipeline import prospective_ledger as ledger  # noqa: E402
from pipeline import prospective_outcomes as po  # noqa: E402
from pipeline import prospective_tracking as tracking  # noqa: E402
from pipeline.service import run_direct_evaluation, run_market_scan  # noqa: E402
from tests.p6_18_fakes import FakeLoader, FakeSystem, FakeUniverse, make_financials, make_market  # noqa: E402
from utils import nyse_calendar as cal  # noqa: E402

T12 = [f"A{i}" for i in range(12)]
ENTRY = date(2026, 3, 2)          # Monday


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def scan(runs_dir, tickers=T12, capital=50_000):
    prices, volumes = make_market(tickers)
    return run_market_scan(capital=capital, runs_dir=runs_dir, universe_provider=FakeUniverse(tickers),
                           system=FakeSystem(FakeLoader(prices, volumes, make_financials(tickers)), capital=capital))


def frame(sessions, closes, opens=None, dividends=None, adj=None):
    closes = np.asarray(closes, dtype=float)
    opens = closes if opens is None else np.asarray(opens, dtype=float)
    df = pd.DataFrame({"open": opens, "high": np.maximum(opens, closes) * 1.001,
                       "low": np.minimum(opens, closes) * 0.999, "close": closes,
                       "adj_close": closes if adj is None else np.asarray(adj, dtype=float),
                       "volume": 1e6, "dividends": 0.0 if dividends is None else dividends, "splits": 0.0},
                      index=list(sessions))
    return df


def obs(ticker="X", entry=ENTRY, ref_close=100.0, hard_stop=95.0, horizon=30, cls="PORTFOLIO_TOP5", phase="PREMARKET"):
    ref = cal.previous_session(entry)
    return {"observation_id": f"R1:{ticker}", "run_id": "R1", "ticker": ticker, "observation_class": cls,
            "signal": {"entry_session": entry.isoformat(), "market_phase": phase},
            "reference_session": ref.isoformat(), "reference_close": ref_close, "hard_stop": hard_stop,
            "trailing_stop": hard_stop, "entry_1_weight": 0.08, "entry_2_weight": 0.12, "target_weight": 0.2,
            "horizon_days": horizon, "sector": "Energy", "recommendation_rank": 1,
            "recommendation_timestamp_utc": "2026-03-02T11:00:00+00:00"}


def market(entry=ENTRY, warm=40, after=60, growth=0.002, start=100.0):
    """Warm-up sessions before entry, steady geometric rise through entry (reference close = 100)."""
    before = []
    d = entry
    for _ in range(warm):
        d = cal.previous_session(d)
        before.append(d)
    before = before[::-1]
    sess = before + cal.sessions_between(entry, date(2026, 12, 31))[:after]
    k = np.arange(len(sess)) - (len(before) - 1)          # reference session -> 100
    return sess, start * (1 + growth) ** k


# ======================================================================= calendar
class TestCalendarAndEntryTiming(unittest.TestCase):
    def test_holidays_and_observance(self):
        self.assertFalse(cal.is_session(date(2026, 4, 3)))      # Good Friday
        self.assertFalse(cal.is_session(date(2026, 7, 3)))      # July 4 on Saturday -> Friday
        self.assertFalse(cal.is_session(date(2026, 6, 19)))     # Juneteenth
        self.assertTrue(cal.is_session(date(2021, 12, 31)))     # New Year on Saturday is NOT observed Friday
        self.assertTrue(cal.is_session(date(2027, 12, 31)))
        self.assertFalse(cal.is_session(date(2025, 1, 9)))      # national day of mourning
        self.assertFalse(cal.is_session(date(2026, 11, 7)))     # Saturday

    def test_early_closes(self):
        for d in (date(2026, 11, 27), date(2026, 12, 24), date(2025, 7, 3)):
            self.assertTrue(cal.is_early_close(d), d)
        self.assertFalse(cal.is_early_close(date(2026, 11, 25)))

    def test_signal_phases(self):
        c = cal.classify_signal
        self.assertEqual(c("2026-11-04T11:13:42Z")["market_phase"], "PREMARKET")      # 06:13 EST
        self.assertEqual(c("2026-11-04T11:13:42Z")["entry_session"], "2026-11-04")
        self.assertEqual(c("2026-11-04T15:00:00Z")["market_phase"], "REGULAR_SESSION")  # 10:00 EST
        self.assertEqual(c("2026-11-04T15:00:00Z")["entry_session"], "2026-11-05")
        self.assertEqual(c("2026-11-04T14:30:00Z")["market_phase"], "REGULAR_SESSION")  # exactly 09:30 ET
        self.assertEqual(c("2026-11-04T22:00:00Z")["market_phase"], "AFTER_HOURS")
        self.assertEqual(c("2026-11-04T22:00:00Z")["entry_session"], "2026-11-05")
        self.assertEqual(c("2026-11-07T15:00:00Z")["market_phase"], "NON_SESSION_DAY")  # Saturday
        self.assertEqual(c("2026-11-07T15:00:00Z")["entry_session"], "2026-11-09")
        self.assertEqual(c("2026-11-26T15:00:00Z")["entry_session"], "2026-11-27")      # Thanksgiving
        self.assertTrue(c("2026-11-26T15:00:00Z")["entry_session_early_close"])
        # early-close day: 14:00 ET is after the 13:00 close
        self.assertEqual(c("2026-11-27T19:00:00Z")["market_phase"], "AFTER_HOURS")
        self.assertEqual(c("2026-11-27T19:00:00Z")["entry_session"], "2026-11-30")
        # daylight saving: 13:00 UTC in July is 09:00 EDT (premarket); in November 08:00 EST
        self.assertEqual(c("2026-07-06T13:00:00Z")["market_phase"], "PREMARKET")
        self.assertEqual(c("2026-07-06T13:45:00Z")["market_phase"], "REGULAR_SESSION")

    def test_latest_completed_session_never_uses_in_progress_bar(self):
        self.assertEqual(cal.latest_completed_session(datetime(2026, 11, 4, 20, 0, tzinfo=timezone.utc)),
                         date(2026, 11, 3))   # 15:00 ET: today's bar incomplete
        self.assertEqual(cal.latest_completed_session(datetime(2026, 11, 4, 22, 30, tzinfo=timezone.utc)),
                         date(2026, 11, 4))
        prices = {"X": frame([date(2026, 11, 3), date(2026, 11, 4)], [10, 11])}
        self.assertEqual(list(tracking._trim(prices, date(2026, 11, 3))["X"].index), [date(2026, 11, 3)])

    def test_entry_uses_open_after_signal_not_prior_close(self):
        sess, closes = market()
        opens = closes * 1.01
        e = po.find_entry(frame(sess, closes, opens), ENTRY, date(2026, 4, 30))
        self.assertEqual(e["session"], ENTRY)
        self.assertAlmostEqual(e["price"], opens[sess.index(ENTRY)])
        self.assertNotAlmostEqual(e["price"], closes[sess.index(ENTRY) - 1])

    def test_missing_open_rolls_forward_and_is_recorded(self):
        sess, closes = market()
        df = frame(sess, closes).drop(index=[ENTRY])                  # halted / no bar
        e = po.find_entry(df, ENTRY, date(2026, 4, 30))
        self.assertEqual(e["session"], cal.next_session(ENTRY))
        self.assertEqual(e["delay_sessions"], 1)
        df2 = frame(sess, closes)
        df2.loc[ENTRY, "open"] = np.nan                              # bar without an open
        self.assertEqual(po.find_entry(df2, ENTRY, date(2026, 4, 30))["delay_sessions"], 1)

    def test_entry_unavailable_and_pending(self):
        sess, closes = market()
        df = frame(sess, closes)
        df = df[(df.index < ENTRY) | (df.index > cal.sessions_between(ENTRY, date(2026, 12, 1))[6])]
        self.assertEqual(po.find_entry(df, ENTRY, date(2026, 4, 30))["status"], "ENTRY_UNAVAILABLE")
        self.assertEqual(po.find_entry(df, ENTRY, cal.next_session(ENTRY))["status"], "PENDING_ENTRY")
        self.assertEqual(po.find_entry(frame(sess, closes), ENTRY, cal.previous_session(ENTRY))["status"],
                         "PENDING_ENTRY")


# ======================================================================= outcomes
class TestOutcomes(unittest.TestCase):
    def setUp(self):
        self.sess, self.closes = market()
        self.spy = frame(self.sess, 400 * (1.001 ** np.arange(len(self.sess))))

    def _measure(self, df, o=None, as_of=date(2026, 6, 30), lookup=None):
        return po.observation_outcome(o or obs(), {"X": df, "SPY": self.spy}, as_of, lookup)

    def test_horizon_review_without_same_day_scan_ends_at_frozen_horizon(self):
        out = self._measure(frame(self.sess, self.closes))
        horizon = next(s for s in cal.sessions_between(ENTRY, date(2026, 12, 1))
                       if np.busday_count(ENTRY, s) >= 30)                   # frozen weekday count
        self.assertEqual(out["outcome_state"], "COMPLETED_OUTCOME")
        self.assertEqual(out["exit"]["session"], horizon.isoformat())
        self.assertEqual(out["frozen_rule_path"]["horizon_review"], "UNAVAILABLE_NO_SAME_DAY_SCAN")
        p_in, p_out = self.closes[self.sess.index(ENTRY)], self.closes[self.sess.index(horizon)]
        self.assertAlmostEqual(out["returns"]["price_return"], p_out / p_in - 1, places=12)
        # entry #2: first close above EMA20 -> filled at the NEXT session open
        self.assertEqual(out["entry_2"]["session"], cal.next_session(ENTRY).isoformat())

    def test_benchmark_window_is_identical(self):
        out = self._measure(frame(self.sess, self.closes))
        r = out["returns"]
        x = self.spy
        bench = x.loc[date.fromisoformat(r["benchmark_window"]["exit"]), "close"] / x.loc[ENTRY, "open"] - 1
        self.assertEqual(r["benchmark_window"]["entry"], out["entry"]["session"])
        self.assertEqual(r["benchmark_window"]["exit"], out["exit"]["session"])
        self.assertAlmostEqual(r["benchmark_price_return"], bench, places=12)
        self.assertAlmostEqual(r["excess_vs_spy_price"], r["price_return"] - bench, places=12)
        self.assertEqual(r["benchmark_status"], "VALID")

    def test_negative_and_positive_review_alpha(self):
        out = self._measure(frame(self.sess, self.closes), lookup=lambda t, d: -0.5)
        self.assertEqual(out["exit"]["reason"], "30D_REVIEW_NEGATIVE_ALPHA")
        self.assertEqual(out["exit"]["type"], "OPEN")
        self.assertEqual(out["frozen_rule_path"]["horizon_review"], "EXIT_NEGATIVE_ALPHA")
        out = self._measure(frame(self.sess, self.closes), lookup=lambda t, d: 0.5)
        self.assertEqual(out["frozen_rule_path"]["horizon_review"], "HOLD_REVIEW_PASSED")
        self.assertEqual(out["exit"]["type"], "CLOSE")

    def test_hard_stop_signal_on_close_fills_next_open(self):
        closes = self.closes.copy()
        i = self.sess.index(ENTRY) + 3
        closes[i] = 94.0                                                # below the 95 hard stop
        opens = closes.copy()
        opens[i + 1] = 92.5                                             # gap down next morning
        out = self._measure(frame(self.sess, closes, opens))
        self.assertEqual(out["exit"]["reason"], "HARD_STOP")
        self.assertEqual(out["exit"]["session"], self.sess[i + 1].isoformat())
        self.assertAlmostEqual(out["exit"]["price"], 92.5)
        self.assertAlmostEqual(out["returns"]["price_return"], 92.5 / closes[self.sess.index(ENTRY)] - 1)

    def test_pending_when_window_not_finished_and_missing_is_not_zero(self):
        out = self._measure(frame(self.sess, self.closes), as_of=date(2026, 3, 13))
        self.assertEqual(out["outcome_state"], "PENDING_OUTCOME")
        self.assertIsNone(out["exit"])
        self.assertIsNone(out["diagnostic_fixed_horizons"]["horizons"]["30s"])

    def test_data_gap_is_incomplete(self):
        df = frame(self.sess, self.closes)
        gap = cal.sessions_between(date(2026, 3, 9), date(2026, 3, 20))
        out = self._measure(df.drop(index=gap))
        self.assertEqual(out["outcome_state"], "INCOMPLETE")
        self.assertIn("DATA_GAP", out["incomplete_reason"])

    def test_total_return_includes_dividend_price_return_does_not(self):
        closes = self.closes.copy()
        ex = self.sess.index(ENTRY) + 10
        adj = closes.copy()
        adj[:ex] = closes[:ex] * (1 - 2.0 / closes[ex - 1])          # provider back-adjustment
        div = np.zeros(len(closes))
        div[ex] = 2.0
        out = self._measure(frame(self.sess, closes, adj=adj, dividends=div))
        r = out["returns"]
        self.assertGreater(r["total_return"], r["price_return"])
        f_in = adj[self.sess.index(ENTRY)] / closes[self.sess.index(ENTRY)]
        p_out = float(out["exit"]["price"])
        self.assertAlmostEqual(r["total_return"], p_out / (closes[self.sess.index(ENTRY)] * f_in) - 1, places=10)
        self.assertIn(self.sess[ex].isoformat(), out["corporate_actions"]["dividends_in_window"])

    def test_split_adjusted_snapshot_gives_identical_outcome(self):
        """A later 2:1 split re-adjusts history; stops are rescaled, returns are unchanged."""
        closes = self.closes.copy()
        closes[self.sess.index(ENTRY) + 3] = 94.0
        a = self._measure(frame(self.sess, closes))
        b = self._measure(frame(self.sess, closes / 2))            # same history, post-split basis
        self.assertAlmostEqual(b["corporate_actions"]["stop_basis_factor"], 0.5)
        self.assertEqual(a["exit"]["reason"], b["exit"]["reason"])
        self.assertEqual(a["exit"]["session"], b["exit"]["session"])
        self.assertAlmostEqual(a["returns"]["price_return"], b["returns"]["price_return"], places=12)

    def test_cost_scenarios_are_hypothetical_and_exact(self):
        out = self._measure(frame(self.sess, self.closes))
        r, table = out["returns"], out["returns"]["cost_sensitivity"]
        self.assertAlmostEqual(table[0]["net_return"], r["price_return"], places=12)   # 0 bps == gross
        c = 25 / 10_000
        p_in, p_out = out["entry"]["price"], out["exit"]["price"]
        self.assertAlmostEqual(table[-1]["net_return"], (1 - c) * p_out / ((1 + c) * p_in) - 1, places=12)
        self.assertTrue(all("HYPOTHETICAL" in row["label"] for row in table))

    def test_watchlist_diagnostic_uses_horizon_only(self):
        out = self._measure(frame(self.sess, self.closes), o=obs(cls="WATCHLIST_DIAGNOSTIC", hard_stop=None))
        self.assertFalse(out["frozen_rule_path"]["applied"])
        self.assertEqual(out["exit"]["reason"], "HORIZON_REACHED")


# ======================================================================= ledger + integration
class TestLedgerIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = self.tmp.name
        self.track = str(Path(self.runs) / "_tracking")
        self.res = scan(self.runs)
        self.run_dir = Path(self.res["artifact_dir"])
        self.obs_file = Path(self.track) / "ledger" / "observations.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_eligible_scan_records_immutable_observations(self):
        self.assertEqual(self.res["recommendation_status"], "REAL RECOMMENDATION")
        self.assertEqual(self.res["forward_tracking"]["recorded_rows"], 5)
        recs = ledger.read_observations(self.track)
        runs = [r for r in recs if r["record_type"] == "RUN"]
        top5 = [r for r in recs if r.get("observation_class") == "PORTFOLIO_TOP5"]
        self.assertEqual(len(runs), 1)
        self.assertEqual([r["ticker"] for r in top5], [x["ticker"] for x in self.res["recommendations"]])
        o = top5[0]
        for field in ("observation_id", "recommendation_timestamp_utc", "signal", "model_version",
                      "frozen_config_sha256", "data_input_spec_version", "universe_tickers_sha256",
                      "model_rank_e_rank", "alpha_percentile", "factors_z", "factor_contributions", "sector",
                      "data_status", "fundamental_provenance", "source_observation", "source_retrieval",
                      "reference_close", "adv20", "target_weight", "horizon_days", "hard_stop"):
            self.assertIn(field, o)
        self.assertLess(o["factor_contributions"]["reconstruction_error"], 1e-9)
        self.assertEqual(o["data_input_spec_version"], "P6-19-final")
        self.assertEqual(runs[0]["capital"], 50_000)

    def test_duplicates_prevented_and_chain_verifies(self):
        before = sha(self.obs_file)
        ledger.record_run(self.run_dir, self.track)
        ledger.sync_runs(self.runs, self.track)
        self.assertEqual(sha(self.obs_file), before)
        v = ledger.verify(self.track, self.runs)
        self.assertTrue(v["ok"], v)
        self.assertEqual(v["runs"][self.res["run_id"]]["reconstruction"], "MATCH")

    def test_tampering_is_detected(self):
        lines = self.obs_file.read_text().splitlines()
        row = json.loads(lines[1])
        row["alpha"] = 99.0
        lines[1] = json.dumps(row)
        self.obs_file.write_text("\n".join(lines) + "\n")
        self.assertFalse(ledger.verify_chain(self.obs_file)["ok"])

    def test_changed_run_artifact_is_detected(self):
        p = self.run_dir / "validation_result.json"
        v = json.loads(p.read_text())
        v["market_regime"] = "BULL"
        p.write_text(json.dumps(v))
        res = ledger.verify(self.track, self.runs)
        self.assertFalse(res["ok"])
        self.assertIn("CHANGED", res["runs"][self.res["run_id"]]["artifacts"])

    def test_non_eligible_runs_are_never_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            prices, volumes = make_market(T12)
            loader = FakeLoader(prices, volumes, make_financials(T12))
            run_market_scan(capital=50_000, limit=6, runs_dir=tmp, universe_provider=FakeUniverse(T12),
                            system=FakeSystem(loader, capital=50_000))                       # bounded
            run_direct_evaluation(["A1"], capital=50_000, runs_dir=tmp, universe_provider=FakeUniverse(T12),
                                  system=FakeSystem(FakeLoader(prices, volumes, make_financials(T12)),
                                                    capital=50_000))                           # single ticker
            run_market_scan(capital=50_000, runs_dir=tmp, universe_provider=FakeUniverse(T12[:4]),
                            system=FakeSystem(FakeLoader(*make_market(T12[:4]), make_financials(T12[:4])),
                                              capital=50_000))                               # no valid portfolio
            out = ledger.sync_runs(tmp, str(Path(tmp) / "_tracking"))
            self.assertEqual(out["recorded_runs"], [])
            self.assertEqual(ledger.read_observations(str(Path(tmp) / "_tracking")), [])
            reasons = sorted(r for rs in out["skipped"].values() for r in rs)
            self.assertIn("NOT_FULL_UNIVERSE", reasons)
            self.assertIn("NOT_A_MARKET_SCAN", reasons)
            self.assertIn("NO_VALID_PORTFOLIO_RECOMMENDATION", reasons)

    def test_exclusion_and_correction_events_never_rewrite_originals(self):
        before = sha(self.obs_file)
        rid = self.res["run_id"]
        oid = f"{rid}:{self.res['recommendations'][0]['ticker']}"
        self.assertTrue(ledger.append_event("CORRECTION", {"observation_id": oid}, "provider restated close",
                                            tracking_dir=self.track, details={"field": "reference_close"}))
        self.assertTrue(ledger.append_event("EXCLUSION", {"run_id": rid}, "test invalidation", "DATA_INVALID",
                                            tracking_dir=self.track))
        self.assertFalse(ledger.append_event("EXCLUSION", {"run_id": rid}, "test invalidation", "DATA_INVALID",
                                             tracking_dir=self.track))       # idempotent
        self.assertEqual(sha(self.obs_file), before)
        o = next(r for r in ledger.read_observations(self.track) if r.get("observation_id") == oid)
        self.assertEqual(ledger.eligibility_cohort(o, ledger.exclusions_index(self.track))["cohort"],
                         ledger.DATA_INVALID)
        self.assertEqual(len(ledger.corrections_for(oid, self.track)), 1)
        with self.assertRaises(ValueError):
            ledger.append_event("EXCLUSION", {"run_id": rid}, "", "PRE_FIX", tracking_dir=self.track)

    def test_legacy_excluded_runs_file_is_honoured_and_preserved(self):
        legacy = Path(self.track) / "excluded_runs.json"
        legacy.write_text(json.dumps({self.res["run_id"]: "pre-fix inputs"}))
        before = sha(legacy)
        ledger.sync_runs(self.runs, self.track)
        ledger.sync_runs(self.runs, self.track)
        self.assertEqual(sha(legacy), before)
        events = [e for e in ledger.read_events(self.track) if e["kind"] == "EXCLUSION"]
        self.assertEqual(len(events), 1)
        o = next(r for r in ledger.read_observations(self.track) if r["record_type"] == "OBSERVATION")
        self.assertEqual(ledger.eligibility_cohort(o, ledger.exclusions_index(self.track))["cohort"],
                         ledger.PRE_FIX_EXCLUDED)

    def test_torn_final_line_is_ignored_not_repaired(self):
        with open(self.obs_file, "a") as fh:
            fh.write('{"record_type": "OBSERV')
        self.assertEqual(len(ledger.read_observations(self.track)), 11)  # 1 RUN + 5 TOP-5 + 5 watchlist


class TestUpdateSafetyAndPaperPortfolio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runs = self.tmp.name
        self.track = str(Path(self.runs) / "_tracking")
        self.res = scan(self.runs)
        self.obs = [r for r in ledger.read_observations(self.track) if r["record_type"] == "OBSERVATION"]
        self.entry = date.fromisoformat(self.obs[0]["signal"]["entry_session"])
        self.now = datetime.combine(self.entry, datetime.min.time()).replace(tzinfo=timezone.utc) + pd.Timedelta(days=120)

    def tearDown(self):
        self.tmp.cleanup()

    def fetcher(self, tickers, start, end):
        out = {}
        for i, t in enumerate(tickers):
            o = next((x for x in self.obs if x["ticker"] == t), None)
            sess = cal.sessions_between(start, end)
            ref = date.fromisoformat(o["reference_session"]) if o else sess[0]
            k = np.array([(s - ref).days for s in sess], dtype=float)
            base = (o["reference_close"] if o else 400.0)
            closes = base * (1 + 0.0005 * (i + 1)) ** (k / 1.4)
            out[t] = frame(sess, closes)
        return out

    def _update(self, **kw):
        return tracking.update(self.track, self.runs, fetcher=kw.pop("fetcher", self.fetcher), now=self.now, **kw)

    def test_update_never_changes_ledger_and_is_safe_to_rerun(self):
        obs_file = Path(self.track) / "ledger" / "observations.jsonl"
        before = sha(obs_file)
        first = self._update()
        self.assertIn(first["status"], ("COMPLETE", "PARTIAL"))
        self.assertEqual(sha(obs_file), before)
        calls = []

        def counting(*a):
            calls.append(a)
            return self.fetcher(*a)
        second = self._update(fetcher=counting)
        self.assertEqual(second["status"], "NO_CHANGE")
        self.assertTrue(second["snapshot_reused"])
        self.assertEqual(calls, [])                                   # no repeated download
        self.assertEqual(sha(obs_file), before)
        self.assertTrue(tracking.replay_update(tracking_dir=self.track, runs_dir=self.runs)["match"])
        self.assertTrue((Path(self.track) / "reports" / "latest.md").exists())

    def test_failed_or_interrupted_update_leaves_records_intact(self):
        obs_file = Path(self.track) / "ledger" / "observations.jsonl"
        before = sha(obs_file)

        def broken(*a):
            raise ConnectionError("provider down")
        res = self._update(fetcher=broken)
        self.assertEqual(res["status"], "FAILED")
        self.assertIsNone(tracking.latest_update(self.track))
        self.assertFalse((Path(self.track) / "outcomes").exists())
        with patch.object(tracking, "compute", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self._update()
        self.assertIsNone(tracking.latest_update(self.track))        # orphan snapshot never picked up
        self.assertEqual(sha(obs_file), before)
        good = self._update()
        self.assertIn(good["status"], ("COMPLETE", "PARTIAL"))

    def test_paper_portfolio_preserves_original_allocation(self):
        self._update()
        res = tracking.load_latest_result(self.track)
        p = next(x for x in res["paper_portfolios"] if x["run_id"] == self.res["run_id"])
        self.assertEqual([x["ticker"] for x in p["original_top5"]], [r["ticker"] for r in self.res["recommendations"]])
        self.assertEqual(p["capital"], 50_000)
        first = [f for f in p["fills"] if f["ticker"] == p["original_top5"][0]["ticker"]]
        target = 50_000 * p["original_top5"][0]["weight"]
        self.assertAlmostEqual(first[0]["notional"], target * 0.4)
        if len(first) > 1:
            self.assertAlmostEqual(first[1]["notional"], target * 0.6)
        self.assertIn("not an actual investor return", p["label"])
        # the original recommendation is unchanged after outcome updates
        self.assertTrue(ledger.verify(self.track, self.runs)["ok"])

    def test_official_statistics_only_include_valid_prospective(self):
        ledger.append_event("EXCLUSION", {"run_id": self.res["run_id"]}, "test", "PRE_FIX", tracking_dir=self.track)
        self._update()
        s = tracking.load_latest_result(self.track)["summary"]
        self.assertEqual(s["valid_observations"], 0)
        self.assertEqual(s["completed_observations"], 0)
        self.assertEqual(s["sample_status"], "NO_COMPLETED_OBSERVATIONS")

    def test_summary_flags_small_samples_and_never_annualises(self):
        self._update()
        res = tracking.load_latest_result(self.track)
        s = res["summary"]
        self.assertIn(s["sample_status"], ("INSUFFICIENT_SAMPLE", "NO_COMPLETED_OBSERVATIONS"))
        self.assertNotIn("annual", json.dumps(s).replace("No significance test is performed, no annualised", ""))
        self.assertIn("not actual investor returns", s["statistical_caution"])

    def test_offline_update_never_downloads(self):
        res = tracking.update(self.track, self.runs, fetcher=None, now=self.now, offline=True)
        self.assertEqual(res["status"], "OFFLINE_NO_CURRENT_SNAPSHOT")


class TestPaperPortfolioArithmetic(unittest.TestCase):
    def test_reconstruction_cash_and_spy(self):
        sess, closes = market()
        spy = frame(sess, 400 * (1.001 ** np.arange(len(sess))))
        prices, outcomes, top5 = {"SPY": spy}, {}, []
        for i, t in enumerate(["P", "Q", "R", "S", "T"]):
            prices[t] = frame(sess, closes * (1 + 0.01 * i))
            o = obs(ticker=t, ref_close=100.0 * (1 + 0.01 * i), hard_stop=50.0)
            outcomes[o["observation_id"]] = po.observation_outcome(o, prices, date(2026, 6, 30))
            top5.append({"ticker": t, "rank": i + 1, "weight": 0.2})
        run = {"run_id": "R1", "capital": 50_000.0, "top5": top5, "sector_exposure": {"Energy": 1.0}}
        p = po.paper_portfolio(run, outcomes, prices, date(2026, 6, 30))
        self.assertEqual(p["status"], "COMPLETED_OUTCOME")
        expected = 50_000.0
        for t in "PQRST":
            o = outcomes[f"R1:{t}"]
            for leg, frac in ((o["entry"], 0.4), (o["entry_2"], 0.6)):
                expected += 10_000 * frac * (o["exit"]["price"] / leg["price"] - 1)
        self.assertAlmostEqual(p["value_end_price_basis"], expected, places=6)
        self.assertAlmostEqual(p["cash_end"], expected, places=6)
        self.assertEqual(p["open_positions"], [])
        self.assertIsNotNone(p["spy_return_same_window"])


# ======================================================================= diagnostics
class TestDiagnostics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.res = scan(self.tmp.name)
        self.run_dir = Path(self.res["artifact_dir"])
        self.track = str(Path(self.tmp.name) / "_tracking")

    def tearDown(self):
        self.tmp.cleanup()

    def test_diagnostics_are_read_only_and_reconstruct_alpha(self):
        before = {f: sha(self.run_dir / f) for f in ledger.ARTIFACT_FILES}
        run = next(r for r in ledger.read_observations(self.track) if r["record_type"] == "RUN")
        d = diag.run_diagnostics(run, self.tmp.name)
        self.assertTrue(d["available"])
        for t, c in d["top5_contributions"].items():
            self.assertLess(c["reconstruction_error"], 1e-9, t)
            self.assertIn("HYPOTHETICAL", c["factor_ablation"]["label"])
        loo = d["leave_one_out"]
        self.assertIn("HYPOTHETICAL", loo["label"])
        top = [x["ticker"] for x in self.res["recommendations"]]
        for t, v in loo["views"].items():
            self.assertNotIn(t, v["top5_without"])
        self.assertEqual({f: sha(self.run_dir / f) for f in ledger.ARTIFACT_FILES}, before)
        from pipeline.replay import replay
        self.assertTrue(replay(self.run_dir)["match"])
        self.assertEqual([x["ticker"] for x in self.res["recommendations"]], top)

    def test_extreme_factor_and_dominance_flags(self):
        flow = {f"T{i}": {"alpha": 0.1 * i, "model_rank_e_rank": i + 1,
                          "factors": {"quality": 0.1 * i, "momentum": 0.0, "value": 0.0, "low_volatility": 0.0}}
                for i in range(10)}
        flow["T0"]["factors"]["quality"] = 20.0
        w = {"momentum": 0.35, "quality": 0.25, "value": 0.2, "low_volatility": 0.2}
        flow["T0"]["alpha"] = 0.25 * 20.0
        ex = diag.factor_extremes(flow)
        self.assertEqual(ex["quality"]["count_abs_z_gt_10"], 1)
        self.assertEqual(ex["quality"]["max"][0], "T0")
        c = diag.contribution_view(flow, w, ["T0"])["T0"]
        self.assertTrue(c["single_factor_dominates"])
        self.assertEqual(c["dominant_factor"], "quality")
        self.assertGreater(c["factor_ablation"]["views"]["quality"]["alpha_rank_without_factor"], 1)

    def test_sector_exposure_reported_frozen_cap_unchanged(self):
        sv = diag.sector_view({}, {"Healthcare": 0.6, "Technology": 0.4})
        self.assertEqual(sv["top5_over_40pct"], {"Healthcare": 0.6})
        self.assertIn("Technology only", sv["frozen_cap_scope"])
        # frozen engine behaviour is preserved: a non-Technology sector is not capped
        cands = [{"security_id": f"s{i}", "ticker": f"H{i}", "close": 100.0, "volume": 1e6, "alpha": 1 - i / 10,
                  "atr": 1.0, "ema20": 99.0, "entry_readiness": 1.0, "alpha_percentile": 1 - i / 10,
                  "sector": "Healthcare", "data_status": "REAL", "price_status": "REAL", "volume_status": "REAL",
                  "fundamental_status": "REAL"} for i in range(6)]
        dec = DecisionEngine().evaluate_portfolio(datetime(2026, 1, 2), 50_000, "SIDEWAYS", cands)
        self.assertEqual(len(dec.top5), 5)
        self.assertEqual(dec.sector_exposure, {"Healthcare": 1.0})

    def test_ranking_stability(self):
        a = {"run_id": "A", "recommendation_timestamp_utc": "2026-01-01T00:00:00+00:00",
             "top5": [{"ticker": t} for t in "ABCDE"], "ranked_model_rank_e": {t: i for i, t in enumerate("ABCDEFG")}}
        b = {"run_id": "B", "recommendation_timestamp_utc": "2026-01-02T00:00:00+00:00",
             "top5": [{"ticker": t} for t in "ABCDF"], "ranked_model_rank_e": {t: i for i, t in enumerate("ABCDFEG")}}
        s = diag.ranking_stability([b, a], {"A": "VALID_PROSPECTIVE", "B": "VALID_PROSPECTIVE"})[0]
        self.assertEqual((s["from"], s["to"]), ("A", "B"))
        self.assertAlmostEqual(s["top5_jaccard"], 4 / 6)
        self.assertGreater(s["spearman_model_rank_e"], 0.8)


class TestIndicatorParity(unittest.TestCase):
    def test_tracking_indicators_match_canonical_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            res = scan(tmp)
            flow = json.loads((Path(res["artifact_dir"]) / "candidate_flow.json").read_text())["candidates"]
        prices, _ = make_market(T12)
        t = res["recommendations"][0]["ticker"]
        atr, ema20 = po.indicators_until(prices[t])
        self.assertAlmostEqual(atr, flow[t]["atr"], places=9)
        self.assertAlmostEqual(ema20, flow[t]["ema20"], places=9)


class TestNoProductionSideEffects(unittest.TestCase):
    def test_frozen_sources_untouched_and_no_broker_code(self):
        root = Path(__file__).resolve().parents[1]
        pin = json.loads((root / "tests/fixtures/frozen_source_sha256_p6_19.json").read_text())["sha256"]
        for f, h in pin.items():
            self.assertEqual(sha(root / f), h, f)
        for mod in ("prospective_ledger", "prospective_outcomes", "prospective_tracking", "prospective_diagnostics"):
            src = (root / "pipeline" / f"{mod}.py").read_text().lower()
            for word in ("place_order", "submit_order", "broker", "alpaca", "ibkr", "oauth"):
                self.assertNotIn(word, src, f"{mod}: {word}")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(os.getenv("QPP_PROVIDER_TESTS") == "1", "live provider test (set QPP_PROVIDER_TESTS=1)")
class TestLiveProviderSmoke(unittest.TestCase):
    """Format check of the public price fetcher on a past window. Not an observation; nothing is recorded."""

    def test_fetcher_returns_completed_sessions_with_raw_and_adjusted_prices(self):
        prices = tracking.yfinance_fetcher(["AAPL", "SPY"], date(2026, 9, 1), date(2026, 10, 30))
        for t in ("AAPL", "SPY"):
            df = prices[t]
            self.assertTrue({"open", "high", "low", "close", "adj_close", "volume", "dividends", "splits"} <= set(df.columns))
            self.assertTrue(all(cal.is_session(d) for d in df.index), t)
            self.assertEqual(list(df.index), cal.sessions_between(date(2026, 9, 1), date(2026, 10, 30)))
            self.assertTrue((df["open"] > 0).all())
