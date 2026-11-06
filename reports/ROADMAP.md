# Quant Prediction Program: Engineering Roadmap

Status levels: Implemented → Unit Tested → Integration Tested → Provider Tested →
Full-Universe Validated → Operationally Ready. A level is claimed only with evidence
that has been re-verified (P6-19 re-checked every P6-18 claim against code, artifacts
and fresh runs).

## Official phase table (multi-market directive P6-21..P6-25, 2026-11-04)

The "Official status" column is the status the directive assigns. The "State at end of 2026-11-04" column records what the evidence shows after this work.

| Phase | Scope | Official status | State at end of 2026-11-04 | Evidence |
|---|---|---|---|---|
| P6-11B | Frozen US mathematical core | **FROZEN** | unchanged; 5 sha256 pins match | `tests/fixtures/frozen_source_sha256_p6_19.json`, `MULTI_MARKET_PLATFORM_FINAL_REPORT.md` §2 |
| P6-18 | Shared US live pipeline | **Verify evidence** | re-verified: the full US scan `20261104T143051Z_market_scan_7dbbfd` returned REAL RECOMMENDATION (503 symbols, 65 s) | run artifacts; P6-19 report |
| P6-19 | Verification and hardening | **Verify evidence** | re-verified: sandbox guard active (and it caught and restored a cwd leak in a new test); frozen pins pass | `P6-19_IMPLEMENTATION_REPORT.md`, `P6-21_25_pytest_junit.xml` |
| P6-20 | US prospective paper tracking | **ACTIVE** | 3 valid runs / 15 TOP-5 observations, all PENDING_OUTCOME; verify OK | `US_TRACKING_SPECIFICATION.md`, `US_PERFORMANCE_REPORT.md` |
| P6-20-A | Approved US data-input rules | **FROZEN VERSION** | in force for every US run since `63c283d` | `docs/DATA_INPUT_SPECIFICATION.md` |
| P6-21 | Multi-market architecture | **IN PROGRESS** | implemented and tested (identity, config, storage v2, isolation) | `P6-21_ARCHITECTURE.md`, `P6-21_IMPLEMENTATION_REPORT.md` |
| P6-22 | Korean data engine | **PLANNED** | implemented: KIND and Yahoo live; OpenDART and KRX offline only (no keys) | `P6-22_*` |
| P6-23 | Independent KR model | **PLANNED** | implemented as `KR-EXP-0.1`, **EXPERIMENTAL** (no evidence of predictive power) | `KR_MODEL_*`, `P6-23_IMPLEMENTATION_REPORT.md` |
| P6-24 | Unified application | **PLANNED** | implemented (`--market`, dashboard) | `P6-24_IMPLEMENTATION_REPORT.md` |
| P6-25 | Separate paper tracking per market | **PLANNED** | implemented; KR observation started (10 PENDING_ENTRY) | `KR_TRACKING_SPECIFICATION.md`, `P6-25_IMPLEMENTATION_REPORT.md` |
| P6-12D | Institutional historical validation | **DEFERRED INDEFINITELY** | unchanged | no zero-cost survivorship-free PIT source |

**Renumbering note.** The earlier roadmap used "P6-21" for a US evidence-based research review. That review is kept, renamed **US evidence review (unnumbered)**, and still PLANNED. It starts only once there are ≥ 30 completed valid US observations from many independent scan dates, and its agenda includes the sector-cap decision (`P6-20_SECTOR_CAP_REVIEW.md`). Any model change needs explicit user approval.

### Previous phase table (preserved as written before the multi-market directive)

| Phase | Scope | Status | Evidence |
|---|---|---|---|
| P6-11B | Frozen mathematical core (factors, DEFAULT_FACTOR_WEIGHTS, MODEL_RANK_E, 500k ADV, 75th-pct BEAR, 30%/40% caps, entry/stop/horizon) | **FROZEN** | Engine sources unchanged since Aug 2026; sha256 pinned in `tests/fixtures/frozen_source_sha256_p6_19.json` (`TestFrozenSourcePinned`); numerical parity against the pre-change golden baseline (`tests/test_p6_18_frozen_core_parity.py`, 12 tests pass) |
| P6-17 | Live data and universe infrastructure (Wikipedia S&P 500 bootstrap, SEC CIK map, yfinance) | **Provider Tested** | P6-19 live runs: universe `SUCCESS/REAL` (503 constituents), CIK map `REAL`; `tests/test_p6_17_*` pass |
| P6-18 | Shared live recommendation pipeline (canonical route, run durability, Mode A/B) | **Full-Universe Validated (pipeline)**. The P6-18 run's *recommendation* was produced with defective inputs and is excluded from performance statistics (PRE_FIX, P6-20). | Pipeline re-validated by the P6-19 full runs. Run `20261104T071145Z_market_scan_e16f62`: TOP-5 identical to the pre-fix P6-19 run, $10M default capital. |
| P6-19 | Independent verification and operational hardening | **COMPLETE** (re-verified at the P6-20 baseline: frozen hashes match, latest run replays, exclusions intact). Open user actions: NewsAPI key rotation, optional removal of the Desktop copy. | `reports/P6-19_IMPLEMENTATION_REPORT.md`, `reports/P6-19_TEST_RESULTS.json`, `reports/P6-20_BASELINE_VERIFICATION.md` |
| P6-20 | Prospective performance validation and paper tracking | **COMPLETE** (tracking infrastructure). **Observation ongoing**: as of 2026-11-04 there is 1 valid run (5 TOP-5 observations), all PENDING_OUTCOME; there are no completed observations and no performance claim. | `reports/P6-20_IMPLEMENTATION_REPORT.md`, `reports/P6-20_TEST_RESULTS.json` (817 collected, 806 passed, 0 failed), `reports/P6-20_TRACKING_SPECIFICATION.md`, `reports/P6-20_SECTOR_CAP_REVIEW.md`, `tracking/ledger/` (hash chain verified) |
| P6-20-A | Addendum: approved data-input rules (A1–A7) and safe local git (B) | **COMPLETE**. Spec `P6-20-A` is in force for runs after commit `63c283d`. Local git on `main` (baseline `1e9472f`), with no remote and no push. | `docs/DATA_INPUT_SPECIFICATION.md`, `reports/P6-20_INPUT_VALIDATION_TEST_RESULTS.json` (837 passed, 0 failed), `docs/GIT_SETUP_REPORT.md`, validation run `20261104T125402Z_market_scan_5a396d` (replay MATCH) |
| (former P6-21, now "US evidence review") | Evidence-based research review | **PLANNED**, not scheduled automatically | Starts only once the prospective record holds ≥30 completed valid observations from many independent scan dates. It decides whether further research is justified. It is not an optimisation phase, and any model change requires explicit user approval. Agenda includes the sector-cap decision (`P6-20_SECTOR_CAP_REVIEW.md`). |
| P6-12D | Institutional historical validation | **DEFERRED INDEFINITELY** | Needs survivorship-free point-in-time constituents and fundamentals, which have no zero-cost source |

## History (completed, preserved)

- **P6-11A-REPAIR**: MODEL_RANK_E parity restoration, PIT leakage fix.
- **P6-11B**: Mathematical core finalised and permanently frozen.
- **P6-13.5**: Candidate-level quarantine, UNAVAILABLE semantics, graceful optional degradation.
- **P6-14 / P6-15 / P6-15.1**: Historical PIT preparation; data-acquisition blocker reviews.
- **P6-16**: Mock firewall, candidate quarantine, fail-safe short circuit.
- **P6-17 / P6-17.4 / P6-17.4.1**: Live universe and data readiness; canonical frozen route; runtime certification.
- **P6-17.5**: First 503-ticker live run (REAL RECOMMENDATION, 8,018 s). Superseded by P6-18.
- **P6-18** (2026-11-04): canonical shared pipeline, durable runs, Adj-Close blanking fix, SEC period alignment, ADV20, provider sector, provenance gate before normalisation. Full scan of 503 symbols in 194 s.
- **P6-19** (2026-11-04): independent verification and hardening. Highlights:
  - project moved out of the iCloud Desktop;
  - 12 tests and 6 scripts no longer hard-code the old Desktop path;
  - an offline test sandbox now protects user data;
  - the test inventory is reconciled (778 collected: 768 passed, 5 opt-in live skipped, 5 strict-xfail isolated, 0 failed);
  - the four input definitions are formally approved (`docs/DATA_INPUT_SPECIFICATION.md`);
  - there is no default capital, no fabricated SEC contacts, and SEC is never queried without a valid contact;
  - forward-tracking foundation added.
  - three input defects found in the full live run and fixed at the input layer: BRK-B Yahoo priceToBook (rejected as inconsistent), CPT revenue concept, and FITB/DTE/HBAN/MTB revenue slices. The frozen math was not touched.
- **P6-20** (2026-11-04): prospective performance validation and paper tracking.
  - Immutable hash-chained ledger (schema 2), built only from run artifacts, with append-only exclusion and correction events.
  - Cohorts: VALID_PROSPECTIVE / PRE_FIX_EXCLUDED / DATA_INVALID × PENDING / COMPLETED / INCOMPLETE.
  - NYSE calendar with early closes. Entry is the first open after the recommendation timestamp.
  - The frozen exit rules are applied via the unmodified `evaluate_existing_position`, with next-open fills.
  - SPY over identical windows; hypothetical cost scenarios.
  - Paper portfolios with the original weights and staged entries.
  - Read-only diagnostics.
  - Safe, replayable updates (`app.py tracking …`).
  - Sector-cap contract review: the Technology-only cap is the approved P6-11B rule and is unchanged.
  - The P6-18 run was added to the pre-fix exclusions.

## Corrections to earlier roadmap claims (P6-19)

- "154 deterministic tests pass" (P6-18) counted only `unittest`-style tests. The real inventory under pytest is 778 tests in 62 files (after P6-19 additions). Seven pytest-style modules had never been executed; two of them fail (legacy research engines, now isolated as strict xfail).
- "Remaining blockers: none" (P6-18) was inaccurate:
  - tests overwrote historical P6-9/P6-10 reports and production `data/*.db`;
  - 12 test modules imported code from the iCloud Desktop path;
  - the default capital was $10,000,000;
  - the default SEC contact was a placeholder. All are fixed in P6-19.
- "Sector cap enforced": true for **Technology only**. That is the frozen implementation; other sectors are not capped (frozen-core limitation, reported in every run, not changed).

## Corrections (P6-20)

- The P6-19 forward tracker measured from the scan's reference close, a price from **before** the recommendation timestamp. That is a look-ahead-prone entry. It is superseded by the P6-20 entry policy, and the schema-1 ledger is preserved but no longer written.
- The P6-18 full run was not excluded in P6-19, although its TOP-5 came from the same defective inputs. It is now excluded via an appended PRE_FIX event.
- `utils/market_calendar.py` (freshness gate) mis-handles New Year's Day falling on a Saturday (next occurrence 2027-12-31). It is documented and not changed (production path); the tracking calendar is correct.

- P6-19 input rules superseded by P6-20-A: revenue "largest same-period concept" (it could select a component, e.g. CPT lease income); the NI > revenue rejection (it rejected DTE although DTE tags a total-revenue concept); and the P/B check against annual-period equity with no scope, staleness or common-equity handling. Observations made under `P6-19-final` stay valid and are reported separately by spec version.

## Terminal and QSF status (2026-11-05)

| Phase | State | Evidence |
|---|---|---|
| TERMINAL-1..4 (market, stock, macro, portfolio, challengers, automation, Telegram, backup) | implemented, committed through `faf461a` | `reports/TERMINAL_4_SPECIFICATION.md` |
| QSF 1.1 scoring, holding-period and exit engine (US and KR) | implemented, **EXPERIMENTAL**; predictive power not validated | `reports/QSF_1_1_IMPLEMENTATION_REPORT.md` |
| Korean market in the terminal (market switch, won account, KR limits, DART company screen, ECOS macro, name search) | implemented, not yet used with real trades; ECOS needs the user's free key | README "Korean market in the terminal", `tests/test_kr_terminal.py` |

| Portfolio long-term and swing tagging, per-style limits, target weight, exit readings, alerts | implemented, tested | `tests/test_portfolio_style.py`, README section 5 |

The order the user set (automation, long and swing tags, Korean market) is complete.
QSF historical checks (2026-11-05): QSF 1.2 candidate NO_EVIDENCE (`reports/QSF_1_2_VALIDATION_RESULTS.md`); research score: no factor passed (`reports/QSF_RESEARCH_SCORE_RESULTS.md`). Live score stays QSF-1.1.2 with a notice.

## Next tasks (candidates, not started)

0. Multi-market:
   - configure the free `OPENDART_API_KEY` and `KRX_API_KEY` yourself (registration in the README);
   - after the keys are set: live-validate the KRX field mapping and measure DART concept coverage per industry class;
   - run the KR scan after 18:00 KST on trading days, and `--market KR tracking update` afterwards;
   - `tests/test_cross_asset.py` depends on live Yahoo macro moves and is reclassified as a non-running xfail (user approved, 2026-11-06). Still open: the network-guard gap (yfinance `curl_cffi` bypasses the Python socket guard).

1. Run a full scan on each trading day before 09:30 ET, then run `app.py tracking update` after 17:00 ET. Review `tracking/reports/latest.html`. No model changes.
2. Before 2027-12-31: decide whether to fix the New Year-on-Saturday rule in `utils/market_calendar.py` (freshness gate).
3. Optional: persist position state so the frozen `evaluate_existing_position` exit rules can run on actual holdings (read-only advice, no execution).
4. Done (P6-20-A): local git. Connecting a private GitHub remote requires your explicit approval (`docs/GIT_SETUP_REPORT.md` §7).
5. Optional input-coverage review (needs approval): 48 tickers have a P/B cross-check NOT_VERIFIABLE because companyfacts has no recent `StockholdersEquity` (e.g. AVGO tags only the NCI-inclusive concept). The Yahoo value is kept and labelled. Adopting another equity concept would be an input-definition change.
