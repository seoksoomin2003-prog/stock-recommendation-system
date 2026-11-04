# P5-4A / P5-5A Real Historical Data Acquisition & Provider Validation

## Final verdict

**C. NOT READY**

The P5 repository has been hardened for production ingestion, but no authoritative provider was successfully connected and no real historical data was acquired. P5-6 must not begin.

## Environment and audit

| Item | Result |
| --- | --- |
| OS / Python | macOS 15.5 arm64 / Python 3.14.2 |
| Network | DNS resolution failed for `data.sec.gov`, `data.nasdaq.com`, and `api.nasdaq.com` |
| Available packages | `requests`, `pandas`, `yfinance` |
| Unavailable packages | `duckdb`, `pyarrow`, `pytest` |
| Storage | SQLite remains the bounded, lazy P5 store; no dependency added |
| Historical production DB | Absent: 0 fundamentals, 0 prices, 0 actions, 0 securities |
| Security/universe DB | Schemas exist but have 0 states, identifiers, memberships, and actions |

The machine-readable audit is [P5-4A_P5-5A_PROVIDER_AUDIT.json](P5-4A_P5-5A_PROVIDER_AUDIT.json).

## Provider configuration and connectivity

| Provider | Configured | Reachable | Authenticated | Sample acquired | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| SEC official EDGAR | No `SEC_USER_AGENT` | No | No | No | UNAVAILABLE |
| Sharadar / Nasdaq Data Link | No credential | No | No | No | UNAVAILABLE |
| Norgate | No credential | Not probed (no credential) | No | No | UNAVAILABLE |

The legacy SEC provider's synthetic fallback was not used. Existing SEC cache contains only submissions/ticker metadata and is classified **CACHED metadata**, not real PIT fundamentals. Existing `research_cache.db` records are classified **current cache**, not PIT historical data.

## Changes delivered

- Added `OfficialSecHistoricalFinancialProvider` in `providers/historical.py`. It only calls official `data.sec.gov` after an injected/configured contactable User-Agent, has no synthetic fallback, is sequential, and caps local request rate at 2/s.
- It parses official companyfacts into `HistoricalFinancialFact` with CIK-backed accession, filing date, period, unit, source URL, fetch time, and provenance. `accepted_at` remains absent until filing-submission metadata enrichment is available; absent is not synthesized.
- Production `HistoricalDataRepository` now rejects any source containing `SYNTHETIC`, validates OHLC/volume, makes byte-identical source acquisition idempotent, and rejects conflicting duplicates.
- Snapshot provenance now records derived ROE/profit-margin source accessions and `as_of`; a derived value is only calculated from PIT-selected source facts.

No Quant formula, current `NormalizedData` path, execution code, portfolio code, MemoryGuard, or protected runtime file was modified.

## Real-data coverage / cross-provider validation

No provider passed authentication or returned a real sample. Therefore:

- REAL fundamentals: 0
- REAL price bars: 0
- REAL actions: 0
- REAL delisted securities: 0
- PIT InformationSet samples from real data: 0
- SEC vs Sharadar / price / action comparisons: not applicable

No fixture or synthetic record was written to a production historical repository.

## PIT, cache, identity, and data-integrity verification

Synthetic-only test fixtures validate: future filing rejection; accepted timestamp handling; amendment/restatement visibility; future price exclusion; ticker reuse and `security_id` isolation; delisted-price retention; corporate announcement/effective timing; raw versus adjusted price separation; deterministic hashes; derived-factor lineage; synthetic production ingestion rejection; immutable duplicate idempotency and conflict rejection; unavailable SEC provider semantics; and SEC record parsing provenance.

The repository query remains `security_id` and date constrained in SQLite. It does not load a universe into pandas and does not bypass MemoryGuard. The acquisition boundary is sequential and rate-limited. No measured real-provider latency, data-memory footprint, or cache hit rate is available because acquisition did not occur.

## Regression

- New P5 layer + P5-2/P5-3 targeted `unittest`: **51 passed**.
- `python3 -m unittest discover -s tests -q`: **exit 0**. Existing unrelated tests emit known network/fallback and SQLite ResourceWarning messages but did not fail.
- `pytest`: **unavailable**; not installed. It was not installed because network/DNS is unavailable.

## Known limitations and P5-6 gate

1. Configure a compliant `SEC_USER_AGENT`, restore DNS/network, and run a bounded official SEC probe with a security whose historical CIK mapping exists.
2. Configure a licensed Sharadar/Nasdaq or Norgate adapter to prove real survivorship-free price/delisting/action coverage.
3. Populate and validate historical security master and universe provider identifiers before ingesting real records.
4. Enrich SEC companyfacts accession records with submission acceptance timestamps when filing metadata is retrievable.
5. Acquire the specified small sample only after the above gate; do not bulk download.

Until authoritative fundamentals, delisted historical prices, and identity mappings exist, this system makes **no predictive-validity claim** and P5-6 remains blocked.
