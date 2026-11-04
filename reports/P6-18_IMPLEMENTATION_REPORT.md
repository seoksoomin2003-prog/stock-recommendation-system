# P6-18: Operational Completion of the Canonical Recommendation System

Date: 2026-11-04 (KST) · Environment: MacBook Apple Silicon, Python 3.14.2, pandas 3.1.0, yfinance 1.8.0
Evidence: `runs/<run_id>/` artifacts, `reports/P6-18_TEST_RESULTS.json`, `tests/fixtures/frozen_core_baseline_p6_18.json`.

## A. Executive summary

The repository now has one canonical production route (`pipeline/canonical.py`).
The Automated Market Scan and Direct Ticker Evaluation both use it. Every run
leaves durable, atomic artifacts with stage checkpoints. A live full S&P 500 run
completed against public providers in **194 s** (the previous full run took
8,018 s) with **307 MB** peak RSS and produced a **REAL RECOMMENDATION**. The
frozen P6-11B core is numerically identical to a baseline captured before any
change. One severe latent data defect was found and fixed: a single failed
symbol blanked every price. Readiness: **READY FOR CONTROLLED PERSONAL USE**,
with the limitations in section L.

## B. Initial audit findings (verified in source and runtime, not taken from earlier reports)

| # | Finding | Severity | Resolution |
|---|---|---|---|
| 1 | Project lives in iCloud-synced Desktop on a 97–99% full disk; macOS evicts files ("dataless"), so imports and cache reads block for minutes. The `.venv` had been fully offloaded (8 KB on disk). | Critical (environment) | New venv in `.venv.nosync` (symlinked as `.venv`), cache in `cache.nosync/`, `app.py doctor` detects offloaded files. User action still recommended (section L). |
| 2 | `DataLoader` preferred `Adj Close`; with `auto_adjust=True`, yfinance ≥1.x adds `Adj Close` only as an all-NaN filler when a symbol in the download fails. One bad or delisted symbol blanked all prices, giving LIVE DATA UNAVAILABLE. Reproduced live (direct evaluation with `ZZZZX`). | Critical | Use `Close` (already adjusted); regression test added. |
| 3 | SEC CompanyFacts value chosen as "latest `filed`". A 10-K files three fiscal years on one date, so the first (often oldest) was taken, and quarterly 10-Q values could be mixed with annual ones. | High | Period-aligned extraction: FY 10-K family with ~1-year duration; revenue and equity taken for the same fiscal period end; ASC 606 revenue concept added; >550-day-old period marked STALE and not used. |
| 4 | Liquidity gate fed **last-session** volume; the frozen rule is a 500,000 **average daily volume** threshold, and P6-12A and the legacy route used 20-day ADV. | High | `volume` input is ADV20 (threshold and comparison unchanged); last-session volume kept as a diagnostic. |
| 5 | Live candidates always had `sector="Unknown"`, so the frozen Technology sector cap could never bind. | High | Sector from the yfinance profile (Yahoo's label is exactly `Technology`, matching the frozen rule); missing sector reported as `Unknown` and flagged. |
| 6 | STALE, PARTIAL and quarantined tickers stayed in the cross-section used for normalisation, so their data shifted every other ticker's alpha. | High | Provenance gate now runs before FactorEngine; a test proves quarantined data has zero influence. |
| 7 | Price and volume each downloaded the full universe (2× requests); fundamentals ran serially (yfinance `.info` + SEC per ticker), which explains the 8,018 s run. | High | One chunked, memoised download; bounded thread pool with SEC < 10 req/s and Yahoo ~3 req/s pacing; bounded retries; 20 h cache of extracted genuine observations. |
| 8 | No run ID, checkpoints or failure artifact; output overwrote `reports/live_data_quality_latest.json`. | High | `RunRecorder` (section C). |
| 9 | No Direct Ticker Evaluation workflow. | High | `run_direct_evaluation` (section H). |
| 10 | Hardcoded NewsAPI key default in `utils/config.py` (flagged in P6-11A, never removed). | Security | Removed; env-only. **The old key should be considered exposed and rotated.** |
| 11 | `setup_logger` added a handler per call, so every log line printed twice. | Low | Idempotent handler. |
| 12 | Download `end` = local (KST) date, which could admit an in-progress intraday bar. | Medium | `end` = latest completed NYSE session + 1 day (exclusive). |
| 13 | Tests: `test_09` was `pass`; `test_11` asserted its own inline code; `test_13`/`test_16` only grepped source text; network tests overwrote the production universe cache; the scheduler test deleted the real daily report; the full legacy suite hung for more than 27 min in one module. | Medium | Rewritten as behavioural tests; live tests opt-in (`QPP_PROVIDER_TESTS=1`) using temp caches; per-module runner with timeouts (section I). |
| 14 | `main.py` used `Dict` without importing it (works only because of Python 3.14 lazy annotations). | Low | Imported. |
| 15 | Prior reports were inconsistent: the roadmap said the full run "did not produce a completed result", while `P6-17.5_FINAL_VERDICT.md` holds a full 503-ticker REAL RECOMMENDATION run (8,018 s). | Info | Roadmap rewritten from evidence. |

Not changed, intentionally: the research/backtest engines (`run_research=True`)
remain isolated legacy code. `run_system_audit` still builds random data, but it
is reachable only in research mode, and a test proves the live route never
imports synthetic or adaptive modules.

## C. Architecture changes

```
app.py (CLI / menu) ─┬─ scan      → pipeline.service.run_market_scan
                     └─ evaluate  → pipeline.service.run_direct_evaluation
                                        │ RunRecorder (run_id, artifacts, checkpoints)
                                        ▼
            pipeline.canonical.CanonicalPipeline.evaluate(tickers, ciks)
  market data (DataLoader, one download) → fundamentals (SEC + yfinance, paced, cached)
  → normalisation → provenance / required-data gate
  → FactorEngine → RankingEngine z-score → ScoringEngine(DEFAULT_FACTOR_WEIGHTS)   [frozen]
  → required-numeric + liquidity gate (DecisionEngine._check_data_quality, ADV20)  [frozen]
  → DecisionEngine.evaluate_portfolio: BEAR 75th pct → MODEL_RANK_E → sector cap/sizing [frozen]
  → final validity (decision.data_quality: needs 5 positions)                      [frozen]
```

`QuantTradingSystemV2._run_frozen_live_cycle` now delegates to the same class,
`python main.py` delegates to `app.py scan`, and `automation/daily_job.py` calls
`run_market_scan`. So there is exactly one production route.
`pipeline_status` (execution) and `recommendation_status` (validity) are separate fields.

## D. Files

**Created:** `app.py`, `pipeline/__init__.py`, `pipeline/canonical.py`, `pipeline/service.py`,
`pipeline/run_recorder.py`, `pipeline/report.py`, `README.md`,
`scripts/generate_frozen_core_baseline.py`, `scripts/run_test_modules.py`, `scripts/__init__.py`,
`tests/p6_18_fakes.py`, `tests/test_p6_18_frozen_core_parity.py`, `tests/test_p6_18_canonical_pipeline.py`,
`tests/test_p6_18_loader_contracts.py`, `tests/fixtures/frozen_core_baseline_p6_18.json`,
this report, `reports/P6-18_TEST_RESULTS.json`.
**Modified:** `data/loader.py`, `core/universe_provider.py`, `main.py` (live route + entry point only),
`utils/config.py` (secret removed, runtime settings appended), `utils/logger.py`,
`utils/market_calendar.py` (pandas 4 deprecation), `automation/daily_job.py`,
`tests/test_p6_17_5_live_pipeline.py`, `tests/test_p6_18_scheduler.py`, `.vscode/launch.json`, `requirements.txt` (pinned).
**Moved, not deleted:** old offloaded venv → `.venv.icloud-old` (safe to delete manually);
provider cache → `cache.nosync/provider`. Offloaded provider-cache entries were dropped
(regenerable). No user data deleted.
**Frozen files untouched:** `core/factor_engine.py`, `core/scoring_engine.py`, `core/ranking_engine.py`,
`core/decision_engine.py`, `contracts/decision.py`, frozen sections of `utils/config.py`.

## E. Frozen-core preservation audit

* A baseline was captured **before** any change from the unmodified engines on a seeded
  24-ticker, 430-session fixture covering: genuine missingness, volume 499,999 / 500,000,
  three regimes × two capitals, and Technology concentration.
* `tests/test_p6_18_frozen_core_parity.py` checks factor matrix, standardisation, scores,
  MODEL_RANK_E order and combined scores, and all six decision scenarios at 1e-12
  tolerance: **pass**. Behavioural boundary tests: liquidity 499,999 rejected / 500,000
  accepted; BEAR 0.7499 rejected / 0.75 kept; MODEL_RANK_E formula (including the capital
  penalty); 40% Technology cap; 20% sizing, 40/60 entries, 2×ATR stop, 30-day horizon;
  5-position validity; MOCK exclusion; exit hierarchy.
* Every run manifest records a sha256 of the frozen constants.
* **Decisions for user review** (input definitions, not math): (1) ADV20 as the liquidity
  input (finding 4); (2) the provenance gate runs before FactorEngine, so quarantined
  tickers no longer shape normalisation (finding 6); (3) Yahoo sector labels drive the
  existing literal `"Technology"` cap (finding 5); (4) SEC period alignment (finding 3).
  Each matches the directive's stated rule or route. Reverting any of them is a one-line
  change in `pipeline/canonical.py` or `data/loader.py`.

## F. Provider and provenance report (full run `20261104T071145Z_market_scan_e16f62`)

| Source | Result |
|---|---|
| Wikipedia S&P 500 | SUCCESS, REAL, 503 constituents, retrieved 2026-11-04T07:11:46Z |
| SEC company_tickers.json | REAL (live), 503/503 CIKs mapped. With a User-Agent lacking contact details SEC returns 403; the cached map is the disclosed fallback (`CACHED` + age). |
| yfinance prices/volume | 6 chunked requests; 502 REAL, 1 STALE (KVUE, last bar 2026-10-30); 502 symbols at last bar 2026-11-03 = expected latest session |
| Fundamentals | 447 REAL, 56 PARTIAL; ROE: SEC 406 / yfinance 66 / unavailable 31; margin: SEC 445 / yfinance 58; PER unavailable 24 (negative earnings) |
| SEC extraction | 457 period-aligned REAL, 31 STALE annual period (fallback to yfinance), 15 no NetIncomeLoss |
| Requests | 478 yfinance `.info`, 478 SEC CompanyFacts, 25 cache hits, **0 provider errors or retries** |

## G. Automated scan validation

* Bounded (25 symbols, `20261104T070854Z_market_scan_773448`): REAL RECOMMENDATION, 31 s, 193 MB.
* Full (503 symbols, cold except 25): requested 503 → provenance gate 446 → liquidity and
  required data 433 → MODEL_RANK_E ranked 433 (regime SIDEWAYS, BEAR filter inactive) →
  **TOP-5: BRK-B, CPT, CL, SNDK, MU** (two Technology names, at the 40% cap). Watchlist:
  TRGP, EXPD, TGT, HST, NUE. Quarantined: 57 provenance (56 PARTIAL fundamentals, 1 STALE),
  13 liquidity (ADV20 < 500k).

## H. Direct ticker evaluation validation

Run `20261104T071652Z_direct_evaluation_0bbc6d`, input `NVDA AAPL TSLA PLTR RKLB SPY ZZZZX @@`:
NVDA, AAPL, TSLA and PLTR were scored inside the same 446-name cross-section, with alphas
identical to the scan (e.g. AAPL 94.2nd percentile, MODEL_RANK_E #269 →
`RANKED_NOT_SELECTED`). RKLB (non-member) → QUARANTINED: PER missing. SPY → QUARANTINED:
ETF, no company fundamentals. ZZZZX → SYMBOL_NOT_FOUND_OR_NO_PROVIDER_DATA. `@@` →
INVALID_SYMBOL_FORMAT. Each ticker's individual verdict is reported separately from the
portfolio status (REAL RECOMMENDATION). The first attempt exposed defect B-2, fixed and re-run.

## I. Test results (61 modules, each in its own process, 180 s timeout: `scripts/run_test_modules.py`)

| Class | Count | Detail |
|---|---|---|
| Executed and passed | **53 modules** | All 5 P6-18 modules (frozen-core parity 12 tests, canonical pipeline 20, loader contracts 14, scheduler 3, plus import isolation); P6-11B decision engine; P6-17.4 reconciliation; 46 legacy modules |
| Executed and failed | **1 module** | `test_local_workload_control` (3 of 6 tests): legacy research path, 365-day lookback assertion vs the loader's 425-day momentum minimum (same in the original loader), and an empty-scores duplicate test in `mode="backtest"`. Not the canonical route; unresolved. |
| Not executed | **7 modules** | pytest-style functions with no `unittest.TestCase`; pytest not installed, so 0 tests collected |
| Blocked by provider (opt-in) | 5 tests | `QPP_PROVIDER_TESTS=1`; covered in practice by the full live run |

Fixes made during testing: added the missing `python-dotenv` dependency (legacy
`alpha_engine` import, which caused 5 import errors); updated the stale `FALLBACK`→`MOCK`
expectation. One timeout was environmental (iCloud re-downloading `data/tickers.db`).
Note: `test_sec_security_master` writes to the production `data/tickers.db`.
Raw results: `reports/P6-18_TEST_RESULTS.json`.

## J. Full-universe run

Completed: `runs/20261104T071145Z_market_scan_e16f62` (state COMPLETED, all 11 checkpoints).

## K. Runtime and resources (full run)

| Stage | Cumulative seconds |
|---|---|
| Universe bootstrap | 1.1 |
| Market data (503 × 430 days) | 20.4 |
| Fundamentals (478 SEC + 478 Yahoo) | 185.4 |
| Gates + factors + MODEL_RANK_E + portfolio | 193.8 |

Peak RSS 307 MB (`/usr/bin/time -l`); 53 s user CPU. Well within the 8 GB M2 budget.

Direct evaluation (506-symbol cross-section): cache rebuild 271 s; **warm run 94 s wall**
(fundamentals 3.5 s with 505 cache hits and 0 fundamental requests; the rest is the
always-live Wikipedia and Yahoo price download).

## L. Remaining limitations

1. **iCloud + disk pressure** (97–99% full) can still offload project source files. Fix it
   permanently: Finder → right-click the folder → *Keep Downloaded*, move the project out of
   Desktop/Documents, or free disk space.
2. The frozen contract quarantines every PARTIAL-fundamental ticker (about 11% of the S&P
   500: negative earnings, negative equity), so loss-making companies are never recommended.
3. ROE mixes SEC FY values and yfinance TTM values across tickers (existing SEC-primary policy).
4. The frozen MODEL_RANK_E has no event awareness; a price pinned by a pending acquisition
   (e.g. AES in the bounded run) has a very small ATR and stop distance.
5. No historical or out-of-sample validation of predictive power (P6-12D deferred). Rankings
   are transparent, but their expected return is unproven.
6. yfinance is an unofficial interface to Yahoo; terms and availability can change without
   notice. SEC requires a declared User-Agent, so set `SEC_USER_AGENT`.
7. Direct evaluation of a non-S&P ticker slightly enlarges the cross-section (S&P 500 +
   supplied tickers).
8. Capital is in USD; the default 10,000,000 is a legacy value. Pass `--capital` for real
   account size (sizing only affects shares and the MODEL_RANK_E capital penalty).

## P. Readiness verdict

**READY FOR CONTROLLED PERSONAL USE.** Not institutionally validated; see L-5.
