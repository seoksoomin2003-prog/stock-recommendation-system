# KR Prospective Paper Tracking Specification: schema `kr-1`

Code: `markets/kr/tracking.py`. Market: South Korea (KOSPI + KOSDAQ). Currency: **KRW only**.

This tracking is fully separate from the US P6-20 ledger. It shares only the hash-chain primitives (`append_records`, `verify_chain`). Paper results are **not** actual investor returns.

## 1. Ledger (immutable, append-only)

| Item | Rule |
|---|---|
| Files | `tracking/kr/ledger/observations.jsonl` (RUN and OBSERVATION records), `tracking/kr/updates.jsonl` (update log), `tracking/kr/prices/<update_id>.csv.gz` (price snapshot per update), `tracking/kr/outcomes/<update_id>.json`, `tracking/kr/reports/latest.{md,html}` |
| Integrity | `prev_hash` / `record_hash` chain, the same as the US ledger. Exclusive lock and `fsync` on append. |
| Keys | `RUN:KR:<run_id>`, `OBS:KR:<run_id>:<code>`. Re-recording writes nothing. |
| Eligible runs | `market == "KR"`, mode `kr_market_scan`, full liquid-300 scope, `REAL RECOMMENDATION`, state COMPLETED, exactly 10 positions. Bounded scans and direct evaluations are never recorded. |
| Source | Built only from the run's own artifacts (`runs/KR/<run_id>/`). The sha256 of `validation_result.json`, `candidate_flow.json` and `universe_snapshot.csv.gz` is stored. `verify` rebuilds every record from the artifacts and compares. |
| RUN record | run ID; versions (market config, data spec, account mapping, model, model status); signal timestamp (UTC and KST) with its classification; capital (KRW); universe summary and snapshot sha256; active factors and weights; provider and traded-value basis |
| OBSERVATION record | security key; code; name; market; KIND industry and class; rank; score; z-scores; raw factors; target weight; whole shares; reference close (KRW); allocated KRW; `entry_not_before`; entry and exit rules; horizon (20 sessions); benchmark index; currency; cohort |

## 2. Cohorts and states

| Cohort | Meaning |
|---|---|
| `EXPERIMENTAL_PROSPECTIVE` | Every observation of a model whose status is EXPERIMENTAL (KR-EXP-*). Never pooled with any approved model and never with the US. |
| `APPROVED_PROSPECTIVE` | Reserved for a future KR model that passes the validation gates in `KR_MODEL_SPECIFICATION.md`. Not used today. |

Outcome states are recomputed on every update from that update's snapshot:

| State | Meaning |
|---|---|
| `PENDING_ENTRY` | No KRX session yet on or after `entry_not_before` |
| `PENDING_OUTCOME` | Entered; fewer than 20 sessions observed. Marked to the latest close. |
| `COMPLETED_OUTCOME` | All 20 sessions observed |
| `INCOMPLETE` | `ENTRY_BAR_MISSING` (no valid open on the entry session) or `DATA_GAP` (an observed KRX session inside the window has no valid bar for the security, e.g. a halt). Never filled or interpolated. If the provider later supplies the bar, a later update can resolve it. |

## 3. Timing (no look-ahead)

- **Signal time:** the run's `RUN_COMPLETED` instant (UTC, also stored in KST).
- **Classification:**
  - before 09:00 KST on a weekday → `PREMARKET`, entry the same day;
  - 09:00–15:30 → `REGULAR_SESSION`, entry the next day;
  - after 15:30 → `AFTER_CLOSE`, entry the next day;
  - weekend → `NON_SESSION_DAY`, entry the next day.

  `entry_not_before` is that calendar date.
- **Entry:** the **open** of the first observed KRX session (a KOSPI index bar date) on or after `entry_not_before`. Holidays are skipped because they have no bar.
- **Exit:** the **close** of session 20, counting the entry session as session 1. KR-EXP-0.1 has no stop-loss and no other exit rule.
- A bar is used only after 18:00 KST on its date. Price snapshots never contain later bars (this is tested).

## 4. Returns (KRW)

| Measure | Definition |
|---|---|
| Price return | exit close / entry open − 1 |
| Total return | price return × (adj/close factor at exit ÷ factor at entry), i.e. it includes Yahoo's dividend adjustment where present. Otherwise `None`. |
| Benchmark | each security's **own market index** (KOSPI `^KS11` or KOSDAQ `^KQ11`) over the identical window, from the index open on the entry session to the index close on the exit session. This is the benchmark policy for a mixed KOSPI/KOSDAQ universe: no blended index is assumed. |
| Excess | price return − benchmark return |
| MFE / MAE | maximum and minimum close inside the window relative to the entry price |
| Cost sensitivity | 0, 10, 25 and 50 bps per side: `(1+r)(1−c)/(1+c) − 1`. Hypothetical. The KRX sell-side securities transaction tax is **not** modelled separately and is covered only by the higher scenarios. |

## 5. Paper portfolio

Per run:

- invested = Σ shares × entry open; value = Σ shares × exit close (or the latest mark);
- portfolio price return; position-weighted matched-index benchmark; excess;
- KRW only. Uninvested cash (from rounding to whole shares) is reported in the run, not in returns.

## 6. Statistics and caution

- Official scope: `KR × EXPERIMENTAL_PROSPECTIVE × COMPLETED_OUTCOME`, in KRW.
- Reported: n, mean, median, std, win rate, min and max for price return, excess, MFE and MAE; mean net return per cost scenario; turnover between consecutive runs; industry exposure counts. Everything is split by model version / data-spec version.
- No annualisation, no significance test, no profitability claim. The sample status is `NO_COMPLETED_OBSERVATIONS` / `INSUFFICIENT_SAMPLE` (< 30 completed) / `OBSERVATIONAL_ONLY`.
- Overlapping 20-session windows from runs less than 20 sessions apart are not independent. This is stated in the report.

## 7. Updates, replay, verify

- `python app.py --market KR tracking update` records any eligible runs not yet recorded, downloads bars for every observed security and both indices, writes a snapshot, computes outcomes, appends the update log (with snapshot and outcomes sha256) and writes the report.
- `replay(update_id)` recomputes outcomes from the stored snapshot. The result must be canonical-JSON identical.
- `python app.py --market KR tracking verify` checks:
  - both hash chains;
  - artifact hashes;
  - record reconstruction for every run;
  - a replay of the latest update.
