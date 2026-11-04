# P6-20 Baseline Verification (P6-19 state)

The evidence was captured on 2026-11-04 at about 11:28 UTC, **before** any P6-20 code change. This
document was written up afterwards from those captured results. Nothing in `runs/` was modified.

| # | Check | Result | Evidence |
|---|---|---|---|
| 1 | Project location | `/Users/soominseok/Developer/quant-stock-engine` exists and is the active project (not iCloud) | `pwd`, `app.py doctor` (P6-19) |
| 2 | Frozen core unchanged | All five files match `tests/fixtures/frozen_source_sha256_p6_19.json`: `core/factor_engine.py` d84820f8…, `core/scoring_engine.py` 0f42f840…, `core/ranking_engine.py` 2b354792…, `core/decision_engine.py` 074f5180…, `contracts/decision.py` 3339af55… | sha256 recomputed at baseline |
| 3 | Latest production run replays | `20261104T111004Z_market_scan_953827`: status, TOP-5 tickers, weights and shares reproduced by the unmodified `DecisionEngine` (`match: true`) | `scripts/replay_run_decision.py` |
| 4 | Pre-fix runs excluded | `tracking/excluded_runs.json` lists `…105453Z_market_scan_9072c9` and `…110528Z_market_scan_4f4b37`, with reasons. The P6-19 tracker excluded 10 rows. | file content, `app.py track` |
| 5 | Exclusion reasons preserved | Both reasons present verbatim | file content |
| 6 | Valid vs pre-fix distinguishable | Yes, by run ID. **Gap found:** P6-18 full run `…071145Z_market_scan_e16f62` (TOP-5 identical to the pre-fix 9072c9, and $10,000,000 default capital) was *not* excluded, because it was never in the P6-19 ledger. P6-20 records it and appends a `PRE_FIX` exclusion event. | `runs/…e16f62/validation_result.json` |
| 7 | One canonical pipeline | `pipeline/service.py` routes scan and evaluate through `pipeline.canonical.CanonicalPipeline`. Each manifest records `"pipeline": "pipeline.canonical.CanonicalPipeline"`. | source, `run_manifest.json` |
| 8 | Artifacts sufficient to reconstruct | `candidate_flow.json` contains every candidate's inputs to the frozen decision stage. `execution_status.json` holds the `RUN_COMPLETED` timestamp (the recommendation timestamp). `run_manifest.json` holds frozen settings, hashes and capital. | artifact inspection |

## Pre-existing tracking state (P6-19)

- `tracking/recommendation_ledger.jsonl`: schema 1, 15 rows from 3 runs. It is mutable-by-design JSONL with no
  hash chain and no entry-price policy. It used the scan's reference close as the "entry" price, and that
  close predates the recommendation.
- `tracking/outcomes.json` and `tracking/excluded_runs.json`.

Both P6-19 files are preserved unchanged. A copy is in `~/Developer/qse-backups/tracking_before_p6_20/`.
P6-20 supersedes the schema-1 ledger with the immutable schema-2 ledger, and stops writing schema-1 rows.

## Other findings at baseline

- **Calendar defect in `utils/market_calendar.py`** (freshness gate): New Year's Day falling on a Saturday is
  mapped to the preceding Friday, a day on which NYSE is open. The next occurrence is 2027-12-31. Early
  closes are not modelled (they are not needed for the daily-bar freshness check). It is not changed in
  P6-20, because it lies on the production freshness path; it is documented here. The new tracking calendar
  `utils/nyse_calendar.py` implements the correct rule and is tested.
- **P6-19 forward tracker look-ahead risk**: it measured returns from the reference close of the session
  *before* the recommendation, i.e. a price no longer available when the recommendation was made. P6-20
  replaces this with an explicit entry policy (first open after the recommendation timestamp).
- **Indicator inputs**: the canonical pipeline's ATR is a close-only proxy (`mean(|Δclose/close|, 14) × close`).
  For low-volatility names this sets the frozen 2×ATR hard stop very close to the price (AES: 0.35%).
  This is an existing input definition and is not changed; it is reported in the diagnostics.
