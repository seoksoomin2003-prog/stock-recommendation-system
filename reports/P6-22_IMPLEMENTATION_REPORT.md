# P6-22 Implementation Report: Korean Data Engine (`KR-DATA-0.1`)

Date: 2026-11-04 · Status: **IMPLEMENTED**.

- Live: KIND (master) and Yahoo (supplementary prices).
- Offline only: OpenDART and the KRX Open API. Their keys are not configured.

Specifications:

- `reports/P6-22_KR_DATA_SPECIFICATION.md`;
- `reports/P6-22_KR_ACCOUNT_MAPPING.md`.

## Modules

`markets/kr/`:

- `security_master.py`, `calendar.py`, `market_data.py` (validation, Yahoo provider, KRX adapter), `acquisition.py` (cache, windows);
- `dart.py` (OpenDART client, K-IFRS normaliser, point-in-time extraction), `account_mapping.py` (registry `KR-ACCT-0.1`);
- `universe.py` (liquid-300).

## Live data evidence (2026-11-04, KST evening, after the 18:00 bar-completion time)

| Item | Value |
|---|---|
| KIND master | 2,658 rows: 829 KOSPI and 1,829 KOSDAQ. 2,531 eligible. Exclusions: SPAC 70, REIT 25, foreign 19, collective investment 13. Snapshot sha256 stored. |
| Yahoo universe download (70 calendar days, 2,531 symbols) | 1,152 s (first fetch, cold) |
| Universe candidates with complete 20-session data | 2,418 |
| Universe exclusions | `STALE_LAST_BAR` 96 (Yahoo had no 2026-11-04 bar for these), `INSUFFICIENT_VALID_OBSERVATIONS` 11, `NO_MARKET_DATA` 6 |
| Liquid-300 | 300 members: **KOSPI 161, KOSDAQ 139** |
| ADTV20 (proxy) | cutoff 8.58 bn KRW, median member 25.1 bn KRW, largest member SK하이닉스 5.22 tn KRW |
| Traded-value basis | `PROXY_CLOSE_X_VOLUME` (Yahoo). The official 거래대금 needs `KRX_API_KEY`. |
| OpenDART | **UNAVAILABLE**: `OPENDART_API_KEY` is not set. No live statement was fetched and none was fabricated. |
| KRX Open API | **UNAVAILABLE**: an unauthenticated request returns HTTP 401 "Unauthorized Key" (verified). |
| `data.krx.co.kr` | HTTP 403 to scripted clients. Not used and not bypassed. |

## Data-quality statistics (live liquid-300 run `20261104T141806Z_kr_market_scan_c4ed3d`)

- Members scored: 294 of 300.
- Quarantined before normalisation: 6, all `INSUFFICIENT_HISTORY_FOR_REQUIRED_FACTORS` (recent listings with fewer than 127 sessions).
- Invalid rows are set to NaN, never 0. Stale members are excluded from the universe; they are never presented as fresh.

## Offline coverage (`tests/test_p6_22_kr_data.py`, 33 tests)

- KIND parsing: leading zeros, alphanumeric codes, the layout-change guard, snapshot and cache, and a failed fetch never being fabricated.
- Classification: SPAC, REIT, fund, foreign issuer, financial classes, market-label mismatch, duplicates.
- OHLCV validation: 6 parametrised invalid-row cases, duplicates; series checks for stale, halted and corporate actions.
- Yahoo provider: the proxy is labelled, and failed chunks are recorded.
- KRX adapter: official traded value, layout guard, key confined to the header and absent from errors, provider selection.
- OpenDART:
  - missing key, status codes, the key never leaking, corpCode ZIP parsing;
  - annual, quarterly and balance-sheet normalisation and derived fiscal periods (including March year ends);
  - concept extraction: REAL, VALUE_MISSING ≠ 0, NOT_APPLICABLE for banks;
  - basis separation, the receipt-date point-in-time rule, ambiguity handling, CFS → OFS fallback labelling, registry structure.
- Calendar: bar completion and signal classification.
- Universe: ranking, every exclusion reason, stability.

## Limitations

- The traded value is a proxy.
- The session calendar is observed from index bars, not taken from an official holiday file.
- 관리종목 and halt flags are not in KIND corpList, so halts are only suspected (from 3 zero-volume sessions).
- The KRX daily field mapping (`ISU_CD` = 6-digit code) follows the published service specification and is unverified live until a key exists.
- The DART account registry has no live coverage measurement yet.
