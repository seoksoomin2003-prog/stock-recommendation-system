# P6-25 Implementation Report: Separate Paper Tracking per Market

Date: 2026-11-04 · Status: **IMPLEMENTED; observation started**.

Specifications:

- `KR_TRACKING_SPECIFICATION.md` (new);
- `US_TRACKING_SPECIFICATION.md` (US unchanged from P6-20).

## KR tracking (`markets/kr/tracking.py`)

- Immutable hash-chained ledger in `tracking/kr/`. Duplicate-safe keys `OBS:KR:<run>:<code>`. Records built only from run artifacts, with artifact and universe-snapshot sha256.
- Entry at the first KRX session open on or after `entry_not_before`; exit at the close of session 20.
- Matched-index benchmark: KOSPI → ^KS11, KOSDAQ → ^KQ11.
- KRW only. Cost scenarios of 0, 10, 25 and 50 bps; MFE and MAE.
- Gaps lead to INCOMPLETE and are never filled.
- Paper portfolio per run; summaries split by model and data-spec version; turnover; no annualisation.
- Replayable updates; `verify`.

## Live state (2026-11-04)

| Market | Ledger | Runs tracked | Observations | States | Verify |
|---|---|---|---|---|---|
| US | `tracking/ledger/` (66 chain rows: 6 RUN + 60 OBSERVATION, including watchlist diagnostics) | 3 VALID_PROSPECTIVE + 3 PRE_FIX_EXCLUDED (including the P6-18 run) | 15 valid TOP-5 | 15 PENDING_OUTCOME (as of NYSE session 2026-11-03) | chains OK; 6 runs reconstruction MATCH; replay MATCH |
| KR | `tracking/kr/ledger/` (11 records) | 1 (`20261104T141806Z_kr_market_scan_c4ed3d`) | 10 | 10 PENDING_ENTRY (signal 23:18 KST, after the close → entry at the 2026-11-05 open) | chains OK; reconstruction MATCH; replay MATCH |

**Contamination check** (`MULTI_MARKET_PLATFORM_FINAL_REPORT.md` §6): no US record has a non-US market; no KR record is non-KR or non-KRW; no run ID overlaps between ledgers; `runs/` holds only US manifests and `runs/KR/` only KR manifests.

**Caution.** The three valid US runs are from the same NYSE session and have the same TOP-5. They are not independent observations, as the P6-20 report already states.

## Tests

`tests/test_p6_25_kr_tracking.py`, 11 of 11:

- KR/KRW/cohort fields; separation from the US ledger; duplicate idempotence;
- tamper and artifact-change detection;
- entry ≥ entry_not_before with a 20-session horizon; pending states; no bars after `now`;
- DATA_GAP and ENTRY_BAR_MISSING lead to INCOMPLETE; cost scenarios; replay and report;
- ineligible runs are refused.
