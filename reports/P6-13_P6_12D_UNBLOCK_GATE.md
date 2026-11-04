# P6-13 P6-12D UNBLOCKING CRITERIA GATE

## 1. Core Gate Objective
The P6-12D Liquidity x BEAR Joint Statistical Revalidation MUST remain blocked until the local or central data architecture can guarantee the safe, bias-free provision of the target ~6,500 U.S. equities.

## 2. Explicit Unblock Criteria
The P6-12D statistical computation may run **ONLY** when:
- [ ] 1. Full target universe coverage (~6,500 tickers) is present in `historical_data.db` or Parquet files.
- [ ] 2. Historical daily price and volume arrays span at least 4 years continuously.
- [ ] 3. Security master accurately maps current and historical identifiers.
- [ ] 4. Delisted securities are fully included in the historical vectors to prevent survivorship bias.
- [ ] 5. Corporate actions are either pre-adjusted safely backwards or dynamically calculated from an immutable event table.
- [ ] 6. Historical fundamentals are strictly point-in-time (PIT), aligned to SEC filing acceptance dates.
- [ ] 7. Cross-sectional BEAR percentile (75th) is computable across a statistically robust sample size (thousands of tickers, not 50).
- [ ] 8. No synthetic or MOCK data exists anywhere in the testing pipeline.
- [ ] 9. Current-day financial snapshots are never assigned historical `as_of` dates.
- [ ] 10. `White's Reality Check` matrix operates strictly on real historical return streams.

## 3. Enforcement
These criteria must be embedded as unit tests or runtime assertions in the `P6-12D` orchestrator script before the final simulation executes.
