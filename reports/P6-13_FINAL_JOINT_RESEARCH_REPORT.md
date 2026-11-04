# P6-13 FINAL JOINT RESEARCH REPORT

## A. Executive Summary
The P6-13 Joint Research phase conducted a comprehensive data forensic, pipeline audit, and architectural design exercise. The objective was to unblock the P6-12D statistical validation while ensuring the Live Recommendation pipeline is stable and safe. The primary finding is that the P6-12D validation remains blocked by severe data scarcity (only 50 tickers available). The live pipeline experienced failures due to poor `yfinance` handling of empty data, propagating 0s into the Liquidity Filter, and masking MOCK fundamental data.

## B. Current Data State
- **Universe**: ~50 / 6,500 target tickers locally available.
- **Data Depth**: Incomplete fundamental histories.
- **Survivorship**: 100% (No delisted tickers).

## C. Exact P6-12D Blocker
- **Blocker**: Missing the comprehensive 6,500-ticker historical dataset containing PIT fundamentals and delisted securities. Without this, cross-sectional ranking (like the 75th percentile BEAR threshold) is statistically invalid.

## D. Provider Comparison
- **Tiingo**: Strongly recommended for historical OHLCV and Corporate Actions. Cost-effective, explicit adjustments, handles `permaTickers` (delisted).
- **SEC EDGAR**: Authoritative source for PIT fundamentals based on actual filing dates.
- **yfinance**: Acceptable only for *current-day live execution*, strictly prohibited for historical backtesting.

## E. Recommended Data Architecture
`Tiingo (OHLCV) + SEC EDGAR (Fundamentals) -> Normalization Pipeline -> SQLite/Parquet Canonical Store -> Backtest Engine`

## F. Estimated Storage Requirements
- **Raw OHLCV (20 Years, 6.5k tickers)**: ~3-5 GB
- **Fundamentals**: ~500 MB
- **Total Estimated Local Footprint**: ~4-6 GB (Highly feasible for an M2 8GB Mac).

## G. Estimated Acquisition Requirements
- Fetching 20 years of data for 6,500 tickers requires careful rate-limiting. Expected ingestion time: 2-6 hours depending on provider API limits.

## H. PIT Risk Analysis
The current implementation of generating historical fundamental alpha using today's `yfinance` snapshots creates extreme lookahead bias. The proposed SEC EDGAR architecture resolves this.

## I. Live Recommendation Pipeline Status
- **Status**: Vulnerable but mechanically functional.
- **Issue**: Fails silently or drops candidates when `yfinance` APIs timeout, returning 0s. 

## J. Root Cause of Previous "0 Tickers" Execution
1. `DataLoader._download_yf` caught a `YFDataException`.
2. It returned an empty DataFrame.
3. `get_volume_data` converted this empty DataFrame to `pd.DataFrame(0)` (all 0s).
4. `adv_20d` (20-day Average Daily Volume) evaluated to `0`.
5. The Execution Engine's Liquidity Filter dropped all candidates because `0 > 500,000` is False.

## K. MOCK Fundamental Exposure
- **Vulnerability**: `LLMFundamentalEngine` correctly tags local simulated scores as `MOCK`. However, `batch_analyze_top_candidates()` strips this metadata, injecting the fabricated score directly into the `MetaAlphaEngine` as a raw float. This critically undermines the ranking integrity of `MODEL_RANK_E`.

## L. Current TOP5/WATCHLIST5 Readiness
- **Readiness**: UNSAFE. The presence of hidden MOCK scores invalidates current capital allocation outputs. 

## M. Exact P6-12D Unblock Criteria
1. Download full U.S. universe (Tiingo OHLCV).
2. Download SEC EDGAR PIT fundamentals.
3. Incorporate delisted tickers.
4. Guarantee 0% synthetic data in the testing matrix.

## N. Recommended Next Engineering Task
**Execute the Data Ingestion Phase**: Construct the data ingestion pipeline targeting Tiingo and SEC EDGAR. Save the results locally to Parquet or SQLite while enforcing the exact schema required by P6-12D. Furthermore, repair the MOCK data leak in `LLMFundamentalEngine` by propagating `data_status` to `DecisionEngine`.

## O. Files Changed
None (Research phase only).

## P. Files Created
1. `reports/P6-13_DATA_FORENSIC.md`
2. `reports/P6-13_DATA_FORENSIC_MATRIX.json`
3. `reports/P6-13_PIT_DATA_CONTRACT.md`
4. `reports/P6-13_PIT_DATA_REQUIREMENTS.json`
5. `reports/P6-13_PROVIDER_RESEARCH.md`
6. `reports/P6-13_PROVIDER_COMPARISON.json`
7. `reports/P6-13_DATA_ARCHITECTURE_SPEC.md`
8. `reports/P6-13_DATA_ARCHITECTURE.json`
9. `reports/P6-13_LIVE_RECOMMENDATION_FORENSIC.md`
10. `reports/P6-13_LIVE_RECOMMENDATION_MATRIX.json`
11. `reports/P6-13_MOCK_DATA_EXPOSURE.md`
12. `reports/P6-13_MOCK_DATA_EXPOSURE.json`
13. `reports/P6-13_P6_12D_UNBLOCK_GATE.md`
14. `reports/P6-13_P6_12D_UNBLOCK_GATE.json`
15. `reports/P6-13_FINAL_JOINT_RESEARCH_REPORT.md`

## Q. Tests Executed
Codebase manual tracing and logic inspection.

## R. Tests Passed/Failed
- Liquidity safeguard logic: PASSED (Correctly dropped 0 volume).
- MOCK propagation logic: FAILED (Silently bypasses safety).

## S. Frozen Components Verification
- **P6-11B Trading Logic**: UNCHANGED
- **Alpha Architecture**: UNCHANGED
- **MODEL_RANK_E**: UNCHANGED
- **500k Liquidity Minimum**: UNCHANGED
- **75th Percentile BEAR Threshold**: UNCHANGED
- **Portfolio Individual Cap**: 30% (UNCHANGED)
- **Technology Sector Cap**: 40% (UNCHANGED)
- **TOP5/WATCHLIST5 Architecture**: UNCHANGED
- **PIT Repair**: PRESERVED
