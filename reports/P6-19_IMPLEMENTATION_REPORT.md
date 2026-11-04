# P6-19 Implementation Report: Independent Verification, Operational Hardening and Controlled Personal-Use Certification

Date: 2026-11-04 · Project root: `~/Developer/quant-stock-engine` · Python 3.14.2 (arm64)

**Final verdict: READY FOR CONTROLLED PERSONAL USE.** Every data and decision gate is
verified end to end on live public data, and the results are reproducible from their
artifacts. **Predictive profitability is unproven.** A REAL RECOMMENDATION means only
that every gate passed. Two user actions remain open (§D).

---

## A. Forensic verification of P6-18 claims

| Area | P6-18 claim | Actual (verified in P6-19) | Evidence | Action |
|---|---|---|---|---|
| Tests | "154 deterministic tests pass" | The runner counted only unittest-style tests. Under pytest the suite has 736 tests in 62 files. Seven pytest-style modules had never been executed. First full run: 724 passed, **7 failed**, 5 skipped. | pytest run 1 log | Reconciled: 778 collected, 768 passed, 0 failed (§E) |
| Test safety | Implicitly safe | The tests **overwrote 20 historical P6-9/P6-10 reports**, modified `data/tickers.db` and `research_cache.db`, fetched SEC data live, and created `data/signals` files | checksum diff after run 1 | Everything restored from backup (checksums verified). Offline sandbox and write guard added (`tests/conftest.py`). |
| Code location | Project runs from `~/Desktop/퀀트 예측 프로그램` | The folder is iCloud-synced, with 590 files offloaded (202 `.py`) on a 97%-full disk. Twelve test modules and six scripts hard-coded the Desktop `sys.path`, so a copy elsewhere silently imported the old code. | `ls -lO`, the 4 P6-19 tests that failed because of it | Moved to `~/Developer` and the paths fixed (§C) |
| Capital | Configurable | `DEFAULT_CAPITAL = $10,000,000` was silently applied in `pipeline/service.py` | source | Removed. Capital must be explicit and validated (§D). |
| SEC identity | Configured | Default `AntigravityIDE/1.0 (soominseok@example.com)`, a fabricated placeholder contact. Five scripts hard-coded contacts, one of them the user's personal e-mail, another a third-party domain. | source | Read from the environment only. SEC is never queried without a valid identity (§D). |
| Secrets | "No secrets" | An old NewsAPI key was still present in a stale `.pyc` in the Desktop copy (`utils/__pycache__/config.cpython-314.pyc`) | `strings` | `.pyc` deleted. Key absent from the new tree. **The user must rotate it** (§D). |
| Sector cap | "Sector cap enforced (40%)" | Enforced **only for the literal `Technology`**. Other sectors are not capped. | `core/decision_engine.py` `_optimize_portfolio` | Frozen-core limitation. Reported (`sector_cap_warnings`) but not changed (§Frozen conflicts). |
| Data-quality gate | "PARTIAL excluded" | Correct, and identical to the frozen `_check_data_quality` set. P6-18 only moved the check before normalisation. | source and tests | KEEP |
| ADV20 | 20-day mean share volume | Correct (`>= 500000`). Hygiene for duplicate timestamps and negative values was missing. | tests | Hygiene added, boundaries tested (B1) |
| Full-universe validated | TOP-5 BRK-B, CPT, CL, SNDK, MU is valid | The gates passed, but **two of the five picks came from provider/input defects**: BRK-B from Yahoo `priceToBook = 0.00107` (value z = 21.1), and CPT from a $13M ASC 606 revenue slice (margin 2,965%) | P6-19 run `9072c9` candidate flow | Fixed at the input layer (B4 REVISE). The pre-fix run is excluded from forward statistics. |
| Cache status | Fundamentals labelled REAL | Cache hits were labelled REAL | source | Now `CACHED` (frozen-usable status) |
| Remaining blockers | "none" | The items above | | Resolved or documented |

## B. Formal review of the four input definitions

The full specification is in `docs/DATA_INPUT_SPECIFICATION.md`.

| # | Definition | Verdict | Basis |
|---|---|---|---|
| B1 | ADV20 = mean of the last 20 valid daily **share**-volume sessions (not dollar volume). Duplicates keep the last value; NaN sessions don't count; negative values are dropped; fewer than 20 sessions means missing. | **KEEP** | Boundary tests: 499,999 FAIL / 500,000 PASS / 500,001 PASS. Share vs dollar volume, NaN, duplicates and short history are all tested. |
| B2 | Yahoo `info.sector` verbatim. Unknown sector → `Unknown` with reason, never guessed. | **KEEP** | Tested with 8 Technology candidates (2 selected). Taxonomy note: Yahoo's sectors are not GICS. Frozen Technology-only limitation documented. |
| B3 | Data-quality exclusion before normalisation, using the frozen usable-status set | **KEEP** | Excluded candidates with extreme values leave every valid candidate's alpha, z-scores, percentiles and rank bit-identical (tested) |
| B4 | SEC period selection: annual forms, 330–380 day duration, latest period end then latest `filed` (restatements win), the same period end for NI, revenue and equity, accn/fy/fp kept | **REVISE** | Period logic kept and tested (restatement, prior-year comparative, quarterly ignored, 53-week year, no period mixing). **Revised** after the live run: (a) revenue = largest same-period total-revenue concept, (b) the SEC margin is rejected when NI > selected revenue, with Yahoo fallback, (c) new P/B consistency rule (§4b, **flagged for your review**). |

## C. Storage and iCloud

- Copied (rsync) to `~/Developer/quant-stock-engine`, which is not iCloud-synced. 701 files; venvs, `__pycache__`, `.DS_Store` and `cache.nosync` were excluded. A fresh `.venv` was built.
- The **original Desktop folder was not deleted or moved.** One change was made there: the stale `.pyc` that contained the old NewsAPI key was deleted.
- Backups of all data DBs and JSON, plus a sha256 manifest of 150 files, are in `~/Developer/qse-backups/`.
- `app.py doctor` warns if the project is run from an iCloud-synced path, and reports offloaded files and disk space.
- Disk is still 97% used (8.3 GB free). This is an environment risk, not a code defect.

## D. Security and configuration

| Item | Change |
|---|---|
| NewsAPI key | Not present anywhere in the new tree. **Not rotated**: rotation must be done by you at <https://newsapi.org/account>. NewsAPI is optional and unused by the pipeline. |
| `SEC_USER_AGENT` | Environment or `.env` only, with no default. Validation (`utils/runtime_config.py`): MISSING / INVALID (template text, no e-mail, placeholder domains, fewer than 2 words) / CONFIGURED. If it is not CONFIGURED, SEC is **not contacted** (status `SEC_NOT_CONFIGURED`; the CIK map falls back to cache with provenance `NOT_QUERIED`). Only the status is written to artifacts, never the value. Your shell profile sets it, and it reports CONFIGURED. |
| Capital | No default. `--capital`, then `QPP_CAPITAL`, then the interactive prompt. It must be positive and finite (`"50,000"`, `"$12_500.5"` accepted). Otherwise the run exits with code 2 **before any fetch**. The amount and its source are printed and stored in `validation_result.json`. |
| `.env` | `.env.example` is provided. `.env` never overrides shell variables. `.gitignore` excludes `.env`, venvs, caches, `runs/`, `data/*.db`, the SEC cache and signals. |
| Hard-coded contacts | Removed from 6 scripts and modules (env only, with no fallback) |

## E. Tests

Final run: `.venv/bin/python -m pytest tests -q`, 158.7 s wall, about 360 MB peak RSS. Details are in `reports/P6-19_TEST_RESULTS.json`.

| Collected | Passed | Failed | Errors | Skipped | Strict xfail (isolated) | Deselected | Collection errors | Empty test files |
|---|---|---|---|---|---|---|---|---|
| 778 | 768 | 0 | 0 | 5 | 5 | 0 | 0 | 0 |

- **Skipped (5):** live-provider tests. They run only with `QPP_PROVIDER_TESTS=1`.
- **Isolated (5)**, strict xfail with documented reasons in `tests/conftest.py`. If any of them starts passing, it fails the run.
  - Two expect a 365-day lookback, which contradicts the frozen 425-day momentum lookback.
  - One expects company-name alias resolution and scoring of stale mock bars, which contradicts the P6-14 contract.
  - Two are legacy research engines that are not on the production route (drift, API change). They had never been executed before.
- **Fixed, not weakened:**
  - `test_p6_13_5_focused::test_01` made deterministic: the same assertions, with providers mocked.
  - `test_sec_security_master` now uses a temp DB and a public-CIK fixture.
  - 12 modules had their Desktop `sys.path` fixed.
  - Two tests gained the now-mandatory explicit capital.
- **Safety:**
  - offline by default;
  - runs inside a throw-away mirror;
  - any write to the real `data/`, `reports/`, `runs/` or `tracking/` fails the test and is restored;
  - no credentials and no trading.

  After the final run, the sha256 check of the 150 protected files showed changes only to `data/loader.py` (intentional edit) and `data/sp500_universe_cache.json` (refreshed by the live scans, not by the tests).
- **New** (`tests/test_p6_19_hardening.py`, 41 tests): SEC UA, capital, `.env`, secret hygiene, ADV20 boundaries, sector, exclusion before normalisation, SEC fiscal periods, SEC gating and cache, frozen-source pinning, direct single-ticker evaluation, CLI, forward tracking, and the live-defect regressions (REIT revenue, revenue below NI, P/B rejection, rejected value surfaced as a reason).

## Frozen-core parity

- The five frozen sources have sha256 values identical to the original Desktop copy (last modified Aug 2026, before P6-18). They are pinned in `tests/fixtures/frozen_source_sha256_p6_19.json`, checked by `TestFrozenSourcePinned`, and recorded in every `run_manifest.json`. **Match: true.**
- Numerical parity against the pre-change golden baseline (`tests/test_p6_18_frozen_core_parity.py`, 12 tests): pass.
- Not modified: factor formulas, DEFAULT_FACTOR_WEIGHTS, MODEL_RANK_E, 500,000 ADV, 75th-percentile BEAR, 30%/40% caps, entry, stop-loss, horizon and execution thresholds. All P6-19 corrections are at the input layer (`data/loader.py`, `pipeline/canonical.py`).

## F. Live validation (public providers, capital $50,000 explicit, SEC configured)

| Run | Scope | Result | Time | Peak RSS | Notes |
|---|---|---|---|---|---|
| `20261104T105421Z_market_scan_e320cd` | bounded 25 | REAL | 13 s | 225 MB | 21 passed provenance (ABBV and MO have negative equity, so ROE is missing; APD and ARE have no PE) |
| `20261104T105453Z_market_scan_9072c9` | full 503 | REAL | 199.7 s | 279 MB | TOP-5 BRK-B, CPT, CL, SNDK, MU, the same as P6-18. **Defects found** (§A). Excluded from forward statistics. |
| `20261104T110528Z_market_scan_4f4b37` | full 503 | REAL | 211.0 s | 300 MB | BRK-B quarantined (`PROVIDER_VALUE_REJECTED_PBR`), CPT margin corrected to 0.244. **New finding:** FITB and DTE (lease-income slice) and HBAN and MTB (fee slice) had margins above 100%, putting FITB at #1. Excluded from forward statistics. |
| **`20261104T111004Z_market_scan_953827`** | **full 503** | **REAL** | **218.4 s** | **225 MB** | Final. Details below. |
| `20261104T111435Z_direct_evaluation_5008d3` | 9 symbols plus the S&P 500 cross-section | REAL | 45.5 s | 181 MB | Every symbol got an individual verdict (below) |

**Final full run `953827`**

- Universe: SUCCESS/REAL, 503 constituents (Wikipedia). CIK map REAL (SEC).
- Prices: REAL 502, STALE 1 (KVUE, last bar 2026-10-30, quarantined). Last bar 2026-11-03 for all others.
- Fundamentals: REAL 447, PARTIAL 56.
  - ROE source: SEC 406, Yahoo 67, missing 30.
  - Margin source: SEC 447, Yahoo 56.
  - SEC extraction: REAL 457, STALE 31, NI unavailable 15.
- Requests: yfinance download 6, info 503, SEC companyfacts 503 (paced at 8/s). Provider events: 0.
- Funnel: 503 → 446 (provenance) → 433 (liquidity/required) → 433 ranked → 5. Quarantine: PROVENANCE_STATUS_REJECTED 57, LIQUIDITY_REJECTED 13.
- **TOP-5:** CL, SNDK, MU, AES, CHTR, each 20%. Sectors: Technology 40%, the others 20% each. Regime: SIDEWAYS.
- Watchlist: ALL, EIX, MTB, CFG, PNC.
- Profit margins above 100%: **0**. Rejections: P/B 1 (BRK-B); SEC margins 4 (DTE, FITB, HBAN, MTB, now on Yahoo values).
- **Reproducibility:** `scripts/replay_run_decision.py runs/<id>` rebuilds the eligible set from `candidate_flow.json`, re-runs the frozen `DecisionEngine.evaluate_portfolio` with the recorded capital and regime, and reproduces status, tickers, weights and shares: **match: true**.

**Direct evaluation `5008d3`** (NVDA AAPL TSLA PLTR RKLB SPY ZZZZX @@ BRK-B)

- Portfolio TOP-5: identical to the scan.
- Individual verdicts:

| Symbol | Verdict | Detail |
|---|---|---|
| NVDA | RANKED_NOT_SELECTED | rank 341 |
| AAPL | RANKED_NOT_SELECTED | rank 301 |
| TSLA | RANKED_NOT_SELECTED | rank 351 |
| PLTR | RANKED_NOT_SELECTED | rank 420 |
| RKLB | QUARANTINED | no PE; not an S&P 500 constituent |
| SPY | QUARANTINED | ETF; no ROE or margin |
| ZZZZX | QUARANTINED | `SYMBOL_NOT_FOUND_OR_NO_PROVIDER_DATA` |
| @@ | NOT_EVALUATED | `INVALID_SYMBOL_FORMAT` |
| BRK-B | QUARANTINED | `PROVIDER_VALUE_REJECTED_PBR` |

- Single-ticker verdicts are never blocked by the five-candidate portfolio rule (also tested).

**Observations to read the TOP-5 honestly**

- CL ranks #1 on ROE 39.5. That figure is genuine: SEC equity is $54M after buybacks. The frozen standardisation does not winsorise, so one extreme factor value can dominate.
- SNDK and MU margins (0.56 and 0.64) are SEC-sourced, reported values.
- These are frozen-model properties, not data errors, and they are not changed.

## G. Usability

| Task | Command |
|---|---|
| Environment check (tested from a clean `env -i` login shell, exit 0) | `cd ~/Developer/quant-stock-engine && .venv/bin/python app.py doctor` |
| Mode A | `.venv/bin/python app.py scan --capital 50000 [--open]` |
| Mode B | `.venv/bin/python app.py evaluate NVDA AAPL --capital 50000` |
| Menu | `.venv/bin/python app.py` (asks for capital) |
| Other | `status`, `track`. VSCode launch configurations ask for capital. |

- Reports (console, markdown, HTML) show capital and its source, SEC usage, MODEL_RANK_E rank and score, ADV20 and liquidity, the data status and last bar date per pick, exclusions with reasons, sector notes, and the operational meaning of REAL.
- No order placement, broker connection or account authentication exists anywhere.

## I. Prospective monitoring foundation (P6-20)

- `pipeline/forward_tracking.py` records the TOP-5 of every **full, REAL** market scan, idempotent per run and ticker. It stores frozen fingerprints, regime, factors, reference close and hard stop.
- `app.py track` reports close-to-close outcomes at 5, 10, 20 and 30 sessions:
  - excess return vs SPY;
  - return after an assumed 0.1% round-trip cost;
  - MFE/MAE on closes, and hard-stop breach on close;
  - sector concentration, and TOP-5 Jaccard stability.
- Fewer than 30 matured observations → `INSUFFICIENT_SAMPLE`. No significance tests, and no re-tuning.
- `tracking/excluded_runs.json` lists the two defect-affected runs (`9072c9`, `4f4b37`). Their ledger rows are kept for audit but excluded from the statistics.
- Current state: 5 counted positions from 1 run; nothing has matured yet.

## Frozen-core conflicts (reported, not changed)

1. **Sector cap is Technology-only.** The frozen `_optimize_portfolio` caps only `sector == "Technology"`, at 2 of 5. A portfolio of five Healthcare names would pass. Enforcing a general 40% cap would change frozen logic. Every run therefore reports `sector_cap_warnings` when a non-Technology sector exceeds 40% (none in the final run). **Your decision is needed** if you want this changed in a future, explicitly unfrozen phase.
2. **No winsorisation** in the frozen cross-sectional standardisation. Genuine outliers (CL ROE) can dominate. Not changed.
3. The frozen momentum lookback is 425 days. Two legacy tests that expect 365 days are isolated, not "fixed".

## Limitations

- Predictive power and profitability are **unproven**. Forward observation has only just started.
- Yahoo is an unofficial, best-effort source: PE, PBR, sector, market cap and prices. The P/B consistency rule catches gross errors (more than 10×) only.
- The SEC revenue concepts are a fixed list. A company reporting total revenue under a concept outside it falls back to Yahoo (labelled).
- Survivorship-free historical validation remains impossible at zero cost (P6-12D deferred).
- The disk is 97% full, so `doctor` warns.
- The repository is not under git (no `git init` was performed without your request).

## Changed files (summary)

**New**

- `utils/runtime_config.py`
- `pipeline/forward_tracking.py`
- `tests/conftest.py`
- `tests/test_p6_19_hardening.py`
- `tests/fixtures/frozen_source_sha256_p6_19.json`
- `.env.example`, `.gitignore`, `requirements-dev.txt`
- `docs/DATA_INPUT_SPECIFICATION.md`
- `scripts/summarize_pytest_junit.py`, `scripts/replay_run_decision.py`
- `tracking/excluded_runs.json`

**Modified**

- Application code:
  - `utils/config.py`, `data/loader.py`
  - `core/universe_provider.py` (data acquisition only; not a frozen file)
  - `pipeline/canonical.py`, `pipeline/service.py`, `pipeline/run_recorder.py`, `pipeline/report.py`
  - `app.py`, `automation/daily_job.py`, `automation/scheduler.py`
  - `.vscode/launch.json`
- Tests: 12 modules (path fix) and 4 modules (determinism, sandboxing, explicit capital).
- Scripts and modules:
  - 6 scripts (path fix);
  - 6 scripts and modules (hard-coded SEC contacts removed).
- Documentation: `README.md`, `reports/ROADMAP.md`.

Historical reports, including P6-18, are unchanged. Corrections to them are recorded in the ROADMAP and in §A above.

## User actions

1. **Rotate the NewsAPI key** at <https://newsapi.org/account>. It was exposed in earlier versions and has **not** been rotated by this work.
2. **Review the new P/B consistency rule (§B4b, 10× tolerance) and the B4 revenue revision.** Both are input-layer rules introduced in P6-19.
3. Optional: once satisfied with the new location, move `~/Desktop/퀀트 예측 프로그램` to the Trash yourself.
4. Optional: put the project under git.

## Verdict

**READY FOR CONTROLLED PERSONAL USE**, as a transparent screening tool for personal research, with explicit capital, no orders, and predictive profitability unproven. This is not READY FOR INSTITUTIONAL USE.
