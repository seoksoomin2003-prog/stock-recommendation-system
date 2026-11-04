# P5-4 / P5-5 Historical Data Layer Implementation Report

## Verdict

**B. READY WITH CONDITIONS**

The repository and PIT contract are independently testable and do not alter the Quant or execution runtime. It is not ready to feed P5-6 with real historical coverage until an authoritative acquisition adapter and real data are available.

## Mandatory read-only audit

| Area | Result |
| --- | --- |
| Historical Security Master / universe | SQLite schemas exist, but local tables contain 0 historical states, identifiers, memberships, and actions. |
| Existing `NormalizedData` | Versioned status contract exists; P5 intentionally does not translate into it. |
| Existing market/financial providers | yfinance supports current market history but marks historical financial `as_of` as unavailable. |
| SEC cache | AAPL submissions and ticker mapping cached; no companyfacts/fundamental fact cache. Legacy SEC fallback can simulate records, therefore excluded. |
| `research_cache.db` | 22 financial and 22 market cache records exist; these are current provider cache metadata, not PIT historical fact/price repositories. |
| Historical fundamentals/prices/actions | No Parquet or actual historical fact, delisted-price, or corporate-action dataset found. |
| Provider credentials | Sharadar/Nasdaq Data Link and Norgate keys missing. SEC User-Agent configuration missing. |
| Dependencies | `duckdb` and `pyarrow` unavailable; SQLite chosen for indexed, lazy local storage. |
| Quant factor input | Existing engine expects `per`, `pbr`, `roe`, `profitMargin`; no formula changed. |

Network/DNS was unavailable while attempting to install the missing test dependency, so live SEC reachability cannot be asserted. No real provider request was represented as successful.

## Delivered implementation

- `contracts/historical_data.py`: financial facts/snapshots, price bars, corporate actions, and deterministic PIT information set.
- `entity/historical_data_repository.py`: separate indexed SQLite store at `data/historical_data.db` when instantiated. It stores no generated production records.
- `providers/historical.py`: configuration-driven availability registry with explicit `UNAVAILABLE` semantics; no provider is hard-coded into Quant.
- `research/historical_information.py`: joins the existing historical security master/universe state to P5 data by `security_id`.
- `docs/P5_HISTORICAL_DATA_LAYER_CONTRACT.md`: schema, PIT, provider, price-adjustment, and P5-6 boundary policy.

## PIT and provenance correctness

Financial eligibility requires `period_end <= as_of`, `filed_at <= as_of`, and `accepted_at <= as_of` when present. Selection is deterministic and favours the latest eligible report version; later amendments/restatements cannot leak into earlier snapshots. Derived ROE/profit margin are made only from selected, PIT-eligible sources. Missing data stays `None`.

Prices are queried by `security_id`, bounded by bar date, and retain raw `close` and `adjusted_close` separately. Corporate events become information-visible at `announced_at`, or `effective_at` if unannounced; the effective date is retained independently. Facts and snapshot provenance retain source, source ID, accession number, filing/acceptance/observation times, units, and period type. Snapshot hashes are canonical SHA-256 values.

## Provider availability matrix

| Provider | Domain | Availability | Reason |
| --- | --- | --- | --- |
| SEC EDGAR | Fundamentals | UNAVAILABLE | no compliant configured User-Agent; legacy simulated fallback rejected |
| Sharadar / Nasdaq Data Link | Fundamentals, prices, actions | UNAVAILABLE | credential missing; adapter not installed |
| Norgate | Universe, prices, actions | UNAVAILABLE | credential missing; adapter not installed |
| Local SEC submissions cache | Filing metadata only | CACHED (metadata) | no historical financial facts |

No synthetic record was written outside `TEST FIXTURE / SYNTHETIC` tests.

## Verification

- `python3 -m unittest tests.test_historical_data_layer tests.test_historical_security_master tests.test_historical_universe`: **46 passed**.
- `python3 -m unittest discover -s tests`: exited **0**.
- Python compile check for all new modules: **passed**.
- P5 adversarial coverage: future financial/SEC filing, amendment/restatement timing, accepted timestamp, instant/duration guard, missing data, delisted price/security isolation/ticker reuse, future price, corporate-action timing, raw-versus-adjusted prices, and snapshot reproducibility.

The full pytest suite could not be invoked because `pytest` is not installed and dependency installation failed due unavailable DNS. This is an environment limitation, not a passing pytest result.

## Performance, cache, and memory

The new repository uses SQLite indexes and SQL `security_id`/date predicates, so reads are lazy and column/row bounded; it does not load a full dataset into pandas or bypass `MemoryGuard`. No production dataset exists, so meaningful measured dataset memory or latency is unavailable. Cache state is not fabricated: local source data is absent and returned as `UNAVAILABLE` through the provider registry.

## Limitations and rollback

- An official SEC companyfacts/submissions acquisition adapter, preserving accepted timestamps, remains to be implemented after a compliant User-Agent is configured.
- Delisted price and authoritative action ingestion require Sharadar/Norgate (or another approved authoritative adapter) and entitlement.
- Unit conversion across incompatible XBRL units is intentionally rejected rather than inferred.
- P5-6 translation, survivorship-free backtesting, and validation are not implemented.

Rollback is additive: remove the four new P5 modules and the new test/document files. No existing database schema, Quant formula, provider orchestration, execution code, or protected core module was modified. If instantiated, `data/historical_data.db` is a separate P5-only store and can be preserved or removed independently after confirming it contains no needed acquired data.

## Predictive-validity impact / P5-6 gate

The layer prevents identified look-ahead paths in its own contracts, but it does not improve predictive validity until real PIT facts and delisted prices are ingested. Enter P5-6 only after configuring and validating at least one authoritative fundamentals source and one historical price/action source, then rerunning the complete pytest regression suite.
