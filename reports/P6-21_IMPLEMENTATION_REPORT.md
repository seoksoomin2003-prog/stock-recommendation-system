# P6-21 Implementation Report: Multi-Market Architecture

Date: 2026-11-04 · Status: **IMPLEMENTED and tested**. Design: `reports/P6-21_ARCHITECTURE.md`.

## Delivered

| Item | Location |
|---|---|
| Market enum and composite security identity (`MARKET:EXCHANGE:SYMBOL`) | `markets/identity.py` |
| Read-only per-market configuration (US-1, KR-0.1) | `markets/config.py` |
| Market-scoped storage, schema v2, additive idempotent migration with backup | `markets/storage.py`; executed once: `MIGRATED`, backup `~/Developer/qse-backups/tracking_before_storage_v2_20261104T135011Z.tar.gz` |
| Pre-change runtime backup | `~/Developer/qse-backups/before_p6_21_20261104/runtime.tar.gz` (645 entries, sha256 alongside) |
| RunRecorder generalised (market, stages, manifest extras; US default unchanged) | `pipeline/run_recorder.py` |
| US ledger refuses non-US runs (`NOT_A_US_MARKET_RUN`) | `pipeline/prospective_ledger.py` |
| Architecture tests | `tests/test_p6_21_multimarket.py` (10 tests) |

## Preservation evidence

- The frozen hashes of `core/factor_engine.py`, `scoring_engine.py`, `ranking_engine.py`, `decision_engine.py` and `contracts/decision.py` all match `tests/fixtures/frozen_source_sha256_p6_19.json`. `git diff` on `core/` and `contracts/` is empty.
- The US ledger was never reset, recreated or rewritten. It now holds 66 records, and verify reports the chain OK, every run's reconstruction MATCH, and the latest replay MATCH.
- Pre-P6-21 records carry no `market` field. They are US by construction (see the architecture document, §3).

## Errors found and fixed during implementation

- `migrate()` first resolved a relative base, which put the backup inside the project. The backup was moved to `~/Developer/qse-backups/`, `base` is now resolved, and the move is recorded in `STORAGE_SCHEMA.json`.
- A new app test called `app.main()`, which `chdir`s to the real project root. Later legacy tests then ran outside the sandbox. The guard detected every write and restored the files: `data/tickers.db` and `data/research_cache.db` were verified byte-identical to the backup. The test now restores the cwd through an autouse fixture.

## Tests

The P6-21 module passes 10 of 10. For the full suite, see `P6-21_TEST_RESULTS.json`.
