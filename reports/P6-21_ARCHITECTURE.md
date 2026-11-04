# P6-21 Multi-Market Platform Architecture

Date: 2026-11-04 · Principle: **share infrastructure, not model assumptions.**

The platform runs two independent engines side by side:

- **US**: the frozen P6-11B engine. It is unchanged byte for byte, and its sha256 hashes are pinned.
- **KR**: a new, separately specified South Korea engine, `KR-EXP-0.1`, with status EXPERIMENTAL.

They share only market-neutral infrastructure: run recording, the hash-chained ledger primitives, the report rendering helper, the CLI shell and the test sandbox. Nothing in the KR engine imports a frozen US module, and an architecture test enforces this. The two markets never share a universe, a factor definition, a normalisation, a portfolio rule, a ledger, a cohort or a currency.

## 1. Component inventory

| Component | Shared / US / KR | Location | Notes |
|---|---|---|---|
| Frozen math (factors, scoring, ranking, decision) | US only | `core/*.py`, `contracts/decision.py` | sha256 pinned (`tests/fixtures/frozen_source_sha256_p6_19.json`); not modified in P6-21..25 |
| US canonical pipeline | US only | `pipeline/canonical_pipeline.py` and friends | unchanged; P6-20-A input rules in force |
| Market identity | shared | `markets/identity.py` | `Market` enum; composite `SecurityId(market, exchange, symbol, currency, instrument_type, identifiers)`; key `MARKET:EXCHANGE:SYMBOL`. Market is never inferred from ticker format. |
| Market configuration | shared type, per-market values | `markets/config.py` | read-only mapping per market: calendar, timezone, currency, session, universe policy, providers, freshness, liquidity, financial rules, model, constraints, benchmark, entry policy, tracking, runs dir |
| Storage layout | shared | `markets/storage.py` | market-scoped paths and an additive, idempotent schema-v2 migration with a backup |
| Run recorder | shared (extended) | `pipeline/run_recorder.py` | new `market`, `stages` and `manifest_extra` arguments. US manifests keep every pre-P6-21 field, and the US default is unchanged. |
| Ledger primitives | shared | `pipeline/prospective_ledger.py` (`append_records`, `verify_chain`, `canonical_json`, `read_jsonl`) | the US eligibility gate now also rejects non-US manifests (`NOT_A_US_MARKET_RUN`) |
| US tracking (P6-20) | US only | `pipeline/prospective_tracking.py`, `tracking/ledger/…` | untouched; US ledger not reset, recreated or rewritten |
| KR security master | KR only | `markets/kr/security_master.py` | KRX KIND corpList (KOSPI + KOSDAQ) |
| KR calendar | KR only | `markets/kr/calendar.py` | KST; sessions observed from KOSPI index bars; a bar counts as complete only after 18:00 KST |
| KR market data | KR only | `markets/kr/market_data.py`, `markets/kr/acquisition.py` | canonical OHLCV rows with validation. Yahoo is supplementary (traded value is a labelled proxy); the KRX Open API adapter is key-gated. |
| KR financial data | KR only | `markets/kr/dart.py`, `markets/kr/account_mapping.py` | OpenDART adapter (key-gated). K-IFRS normaliser keeps CFS and OFS separate. XBRL-keyed account registry `KR-ACCT-0.1`. |
| KR universe | KR only | `markets/kr/universe.py` | liquid-300 by 20-session average traded value |
| KR model | KR only | `markets/kr/model.py` | independent price-factor model, EXPERIMENTAL |
| KR pipeline | KR only | `markets/kr/pipeline.py` | scan and direct evaluation; own stage list; durable run artifacts under `runs/KR/` |
| KR tracking | KR only | `markets/kr/tracking.py` | separate ledger `tracking/kr/`, KRW only, cohort `EXPERIMENTAL_PROSPECTIVE` |
| CLI | shared shell | `app.py` (+ `markets/kr/cli.py`) | `--market {US,KR}` (default US, so existing commands behave exactly as before) |
| Dashboard | shared, per-market panels | `markets/dashboard.py` | static read-only HTML; nothing is aggregated across markets |
| Test sandbox | shared | `tests/conftest.py` | offline by default; protects `data/ reports/ runs/ tracking/` |

## 2. Data flow

```
                     ┌──────────────── shared infrastructure ────────────────┐
                     │ identity · config · storage · RunRecorder · ledger    │
                     │ primitives · report HTML · CLI shell · test sandbox   │
                     └───────────────┬───────────────────────┬───────────────┘
                                     │                       │
   US (frozen)                       │                       │         KR (experimental)
   Wikipedia S&P 500 + SEC + Yahoo   │                       │   KIND corpList → security master
        │                            │                       │   Yahoo .KS/.KQ (proxy TV) | KRX API*
   canonical pipeline (P6-18/20-A)   │                       │        │ validate OHLCV → series checks
        │  frozen core/ math         │                       │   liquid-300 universe (ADTV20)
   runs/<run_id>/                    │                       │   gate → winsorised z → KR-EXP score
        │                            │                       │   TOP-10, ≤3 per KRX industry
   tracking/ledger (USD, SPY)        │                       │   runs/KR/<run_id>/
                                     │                       │   tracking/kr/ledger (KRW, ^KS11/^KQ11)
                                     └──── dashboard (two separate panels) ────┘
   * KRX Open API and OpenDART are used only when OPENDART_API_KEY / KRX_API_KEY are configured.
```

## 3. Isolation rules and how they are enforced

| Rule | Enforcement |
|---|---|
| The frozen US math is never modified | sha256 pin test (`test_frozen_core_hashes_unchanged`, plus the P6-19 pin test); KR modules may not import `core.*` (`test_kr_package_never_imports_frozen_core`) |
| US and KR observations never share a cohort | separate ledgers (`tracking/ledger` vs `tracking/kr/ledger`); the US gate rejects KR manifests; the KR gate rejects anything but `market == "KR"` |
| Currencies are never mixed | US capital `--capital` / `QPP_CAPITAL` (USD); KR capital `--capital` / `QPP_CAPITAL_KRW` (KRW). The KR CLI refuses to fall back to `QPP_CAPITAL`, and every KR record carries `currency: KRW`. |
| Market identity is composite | `SecurityId.key = MARKET:EXCHANGE:SYMBOL`. A 6-digit US-style symbol stays US (test). |
| US records without a market field | They are US by construction: every pre-P6-21 run was produced by the US canonical pipeline. Existing records are not rewritten, which keeps their hashes and the `verify` reconstruction intact. |
| Experimental observations are separate | KR cohort `EXPERIMENTAL_PROSPECTIVE`. Summaries are split by model version and data-spec version. |
| No KR requirement changes the US model | KR differences live in `markets/kr/*` only. The shared-file edits (`run_recorder.py`, `prospective_ledger.py`, `app.py`) are additive and default to the US behaviour. |

## 4. Storage layout (schema v2)

| Path | Market | Content |
|---|---|---|
| `runs/<run_id>/` | US | unchanged |
| `runs/KR/<run_id>/` | KR | manifest, execution status, validation result, candidate flow, universe snapshot, report |
| `tracking/ledger/`, `tracking/prices/`, `tracking/outcomes/`, `tracking/reports/` | US | unchanged (P6-20) |
| `tracking/kr/{ledger,prices,outcomes,reports}/`, `tracking/kr/updates.jsonl` | KR | KR paper tracking |
| `data/kr/security_master/`, `data/kr/cache/` | KR | KIND snapshots with source sha256; OHLCV caches |
| `tracking/STORAGE_SCHEMA.json` | both | schema version, history, backup path, rollback note |
| `tracking/dashboard.html` | both | generated read-only view |

The migration (`python app.py migrate-storage`) is additive: it only creates directories and the schema file. Before it ran, it wrote a tar.gz backup of `tracking/` to `~/Developer/qse-backups/`. It is idempotent (`ALREADY_CURRENT`). Rollback means deleting the new directories and the schema file; the US data is unaffected.

## 5. Shared-file changes (complete list)

| File | Change | US behaviour |
|---|---|---|
| `pipeline/run_recorder.py` | optional `market` (default "US"), `stages`, `manifest_extra`; adds `"market"` to the manifest; US-only fields written only for US | identical apart from the added `market: "US"` key |
| `pipeline/prospective_ledger.py` | eligibility adds `NOT_A_US_MARKET_RUN` for non-US manifests | identical for US runs |
| `app.py` | global `--market` (default US); `dashboard`, `migrate-storage` commands; KR routing | identical without `--market KR` |
| `tests/conftest.py` | allows the new junit output path | unchanged guard |

## 6. Known architectural limitations

- KR market data comes from Yahoo, which is supplementary, until `KRX_API_KEY` is configured. Its traded value is close × volume, labelled `PROXY_CLOSE_X_VOLUME`, and is not the official KRX 거래대금.
- The KR session calendar is the set of observed KOSPI index sessions. It is not an official holiday table: unannounced closures appear only after they occur.
- KR fundamentals (OpenDART) are specified, implemented and tested offline, but they are inactive in the model.
