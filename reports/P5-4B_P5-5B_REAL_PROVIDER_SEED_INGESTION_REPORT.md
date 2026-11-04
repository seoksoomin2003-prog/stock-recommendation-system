# P5-4B / P5-5B Real Provider Connectivity + Historical Seed Ingestion Gate

## Final verdict

**C. NOT READY**

The real acquisition gate is blocked before provider requests: no eligible provider is configured and all tested provider domains return DNS failure. No real records, PIT snapshots, delisted securities, or corporate actions were acquired. P5-6 remains blocked.

## 1–5. Environment, network, configuration, connectivity, authentication

| Provider | Credential/config | DNS | TCP/TLS | Authentication | Sample request | Status |
| --- | --- | --- | --- | --- | --- | --- |
| SEC EDGAR | `SEC_USER_AGENT` missing | DNS_UNAVAILABLE | NOT_ATTEMPTED | NOT_ATTEMPTED | NOT_ATTEMPTED | UNAVAILABLE |
| Sharadar / Nasdaq Data Link | API key missing | DNS_UNAVAILABLE | NOT_ATTEMPTED | NOT_ATTEMPTED | NOT_ATTEMPTED | UNAVAILABLE |
| Norgate | API key/access missing | DNS_UNAVAILABLE | NOT_ATTEMPTED | NOT_ATTEMPTED | NOT_ATTEMPTED | UNAVAILABLE |

The deterministic diagnostic stops at DNS and has a two-second bound. It does not alter DNS, install networking software, use a VPN, or repeatedly retry. Python 3.14.2 is running on macOS arm64. `requests`, `pandas`, and `yfinance` are present; `duckdb`, `pyarrow`, and `pytest` are unavailable. No dependencies were added.

## 6–12. Actual seed coverage

| Coverage | REAL | CACHED PIT data | STALE | FALLBACK | UNAVAILABLE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Security Master validation sample | 0 | 0 | 0 | 0 | 5 requested identities unavailable |
| Historical universe memberships | 0 | 0 | 0 | 0 | unavailable |
| Financial facts | 0 | 0 | 0 | 0 | unavailable |
| Price bars | 0 | 0 | 0 | 0 | unavailable |
| Delisted securities | 0 | 0 | 0 | 0 | unavailable |
| Corporate actions | 0 | 0 | 0 | 0 | unavailable |
| Real PIT InformationSets | 0 | 0 | 0 | 0 | unavailable |

The local security-master and universe tables have zero rows. The local SEC files are **CACHED metadata** (submissions/ticker mapping), not PIT facts. `research_cache.db` contains current runtime cache entries and is not seed history. No current 12-ticker survivor universe was substituted as a historical universe.

## Offline implementation and invariants

- Added `SecUserAgentConfig`: environment-only configuration, fail-closed behavior, no logging or rendering of User-Agent value.
- Added a bounded DNS/TCP/TLS `diagnose_connectivity` contract with statuses `DNS_UNAVAILABLE`, `NETWORK_UNAVAILABLE`, `AUTH_REQUIRED`, `AUTH_FAILED`, `REACHABLE_BUT_NO_DATA`, `CONNECTED`, and `SCHEMA_INVALID`.
- SEC provider remains isolated from the legacy synthetic SEC path. It requires the fail-closed config, is sequential, uses a 2 requests/sec local cap, and retains official-companyfacts provenance when an authenticated source becomes reachable.
- Production historical repository now rejects missing `security_id`, provider/source/source-id provenance, `SYNTHETIC`, invalid OHLC/volume, and conflicting source duplicates. Exact immutable duplicate ingestion is idempotent.
- Fixture-only tests retain the explicit **TEST FIXTURE / SYNTHETIC** marker and can only opt in through `allow_synthetic=True`.

## PIT, amendment/restatement, identity, cache, and cross-provider results

Offline fixtures pass future fact and price rejection, amendment/restatement visibility, accepted timestamp handling, corporate-action announcement/effective-time separation, ticker reuse/security isolation, deterministic snapshot hashing, derived-factor PIT lineage, and production synthetic/provenance rejection.

No historical identity mapping, historical universe reconstruction, real delisting retention, or real corporate-action timing can be validated without a source-backed seed. Cross-provider classification is **MISSING / not applicable** because no overlapping authoritative sample exists. Cache/idempotency is validated for immutable repository records only; no network cache hit can be measured.

## Memory and performance

No bulk dataset was downloaded. Diagnostics are one sequential bounded operation per provider. SQLite remains lazy and constrained by `security_id`/date predicates; MemoryGuard was not modified. Real-acquisition latency and dataset memory use are unavailable because no record was retrieved.

## Regression

- Targeted P5 layer + historical security/universe tests: **54 passed**.
- `python3 -m unittest discover -s tests -q`: **exit 0**.
- `pytest`: **PYTEST_UNAVAILABLE**; it was not installed because the environment cannot resolve provider/internet domains.

## Exact blockers and P5-6 gate

1. Configure a compliant, contactable `SEC_USER_AGENT` in the runtime environment (do not put it in source control).
2. Restore DNS/network access to `data.sec.gov`, then run one bounded official SEC CIK probe.
3. Configure and authenticate a licensed Sharadar or Norgate source for prices, corporate actions, historical universe membership, and at least one real delisted security.
4. Seed real historical security identities/provider identifiers before fact/bar ingestion.
5. Acquire the requested bounded five-security sample only after steps 1–4.

Until every mandatory real-data condition is satisfied, this platform makes no predictive-validity claim and must not start P5-6.

## Files changed / created

- Modified: `providers/historical.py`, `entity/historical_data_repository.py`, `tests/test_historical_data_layer.py`.
- Created: this report.
- Dependencies added: none.
