# P6-20 Prospective Tracking Specification

Version: P6-20 (ledger schema 2) · Code: `utils/nyse_calendar.py`, `pipeline/prospective_ledger.py`,
`pipeline/prospective_outcomes.py`, `pipeline/prospective_diagnostics.py`, `pipeline/prospective_tracking.py`

The purpose is to keep an honest, immutable record of what the frozen P6-11B engine recommended and what
happened afterwards. Nothing here changes scoring, ranking, eligibility, sizing or any frozen rule.
Paper results are **not** actual investor returns. The application does not know your real trades.

---

## 1. Recommendation ledger (immutable)

| Item | Rule |
|---|---|
| Files | `tracking/ledger/observations.jsonl` (RUN and OBSERVATION records), `tracking/ledger/events.jsonl` (EXCLUSION, CORRECTION and NOTE events) |
| Integrity | Each line contains `prev_hash` and `record_hash = sha256(canonical JSON of the record including prev_hash)`, forming a hash chain. `app.py tracking verify` recomputes the chain. |
| Append-only | Records are only appended, under an exclusive file lock with `fsync`. No code path edits, re-ranks or deletes a record. A torn final line (an interrupted append) is ignored and never "repaired". |
| Duplicates | Keys `RUN:<run_id>` and `OBS:<run_id>:<ticker>`. Re-recording a run writes nothing. |
| What is recorded | Every run that is a **completed, full-universe Market Scan with a REAL RECOMMENDATION and 5 positions**. Bounded scans, Direct Ticker Evaluations, failed or interrupted runs and DATA-INCOMPLETE runs are never recorded. |
| When | Automatically after a scan completes (`pipeline/service.py`, after `RUN_COMPLETED`). `tracking update` / `tracking status` also back-fill any eligible run missing from the ledger (recovery after interruptions), labelled `record_source = backfill_from_run_artifacts`. |
| Source | Records are built **only from the run's own artifacts** (`runs/<id>/`), never from today's provider data. The sha256 of `run_manifest.json`, `execution_status.json`, `validation_result.json`, `candidate_flow.json` and `provider_summary.json` is stored, so reconstruction can be verified later. |
| RUN record | run ID, recommendation timestamp (= `RUN_COMPLETED` time, UTC), exchange timezone, market phase and planned entry session, model and strategy version, frozen config sha256 and frozen source sha256, data-input spec version (from the manifest, or inferred from provenance markers for older runs, with the basis stated), universe source / retrieval time / count / sha256 of the ticker list and the ticker list, regime, capital and its source, recommendation status, TOP-5 with weights, watchlist, sector exposure and warnings, cash, funnel, excluded candidates with reasons, alpha and MODEL_RANK_E rank of every ranked candidate |
| OBSERVATION record | one per TOP-5 pick (`PORTFOLIO_TOP5`) and per watchlist name (`WATCHLIST_DIAGNOSTIC`, never part of portfolio statistics). Fields: ticker, name, sector and source, recommendation / watchlist rank, MODEL_RANK_E rank and score, alpha and percentile, factor z-scores, exact factor contributions (frozen weights renormalised over available factors; the reconstruction error is stored), fundamentals and provenance, data statuses, source observation times (last bar, ADV20 window, SEC period), source retrieval times, reference close and its basis, ADV20, ATR, EMA20, liquidity, target weight / notional / shares, entry #1 and #2 weights, hard and trailing stop, horizon, final status, reasons |
| Corrections | `append_event("CORRECTION", {"observation_id": …}, reason, details=…)`. The original record is kept, and outcomes list the corrections next to it. |
| Exclusions | `app.py tracking exclusions --add RUN_ID --category PRE_FIX\|DATA_INVALID --reason "…"`. The P6-19 file `tracking/excluded_runs.json` is preserved unchanged, mirrored idempotently into the event log, and always honoured. |

## 2. Cohorts

| Cohort | Policy |
|---|---|
| `VALID_PROSPECTIVE` | Recorded eligible run with no exclusion event. **Only this cohort enters official statistics.** |
| `PRE_FIX_EXCLUDED` | Exclusion event category `PRE_FIX` (produced before an input-data correction). Kept, reported, never counted. |
| `DATA_INVALID` | Exclusion event category `DATA_INVALID` (found invalid after recording). Kept, reported, never counted. |
| `PENDING_OUTCOME` | The measurement window is not finished, or the entry reference is not yet observable |
| `COMPLETED_OUTCOME` | The window ended and its exit price was observed |
| `INCOMPLETE` | No valid entry open within 5 sessions (`ENTRY_UNAVAILABLE`), or a gap of 5 or more sessions with no bar while SPY has bars (`DATA_GAP`) |

The first three describe **eligibility**; the last three describe **outcome state**. Official statistics
use `VALID_PROSPECTIVE × PORTFOLIO_TOP5 × COMPLETED_OUTCOME`.

## 3. Entry-price policy (no look-ahead)

- **Recommendation timestamp:** the run's `RUN_COMPLETED` checkpoint time (UTC), when the recommendation
  became available. It is converted to `America/New_York`, so daylight saving time is handled by the
  timezone database.
- **Calendar:** NYSE regular holidays with NYSE observance rules, including no Friday observance when New
  Year's Day is a Saturday. It also covers early closes at 13:00 ET (July 3 Mon–Thu, the day after
  Thanksgiving, Christmas Eve on a weekday) and known special closures.

| Signal time (ET) | Phase | Entry reference |
|---|---|---|
| Session day, before 09:30 | `PREMARKET` | that session's regular **open** |
| 09:30 ≤ t < close (16:00, or 13:00 on an early close) | `REGULAR_SESSION` | **next** session's open |
| At or after the close | `AFTER_HOURS` | next session's open |
| Weekend or holiday | `NON_SESSION_DAY` | next session's open |

- **Regular-session signals:** daily bars do not reveal the price at the signal time. The next open is
  the first observable price that involves no look-ahead.
- **Unusable open:** a missing open, a zero open, zero volume, or a halt with no bar rolls forward to the
  next session's open, up to 5 sessions. The delay is recorded as `delay_sessions`. After that the
  observation is `INCOMPLETE / ENTRY_UNAVAILABLE`. The engine never substitutes a price.
- **Completed bars only:** bars are used only up to the latest completed session (17:00 ET boundary). An
  in-progress daily bar is trimmed and never used.
- **No pre-signal price:** a closing price from before the recommendation is never used as the entry.

## 4. Price basis and corporate actions

- **Source:** Yahoo daily bars, requested with `auto_adjust=False, actions=True`. Open, high, low and close
  are split-adjusted but not dividend-adjusted. `Adj Close`, dividends and splits are also downloaded.
- **Price return:** split-adjusted open/close, both legs taken from the **same snapshot**.
- **Total return:** each leg is multiplied by that session's provider dividend factor `adj_close / close`,
  so dividends paid inside the window are included. Bases are never mixed within one return.
- **Stops:** the frozen stops were set in the scan's price basis (`auto_adjust=True` close). They are
  rescaled by `snapshot close(reference session) / recorded reference close`. A split after the
  recommendation therefore re-adjusts the stops and the prices consistently; this is tested.
- **What is never touched:** the original snapshot (reference close and stops in the ledger).
- **What is recorded:** splits and dividends seen in the window, per outcome.

## 5. Primary measurement: frozen exit assumptions

- **Entry #1:** the frozen 40% of the target position, filled at the entry reference open.
- **Daily evaluation:** each later session close is evaluated by the **unmodified**
  `DecisionEngine.evaluate_existing_position`. The hierarchy is hard stop → EMA20 thesis invalidation
  (full position only) → trailing 2×ATR → 30-weekday review → entry #2 when close > EMA20. The trailing
  stop carries forward and never loosens.
- **Indicators:** ATR and EMA20 use the canonical pipeline's definitions (a test checks parity with the
  scan's stored values).
- **Fills:** every signal comes from a close and is filled at the **next session open**.
- **Review alpha:** the frozen 30-day review needs the alpha on the review day. It is taken from a
  `VALID_PROSPECTIVE` full scan that became available after the previous close and by the review close.
  If no such scan exists, the review is recorded as `UNAVAILABLE_NO_SAME_DAY_SCAN` and the window ends at
  that close. This is a **measurement convention**, not a strategy rule.
- **Window end:** the first exit fill, or the close of the review session.
- **Observation return:** `R = P_exit / P_entry − 1`, where `P_entry` is the entry-1 open. The staged
  entry is reflected in the paper portfolio.
- **Benchmark:** SPY over the identical window: same entry session open, same exit session and price type.
  Excess return = R − R_SPY. This is benchmark-relative return, **not alpha**.
- **Path statistics:** MFE and MAE from intraday highs and lows (excluding the exit session when the exit
  fills at its open), MFE and MAE on closes, and maximum drawdown on closes.
- **Diagnostic horizons:** 5, 10, 20 and 30 sessions after entry, labelled DIAGNOSTIC ONLY.
- **Watchlist observations:** frozen horizon only, with no stops (they have no position).
- **Cost sensitivity:** per-side scenarios of 0, 5, 10 and 25 bps, labelled **HYPOTHETICAL**:
  `net = (1−c)·P_exit / ((1+c)·P_entry) − 1`. The gross baseline is always shown. No spread estimate is
  fabricated: an observed spread is unavailable.

## 6. Paper portfolio

| Item | Rule |
|---|---|
| Which runs | One per recorded run: the original TOP-5, original weights and original capital |
| Fills | Entry #1 at 40% and #2 at 60% of each original target notional, filled at that observation's fills. Unfilled tranches stay in cash. |
| Not done | No rebalancing, no substitution, no re-ranking |
| Valuation | Daily mark-to-close. Dividends received are tracked as cash (not reinvested). |
| SPY comparison | The full capital in SPY at the first entry open, marked to the same end |
| Reported | Return, SPY, excess, maximum drawdown, cash, open positions, status |
| Scope | Single-ticker evaluations are never part of portfolio statistics |

## 7. Statistics and caution

- **Reported:** n, mean, median, standard deviation, win rate, min and max of price return and excess vs
  SPY; total return; MFE, MAE and drawdown; results by recommendation rank and by recommendation date; the
  watchlist comparison; cost sensitivity, and whether the sign of mean excess changes with costs; paper
  portfolio means.
- **Sample status:** `NO_COMPLETED_OBSERVATIONS`, then `INSUFFICIENT_SAMPLE` (n < 30), then
  `OBSERVATIONAL_ONLY`.
- **Never reported:** no annualised figure, no significance test, no "alpha" claim.
- **Independence:** observations from runs on the same or overlapping dates are not independent; the
  number of independent runs is shown.

## 8. Diagnostics (read-only; hypothetical where marked)

- **Factor extremes:** median, min, max and top/bottom three per factor; counts of |z| > 3 and |z| > 10.
- **Contributions:** exact decomposition of each TOP-5 alpha; the dominant factor and its share of total
  absolute contribution; flagged as dominant above 50%.
- **Factor ablation (HYPOTHETICAL):** the alpha and alpha rank with the dominant factor removed.
- **Leave-one-out (HYPOTHETICAL):** remove one TOP-5 name and re-run the frozen DecisionEngine with every
  other score held fixed; reports which name would take the slot.
- **Sector:** TOP-5 exposure, any sector above 40%, sector counts in the ranked top 20, and the frozen cap
  scope.
- **Hard-stop distance:** per TOP-5 pick.
- **Ranking stability:** TOP-5 Jaccard and Spearman correlation of MODEL_RANK_E between consecutive full
  scans (cohorts shown).
- **Production is unaffected:** diagnostics never write to the run artifacts or the ledger (tested).

## 9. Updates, caching and replay

- **Update steps** (`app.py tracking update`):
  1. Back-fill eligible runs.
  2. Determine the latest completed session.
  3. Reuse the latest price snapshot if it covers that session and every ticker; otherwise download once
     (chunks of 40, 1 s pacing, up to 3 attempts with backoff) and store `tracking/prices/<update_id>.csv.gz`
     plus its sha256.
  4. Compute outcomes.
  5. Write `tracking/outcomes/<update_id>.json` atomically.
  6. Append the update entry, hash-chained, to `tracking/updates.jsonl`.
  7. Write the report.
- **Unchanged results:** if the outcome hash equals the previous update's, no new outcome file is written
  (status `NO_CHANGE`).
- **Failures:** a failure appends a `FAILED` entry. Earlier outcomes and the ledger are untouched, and an
  orphaned snapshot is never picked up (the log entry is written last).
- **Missing tickers:** status `PARTIAL`; the ticker's data is left missing.
- **Replay:** `app.py tracking replay [UPDATE_ID]` recomputes from the stored snapshot (no network) and
  compares the outcome hash. `tracking verify` also checks hash chains, run-artifact hashes and record
  reconstruction.
