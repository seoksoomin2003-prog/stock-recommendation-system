# Multi-Market Quantitative Platform: Final Report (P6-21 … P6-25)

Date: 2026-11-04 (KST evening / UTC afternoon) · Repository: `~/Developer/quant-stock-engine` (local git, branch `main`, no remote, nothing pushed)

## 1. Summary

The platform now runs two independent engines behind one CLI.

- **US:** the frozen P6-11B engine, unchanged.
- **KR:** a new KOSPI + KOSDAQ engine with its own data, universe, model (`KR-EXP-0.1`, EXPERIMENTAL) and paper tracking.

The two share infrastructure only: identity, configuration, storage, run recording, ledger primitives, CLI, dashboard and test sandbox.

Live validation passed in both markets. Contamination checks are clean, and every frozen hash matches.

OpenDART and the KRX Open API are implemented but **blocked by missing free API keys**. As a result, KR runs on supplementary Yahoo prices with a labelled traded-value proxy, and KR fundamentals are inactive.

## 2. Frozen-core and artifact hashes (sha256, first 16 hex)

Frozen core (all **match** the pins in `tests/fixtures/frozen_source_sha256_p6_19.json`; `git diff core/ contracts/` is empty):

| File | sha256 |
|---|---|
| `core/factor_engine.py` | `d84820f82eda45ce` |
| `core/scoring_engine.py` | `0f42f8401b269616` |
| `core/ranking_engine.py` | `2b354792de5d5eb1` |
| `core/decision_engine.py` | `074f5180426eacdb` |
| `contracts/decision.py` | `3339af551c0dd7f2` |

New modules, as committed:

| File | sha256 |
|---|---|
| `markets/identity.py` | `a3889defcbd1e2ff` |
| `markets/config.py` | `1aecf79b9ac84e0c` |
| `markets/storage.py` | `1c04182c60df6e0e` |
| `markets/dashboard.py` | `654b00748ddf7495` |
| `markets/kr/security_master.py` | `c46226f06e5d46ad` |
| `markets/kr/market_data.py` | `580b791600f64871` |
| `markets/kr/dart.py` | `bc6eb1e009a0e6be` |
| `markets/kr/account_mapping.py` | `1be190c914c656d2` |
| `markets/kr/universe.py` | `196e15ed25a83630` |
| `markets/kr/model.py` | `88b7a4b8eb3b8f42` |
| `markets/kr/pipeline.py` | `e403ae3bc5cfafbf` |
| `markets/kr/tracking.py` | `8feac47521daac5a` |
| `research/kr_factor_study.py` | `07a14d89eb9fb48e` |
| `reports/KR_FACTOR_STUDY_RESULTS.json` | `0e55b2f5c422de47` |

Ledger heads (last `record_hash`):

- US `tracking/ledger/observations.jsonl`: `f21ee022e49fd657`
- KR `tracking/kr/ledger/observations.jsonl`: `211fb17ead8c1a96`

Live validation results:

- KR run `c4ed3d` `validation_result.json`: `9607ad658bfc5a01`
- US run `7dbbfd`: `a860808a2e8b3eeb`

## 3. P6-20 preservation

- The US ledger was not reset, recreated or overwritten. It is append-only: 66 chain rows, the chain is OK, and all 6 runs reconstruct **MATCH**.
- The latest update `20261104T143205Z_644865` replays **MATCH**.
- Exclusions are intact: 3 PRE_FIX runs, including P6-18, plus `tracking/excluded_runs.json`.
- The P6-20-A spec is in force.
- US records carry no market field and are US by construction (`US_TRACKING_SPECIFICATION.md`).
- The only change to US behaviour: the US ledger now also refuses non-US manifests.
- Backups:
  - `~/Developer/qse-backups/before_p6_21_20261104/runtime.tar.gz`;
  - `~/Developer/qse-backups/tracking_before_storage_v2_20261104T135011Z.tar.gz`.

## 4. KR data coverage and universe

| Item | Value |
|---|---|
| Security master (KIND) | 2,658 listings (KOSPI 829, KOSDAQ 1,829); **2,531 eligible**; excluded: SPAC 70, REIT 25, foreign issuer 19, collective investment 13 |
| Market-data candidates (complete 20-session window) | 2,418 |
| Universe exclusions | STALE_LAST_BAR 96 (no 2026-11-04 Yahoo bar), INSUFFICIENT_VALID_OBSERVATIONS 11, NO_MARKET_DATA 6 |
| **Liquid-300 composition** | **KOSPI 161 / KOSDAQ 139** |
| ADTV20 (proxy close × volume) | cutoff 8.58 bn KRW; median 25.1 bn KRW |
| OpenDART fundamentals | **UNAVAILABLE** (no key) |
| KRX official prices and traded value | **UNAVAILABLE** (no key; HTTP 401 verified) |

## 5. Data-quality statistics (live KR run `20261104T141806Z_kr_market_scan_c4ed3d`)

- Scored: 294 of 300.
- Quarantined before normalisation: 6, all for insufficient factor history.
- STALE members: 0 (stale names were already removed at universe construction).
- Unfunded positions at 10M KRW: 1 (삼성전기, 1,115,000 KRW per share).
- Invalid rows are set to NaN, never 0. MOCK data appears only in the offline test fakes (`tests/kr_fakes.py`).

## 6. Contamination check (live tree)

| Check | Result |
|---|---|
| US ledger records with market ≠ US | 0 |
| KR ledger records with market ≠ KR / currency ≠ KRW | 0 / 0 |
| KR cohorts present | `EXPERIMENTAL_PROSPECTIVE` only |
| Run IDs present in both ledgers | none |
| US ledger runs located under `runs/KR` | none |
| Manifest markets in `runs/` / `runs/KR/` | US only / KR only |
| All four hash chains (US observations and events, KR observations and updates) | OK |

## 7. Test inventory (full offline suite, final code)

Command: `.venv/bin/python -m pytest tests -q -p no:cacheprovider --junitxml=<abs>/reports/P6-21_25_pytest_junit.xml`

| Collected | Passed | Failed | Errors | Skipped | xfailed | Collection errors |
|---|---|---|---|---|---|---|
| 923 | 911 | **1** | 0 | 6 | 5 | 0 |

New tests (75, all passing):

| Module | Tests |
|---|---|
| `test_p6_21_multimarket.py` | 10 |
| `test_p6_22_kr_data.py` | 33 |
| `test_p6_23_kr_model.py` | 14 |
| `test_p6_24_app.py` | 7 |
| `test_p6_25_kr_tracking.py` | 11 |

Every one of the 848 test cases from the P6-20-A baseline is still collected (junit name diff: none missing). 848 + 75 new = 923.

**The single failure is pre-existing and is not a regression:** `tests/test_cross_asset.py::test_cross_asset_adjustment`.

- This legacy test asserts the direction of a macro adjustment computed from **live** Yahoo rate data.
- yfinance's `curl_cffi` transport uses native sockets, which bypass the suite's Python socket guard. The test is therefore not deterministic.
- Run at the P6-20-A commit `32878c3` (in a temporary worktree) with today's data, it gives the same adjusted TSLA value of 0.505, which is above 0.5.
- It has not been weakened or reclassified. See §12.

Per-phase result files: `reports/P6-21_TEST_RESULTS.json` … `P6-25_TEST_RESULTS.json`.

## 8. Live evidence (sequential, never concurrent)

| Run | Market | Scope | Result |
|---|---|---|---|
| KR factor study | KR | 300 names × 27 periods | MOM_6_1, REV_1M and LOWVOL_60 kept; TREND_50 dropped (redundant); **no factor has \|t\| > 1** |
| `20261104T141806Z_kr_market_scan_c4ed3d` | KR | **full liquid-300** | REAL RECOMMENDATION. TOP-10: 001820, 095610, 009150, 066570, 000500, 222800, 080220, 078930, 119850, 036930 (KOSPI 5 / KOSDAQ 5). Tracked: 10 observations, PENDING_ENTRY. |
| `20261104T142038Z_kr_direct_evaluation_15ab1f` | KR | evaluate | 005930 rank 30; 000660 rank 26; 035720 rank 106; 999999 NOT_FOUND |
| `20261104T142045Z_kr_market_scan_432753` | KR | bounded (60) | PARTIAL; not tracked |
| KR `tracking update` / `verify` | KR | n/a | COMPLETE (10 PENDING_ENTRY) / chains OK, reconstruction MATCH, replay MATCH |
| `20261104T143042Z_market_scan_ed2a62` | US | bounded (25) | REAL RECOMMENDATION (bounded; not tracked) |
| `20261104T143051Z_market_scan_7dbbfd` | US | **full S&P 500 (503)** | REAL RECOMMENDATION. TOP-5: CL, SNDK, MU, AES, CHTR (identical to the P6-20-A validation run). 433 eligible, 5 tradable. KVUE had no Yahoo data. |
| US `tracking update` / `verify` | US | n/a | COMPLETE as of NYSE session 2026-11-03 (15 valid PENDING_OUTCOME) / verify OK |

The KR live scan ran before two later code changes: the unfunded-position flag and NaN→null in the evaluate output. Neither affects selection or tracked fields. The full suite ran on the final code.

## 9. Runtime and memory (M2, 8 GB)

| Job | Wall time | Peak RSS |
|---|---|---|
| KR factor study (cold download: 2,531 symbols plus 3.2 years of history for 300) | 1,152 s | 272 MB |
| KR full scan (same-day universe cache; 300-symbol history fetched) | 74 s | 213 MB |
| KR bounded scan (60) | 37 s | n/a |
| US full scan (fundamentals cache warm) | 65 s | 160 MB |
| Full offline test suite | 213 s | 368 MB |

A **cold** KR full scan, the first of the KST day, needs the about 18-minute universe download. Disk: 6.1 GiB free (72% used). New data: `data/kr` 11 MB, `runs/KR` 0.5 MB, `tracking/kr` < 0.1 MB.

## 10. Startup and scan commands

```bash
cd ~/Developer/quant-stock-engine
.venv/bin/python app.py doctor
.venv/bin/python app.py scan --capital 50000                       # US full S&P 500 (unchanged)
.venv/bin/python app.py tracking update && .venv/bin/python app.py tracking verify
.venv/bin/python app.py --market KR scan --capital 10000000        # KR liquid-300 (KRW), after 18:00 KST
.venv/bin/python app.py --market KR evaluate 005930 000660
.venv/bin/python app.py --market KR tracking update
.venv/bin/python app.py --market KR tracking verify
.venv/bin/python app.py dashboard --open
```

## 11. Required API keys (all free; you register yourself; never sent through chat)

| Variable | Where | Effect when missing |
|---|---|---|
| `SEC_USER_AGENT` (existing) | your contact identity per the SEC fair-access policy | SEC is not queried (US) |
| `OPENDART_API_KEY` | <https://opendart.fss.or.kr/>, then 인증키 신청 (free; normally 20,000 requests/day) | KR fundamentals UNAVAILABLE; model stays price-only |
| `KRX_API_KEY` | <https://openapi.krx.co.kr/>: sign up, issue a key, then apply for the 유가증권 / 코스닥 일별매매정보 services | KR prices fall back to Yahoo (supplementary); traded value is a proxy |

Put the keys in `.env` (git-ignored) or your shell profile. They are read only from the environment, never logged, and never written to artifacts. Terms: only the request limits stated in the official guides were checked. These sources are not described as unrestricted.

## 12. Blockers and open issues

1. **No OpenDART / KRX keys.**
   - Blocked: live DART coverage, live KRX field verification, official traded value, and any fundamental KR factor.
   - Needs: the user to register the keys.
2. **Legacy live-data test** (`test_cross_asset.py`) fails on today's macro data, and yfinance `curl_cffi` bypasses the network guard. Two decisions need your approval:
   - mark that test as a live-only test;
   - extend the guard to `curl_cffi`.
3. **The KR model has no predictive evidence.** It stays EXPERIMENTAL until the gates in `KR_MODEL_SPECIFICATION.md` §6 are met.
4. **KR data caveats:**
   - Yahoo was missing the latest bar for 96 names (excluded as stale);
   - the session calendar is observed, not official;
   - halts are only suspected;
   - KIND groups financial holding companies under "기타 금융업".
5. **US:** three valid runs from the same session, so the observations are not independent. The New Year-on-Saturday freshness rule is still open, from P6-20.
6. **Disk** is tight (6.1 GiB free).

## 13. Readiness classification (independent)

| Scope | Classification | Basis |
|---|---|---|
| **US** | **READY FOR CONTROLLED PERSONAL USE** | Frozen engine unchanged; full live scan REAL; tracking verify and replay MATCH; 0 regressions. Not a performance claim: 0 completed observations. |
| **KR** | **EXPERIMENTAL PAPER OBSERVATION** | Full live liquid-300 scan REAL and tracked, KRW, isolated. But the model is unvalidated, has no predictive evidence and runs on supplementary data, with official sources blocked by missing keys. |
| **Unified platform** | **READY FOR CONTROLLED PERSONAL USE** | Market selector, dashboard, storage v2 and isolation verified live and by tests; the KR panel is clearly labelled EXPERIMENTAL. |

## 14. Commits (local only)

The milestone commits are listed by `git log` on `main`. No remote exists and nothing has been pushed. Commit messages end with the Co-Authored-By trailer.
