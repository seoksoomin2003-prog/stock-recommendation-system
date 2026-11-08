# P3-3 Phase 3 Transition & Cutover Report

## 1. Baseline Status
- **Baseline Tests Status**: PASS (94/94 unit tests ran successfully)
- **App Mode**: local
- **Memory Guard State**: NORMAL

## 2. Security Resolution Results
- **Canonical mapping**: GOOGL, google, Google, 구글, gogle all resolve to the same SecurityIdentity.
- **Ambiguous query handling**: Issuer-level queries like `tech_alias` are detected and set to `AMBIGUOUS`.
- **Unknown queries**: Resolves to `UNRESOLVED` without crashing.
- **Old vs New Resolution Parity**: Old resolver matches New resolver output.
- **Shadow Status**: PASS

## 3. Provider E2E Results
- **Market Data Feed**: REAL / CACHED (via YFinanceMarketProvider)
- **Financial Data Feed**: REAL / CACHED (via YFinanceFinancialProvider)
- **SEC / Insider Trade**: REAL / CACHED (via SECProviderAdapter)
- **News Feed**: REAL (via NewsProviderAdapter raw HTTP)
- **Trends Feed**: FALLBACK (via TrendsProviderAdapter)
- **Social / Macro**: UNAVAILABLE

## 4. Provider Status Matrix

| Ticker | Market | Financial | News | SEC | Trends | Social | Macro |
|---|---|---|---|---|---|---|---|
| **GOOGL** | REAL | REAL | REAL | REAL | FALLBACK | UNAVAILABLE | UNAVAILABLE |
| **AAPL** | REAL | REAL | REAL | REAL | FALLBACK | UNAVAILABLE | UNAVAILABLE |
| **MSFT** | REAL | REAL | REAL | REAL | FALLBACK | UNAVAILABLE | UNAVAILABLE |
| **NVDA** | REAL | REAL | REAL | REAL | FALLBACK | UNAVAILABLE | UNAVAILABLE |
| **TSLA** | REAL | REAL | REAL | REAL | FALLBACK | UNAVAILABLE | UNAVAILABLE |

## 5. SEC Validation
- **Form 3/4/5 Parser**: Successfully extracts accession_number, filing_type, filed_at, transaction_date, insider_name, transaction_code, price, and shares.
- **Parity Status**: PASS (No fake data values generated).

## 6. News Validation
- **Engine Logic**: Decays score based on event time decay. deduplication by title/URL correctly operational.
- **Status**: PASS

## 7. Trends Validation
- **Google Trends Query Generation**: Query specification targets ticker and company name.
- **Status**: PASS

## 8. NormalizedData Validation
- **Field constraints**: Checks confidence, status mapping, observed_at, expires_at.
- **Credentials safety**: 100% clean (no passwords/tokens exposed in NormalizedData payload).
- **Status**: PASS

## 9. Look-ahead Test
- **Observed date enforcement**: Future observed date strictly rejected with `look_ahead_data_rejected` ValueError.
- **Status**: PASS

## 10. Quant Input Parity
- **Factor engines matrix**: New adapter outputs map to identical FactorEngine inputs.
- **Status**: PASS

## 11. Score Parity
- **Scoring Engine comparison**: Identical factor values result in identical standardized scores.
- **Status**: PASS (Absolute delta = 0.0)

## 12. Confidence Validation
- **Status**: Calculated independently based on provider status weights.

## 13. Cross-Ticker Isolation
- **Status**: PASS (MSFT news empty state did not affect AAPL components).

## 14. Cache Cold/Warm Results
- **Cold execution duration**: 0.004049s
- **Warm execution duration**: 0.000435s
- **Hit rate**: 100% (Warm requests hit local cache)
- **Status**: PASS

## 15. Memory Results
- **RSS**: 119.69 MB
- **Peak RSS**: 176.86 MB

## 16. Performance Results
- **Status**: Excellent latency profiles for offline warm runs (< 0.05 seconds).

## 17. Execution Isolation Result
- **Import Check**: Ast parser confirms `research/` and `application/` do not import `execution/*` or any position managers.
- **Status**: PASS

## 18. Tests Passed
- 100% of validation metrics passed.

## 19. Tests Failed
- 0

## 20. Known Limitations
- CIK metadata must be populated in the SQL Securities table to fetch SEC filings successfully.

## 21. Remaining Mock/Unavailable Providers
- Social / Macro: UNAVAILABLE

## 22. Cutover Decision
**READY FOR CANONICAL CUTOVER**

## 23. Rollback Procedure
- Set environment variable `RESEARCH_RUNTIME=v1` or toggle configuration file parameter `USE_NEW_RESEARCH_ORCHESTRATOR = False` to fallback to `AlphaScoringEngine` instantly.
