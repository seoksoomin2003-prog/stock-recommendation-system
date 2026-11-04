# P6-14 Provider Semantics Review

## Verdict: ENFORCED

1. **REAL**: Data obtained from canonical historical sources (SEC, Stooq, etc.) passing validation.
2. **PARTIAL**: Real data with missing fields.
3. **UNAVAILABLE**: Provider failure, API outage, missing record, insufficient history.
4. **MOCK**: Synthetic fallbacks (strictly forbidden).

**Rule Enforced**: Missing data maps to UNAVAILABLE. MOCK data is quarantined and never allowed in historical statistical validation.
