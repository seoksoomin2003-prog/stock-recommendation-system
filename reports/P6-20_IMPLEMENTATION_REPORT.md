# P6-20 Implementation Report: Prospective Performance Validation and Paper Portfolio Tracking

Date: 2026-11-04 · Project root: `~/Developer/quant-stock-engine` (verified)

**Final status: READY FOR PROSPECTIVE PERFORMANCE OBSERVATION.**

The tracking system is implemented, tested, live-validated on a bounded update, and reproducible.
**There is not yet any performance evidence.** The only valid recommendation was produced on 2026-11-04
before the US open. Its paper entry is that day's open, which had not happened at report time, so all five
observations are `PENDING_OUTCOME`. Nothing here claims profitability, alpha or institutional validation.
Paper results are not actual investor returns.

---

## 1. What was implemented

| Area | Implementation | Files |
|---|---|---|
| Immutable ledger | Append-only JSONL with a sha256 hash chain, file lock and fsync. RUN and OBSERVATION records are built **only from run artifacts**, with artifact hashes stored. Duplicates are keyed. A torn last line is ignored, never repaired. Recording happens automatically after `RUN_COMPLETED`, with back-fill and recovery via `sync_runs`. | `pipeline/prospective_ledger.py`, `pipeline/service.py` (hook) |
| Events | EXCLUSION (PRE_FIX / DATA_INVALID), CORRECTION and NOTE events are linked to original records and hash-chained. The P6-19 `excluded_runs.json` is preserved and mirrored idempotently. | `pipeline/prospective_ledger.py` |
| Cohorts | Eligibility: VALID_PROSPECTIVE / PRE_FIX_EXCLUDED / DATA_INVALID. Outcome state: PENDING_OUTCOME / COMPLETED_OUTCOME / INCOMPLETE. Official statistics come only from VALID × TOP-5 × COMPLETED. | same |
| Market calendar | NYSE holidays with the correct observance rules (including no Friday observance when New Year's Day is a Saturday), early closes and special closures; signal-phase classification | `utils/nyse_calendar.py` |
| Entry policy | First regular-session open strictly after the recommendation timestamp. Unusable opens roll forward (up to 5 sessions, delay recorded), then INCOMPLETE. Only completed bars are used. | `pipeline/prospective_outcomes.py` |
| Outcomes | The frozen exit hierarchy is applied by calling the **unmodified** `DecisionEngine.evaluate_existing_position` on each close, with next-open fills. The window ends at the first exit fill or at the frozen 30-weekday review. Price and total return use one snapshot, with stops rescaled across splits. SPY is measured over the identical window. MFE, MAE, drawdown, 5/10/20/30-session diagnostics and hypothetical cost scenarios are included. | same |
| Paper portfolio | Original TOP-5, weights and capital; staged 40/60 fills; cash; daily mark-to-close; dividends as cash; SPY over the same window; drawdown. No rebalancing or substitution. | same |
| Diagnostics | Factor extremes, exact contributions with dominance, hypothetical factor ablation, hypothetical portfolio-stage leave-one-out, sector view, hard-stop distance, ranking stability. All read-only. | `pipeline/prospective_diagnostics.py`, `pipeline/replay.py` |
| Updates and reporting | Snapshot caching and reuse, atomic writes, a hash-chained update log written last, `NO_CHANGE` de-duplication, a FAILED entry on errors, offline replay, and Markdown and HTML reports | `pipeline/prospective_tracking.py` |
| CLI | `app.py tracking status \| update \| report \| exclusions \| verify \| replay`; `track` is an alias for update + report | `app.py` |
| Manifest | New runs record `data_input_spec_version`. Older runs have it inferred from provenance markers, with the basis stated. | `pipeline/run_recorder.py`, `data/loader.py` (constant only) |

## 2. Independently verified

The baseline is in `reports/P6-20_BASELINE_VERIFICATION.md`.

**Confirmed:**

- Project path.
- Frozen hashes.
- The latest run replays (`match: true`).
- The two pre-fix exclusions and their reasons.
- The single canonical pipeline.
- Artifacts are sufficient for reconstruction.

**Found:**

1. **P6-18 run `e16f62` was not excluded.** Its TOP-5 is identical to pre-fix run 9072c9, and it used the
   removed $10M default capital. It is now recorded and excluded through an appended PRE_FIX event.
2. **The P6-19 tracker measured from a pre-recommendation close**, a look-ahead-prone entry. It is
   superseded; its files are preserved unchanged (sha256 verified).
3. **`utils/market_calendar.py` mishandles New Year's Day on a Saturday** (next occurrence 2027-12-31).
   Documented and not changed (production freshness path).

## 3. Frozen-core hash comparison

| File | Baseline (P6-19 pin) | After P6-20 |
|---|---|---|
| core/factor_engine.py | d84820f82eda… | identical |
| core/scoring_engine.py | 0f42f8401b26… | identical |
| core/ranking_engine.py | 2b354792de5d… | identical |
| core/decision_engine.py | 074f5180426e… | identical |
| contracts/decision.py | 3339af551c0d… | identical |

Full hashes before and after are in `reports/P6-20_TEST_RESULTS.json` → `frozen_core`. The parity tests,
`TestFrozenSourcePinned` and `TestNoProductionSideEffects` pass. No P6-20 change touches scoring, ranking,
eligibility, sizing or thresholds.

- **Re-used, not changed:** the frozen exit logic is called, not reimplemented.
- **Code moved, logic unchanged:** `scripts/replay_run_decision.py` now wraps the importable
  `pipeline/replay.py`. The decision logic is identical, and the latest run still replays with
  `match: true`.

## 4. Ledger state (live, after the bounded update `20261104T114204Z_db6d7d`)

| Run | Data-input spec (basis) | Cohort | TOP-5 observations | Watchlist (diagnostic) |
|---|---|---|---|---|
| `20261104T071145Z_market_scan_e16f62` (P6-18) | pre-P6-19-fix (inferred) | PRE_FIX_EXCLUDED (P6-20 event) | 5 | 5 |
| `20261104T105453Z_market_scan_9072c9` | pre-P6-19-fix (inferred) | PRE_FIX_EXCLUDED (P6-19 file) | 5 | 5 |
| `20261104T110528Z_market_scan_4f4b37` | P6-19-intermediate (inferred) | PRE_FIX_EXCLUDED (P6-19 file) | 5 | 5 |
| `20261104T111004Z_market_scan_953827` | P6-19-final (inferred) | **VALID_PROSPECTIVE** | **5** (CL, SNDK, MU, AES, CHTR) | 5 |

| Count | Value |
|---|---|
| Valid prospective observations (TOP-5) | **5** |
| Excluded observations (TOP-5) | **15** (all PRE_FIX) |
| Pending observations (TOP-5) | **20** (5 valid, 15 excluded) |
| Completed observations | **0** |
| Incomplete | 0 |
| Ledger hash chains | observations: 44 rows OK; events: 3 rows OK |
| Reconstruction (all 4 runs) | artifacts UNCHANGED, records MATCH |

All four runs completed premarket (06:13 ET or earlier), so their planned entry is **the 2026-11-04 open**.
The update ran at 11:42 UTC (06:42 ET), when the latest completed session was 2026-11-03, so every
observation is correctly `PENDING_ENTRY`.

- **When entries become observable:** in the first update after 17:00 ET on 2026-11-04 (07:00 KST on
  11-05).
- **When the window ends:** at the first frozen exit, or at the frozen 30-weekday review around
  2026-12-16.

## 5. Paper portfolio reconstruction and benchmark validity

- **Reconstruction: yes.** Every recorded run has a paper portfolio built from its original TOP-5, its
  weights (20% each) and its capital ($50,000 for valid run 953827). The arithmetic is tested exactly:
  cash, staged fills and final value. The live portfolios are currently `PENDING_OUTCOME` at $50,000 cash.
- **Benchmark: valid by construction and tested.** SPY uses the same entry session open and the same exit
  session and price type. It was present in the live snapshot. It is labelled benchmark-relative, not alpha.

## 6. Diagnostics of the valid run (read-only)

These come from `tracking/reports/latest.md`.

**Single-factor dominance.** Every TOP-5 alpha is dominated by one factor:

| Ticker | Dominant factor | Share of absolute contribution | z-score | Hypothetical alpha rank without that factor |
|---|---|---|---|---|
| CL | quality | 94% | 20.3 | 302 |
| SNDK | momentum | 83% | 11.2 | 347 |
| MU | momentum | 82% | n/a | 264 |
| AES | value | 58% | n/a | 52 |
| CHTR | value | 69% | n/a | 426 |

This is the frozen model's behaviour without winsorisation. It is reported and not changed.

**Hard-stop distance.** AES sits **0.35%** below its close, because the canonical ATR is a close-only proxy
and AES has very low recent volatility. CL is at 3.4%, and SNDK at 9.7%.

**Leave-one-out (hypothetical).** Removing any single TOP-5 name brings in ALL (Allstate).

**Sector.** TOP-5 exposure: Technology 40%, other sectors 20% each, nothing above 40%. The ranked top 10
holds 4 Financial Services names.

**Ranking stability.** Spearman correlation between consecutive scans is 0.897–1.000. TOP-5 Jaccard between
the pre-fix and post-fix runs is 0.43, which reflects the P6-19 input fixes, not market change.

## 7. Sector-cap contract review

See `reports/P6-20_SECTOR_CAP_REVIEW.md`.

- **The approved rule is Technology-only.** The P6-11B approval matrix records "Sector Cap: 40%
  Technology, Approved", and the implementation matches it.
- **The configuration comment suggests a per-sector cap,** but nothing on the canonical route uses it.
- **The cap has never bound in any recorded run.**
- **Changing it requires unfreezing the rule.** The options are documented. The behaviour is unchanged,
  and your approval is needed before any change, with P6-21 suggested.

## 8. Tests

`reports/P6-20_TEST_RESULTS.json`; JUnit XML in `reports/P6-20_pytest_junit.xml`.

| Collected | Passed | Failed | Errors | Skipped | Strict xfail | Deselected | Collection errors |
|---|---|---|---|---|---|---|---|
| 817 | 806 | 0 | 0 | 6 | 5 | 0 | 0 |

- **New:** `tests/test_p6_20_prospective_tracking.py` has 38 deterministic tests and 1 opt-in live test.
- **Deterministic coverage:**
  - immutability and tamper detection;
  - duplicate prevention;
  - artifact-change detection and reconstruction;
  - non-eligible runs never recorded (bounded, single-ticker, no valid portfolio);
  - exclusion and correction events leave originals unchanged;
  - legacy file honoured and unchanged;
  - torn-line tolerance;
  - holidays, observance and early closes;
  - premarket, regular, after-hours, weekend, holiday and DST timing;
  - in-progress bars excluded;
  - no pre-signal price;
  - halts and missing opens;
  - entry unavailable or pending;
  - hard stop with next-open gap fill;
  - entry #2;
  - horizon review (unavailable, negative and positive alpha);
  - data gaps;
  - dividends (total return) and split invariance;
  - benchmark alignment;
  - cost formula;
  - watchlist horizon;
  - rerun safety without re-download;
  - failed and interrupted updates;
  - offline mode;
  - paper allocation and exact arithmetic;
  - official-scope filtering;
  - small-sample flags and no annualisation;
  - diagnostics read-only, with exact contributions, extremes and dominance;
  - sector reporting with the frozen behaviour preserved;
  - ranking stability;
  - indicator parity with the canonical pipeline;
  - frozen hashes and no broker code.
- **Opt-in live test:** a fetcher format smoke test on 2026-09-01..10-30 (AAPL, SPY). It was run once with
  `QPP_PROVIDER_TESTS=1` and passed; its sessions match the calendar exactly.
- **Skipped (6):** all opt-in live tests (5 from P6-19, 1 new).
- **Strict xfail (5):** unchanged from P6-19.
- **Isolation:** the suite runs offline in the sandbox. Production data and the ledger were verified after
  the run (chains OK; the P6-19 tracking files are unchanged).
- **Disclosure:** the first P6-20 suite run wrote its JUnit XML to the P6-19 file name, overwriting the raw
  P6-19 XML. The P6-19 summary `P6-19_TEST_RESULTS.json` is intact. The file was renamed to
  `P6-20_pytest_junit.xml`, and that name is now allow-listed in `tests/conftest.py`.

## 9. Operational instructions

All commands run from `~/Developer/quant-stock-engine`:

```bash
.venv/bin/python app.py scan --capital 50000            # before 09:30 ET on a trading day (23:30 KST winter)
.venv/bin/python app.py tracking update                 # after 17:00 ET (07:00 KST next morning, winter)
.venv/bin/python app.py tracking report --open          # tracking/reports/latest.html
.venv/bin/python app.py tracking status
.venv/bin/python app.py tracking verify                 # hash chains, artifacts, reconstruction, replay
.venv/bin/python app.py tracking exclusions             # list; --add RUN_ID --category DATA_INVALID --reason "..."
.venv/bin/python app.py tracking replay [UPDATE_ID]     # offline recompute from the stored snapshot
```

- Updates are safe to rerun. The same completed session reuses the stored snapshot, with no download.
- A failed update changes nothing.
- Do not delete `runs/<id>/` folders of recorded runs, `tracking/`, or `data/`.

## 10. Remaining limitations

- **No completed observations yet.** Meaningful evidence needs at least 30 completed valid observations
  from many independent scan dates, which means months of daily premarket scans. Observations from the
  same or overlapping dates are not independent.
- **Daily bars only.** Intraday stop triggers are approximated by close-based signals filled at the next
  open, as the frozen rules evaluate closes. Regular-session signals wait for the next open.
- **The frozen 30-day review needs a same-day valid scan's alpha.** Without one, the window ends at the
  review close, flagged `UNAVAILABLE_NO_SAME_DAY_SCAN`. This is a measurement convention, not a rule.
- **Yahoo is a best-effort source.** Its adjusted history can change retroactively. Each update stores its
  own snapshot and hash; the original records are never affected.
- **Inferred spec versions.** Data-input spec versions for the four pre-P6-20 runs are inferred from
  provenance markers (basis recorded); new runs record them in the manifest.
- **No dividend reinvestment in the paper portfolio** (dividends are held as cash). No observed spread data
  exists; cost scenarios are hypothetical.
- **Not visually verified.** The HTML report was not checked in a browser here: the preview pane cannot
  render local files. The Markdown version was checked.
- **Open from P6-19:** NewsAPI key rotation (user action), the sector-cap decision (user, future phase) and
  the freshness-calendar New Year rule (before 2027-12-31).

## Final status

**READY FOR PROSPECTIVE PERFORMANCE OBSERVATION.** Profitability is not established. The system now records
what the frozen model recommended and will measure what happens next, without changing the model.
