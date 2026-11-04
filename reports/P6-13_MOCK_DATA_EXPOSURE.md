# P6-13 MOCK DATA EXPOSURE REPORT

## 1. The Vulnerability
An architectural data-leakage vulnerability was discovered in the live fundamental pipeline where MOCK fundamental scores silently bypass the data validation layer and directly inflate real ranking results.

## 2. Exposure Path
1. `LocalFundamentalProvider` creates a localized simulation output (e.g., Score = 76.25).
2. `LLMFundamentalEngine.generate_signal()` correctly tags this with `"data_status": "MOCK"` in its returned dictionary (line 147).
3. However, `LLMFundamentalEngine.batch_analyze_top_candidates()` (line 167) actively strips out the metadata and extracts ONLY the `final_score` as a raw float in a Pandas Series.
4. The `MOCK` tag is discarded.
5. The raw float is injected into `MetaAlphaEngine.combine_scores()`.
6. The Ranking Engine and Decision Engine compute portfolio allocations under the assumption that this fundamental alpha was generated from `REAL` data.

## 3. Impact
- **Alpha**: Artificially influenced by static or randomized placeholder scores.
- **Ranking / MODEL_RANK_E**: Candidates with mock fundamentals can unfairly outrank candidates with real fundamentals.
- **TOP 5 & WATCHLIST 5**: MOCK data dictates capital allocation.

## 4. Required Mitigation
Define a strict data quality contract:
- The system must propagate the composite `DataStatus` (`REAL`, `PARTIAL`, `MOCK`, `UNAVAILABLE`) down to the `DecisionEngine`.
- If `data_status == MOCK`, the candidate MUST be assigned a zero weight for fundamental alpha, or the system should explicitly alert the user that the TOP 5 list is synthetically generated.
