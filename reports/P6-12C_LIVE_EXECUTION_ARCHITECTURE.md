# P6-12C-A LIVE EXECUTION ARCHITECTURE

## ARCHITECTURAL PARADIGM
The system now adheres to a **CHUNKED SEQUENTIAL EXECUTION WITH GLOBAL AGGREGATION** architecture to prevent memory saturation without discarding candidate validity.

## DATA FLOW
1. **FULL UNIVERSE RESOLUTION** (All candidates)
2. **BOUNDED PROCESSING QUEUE** -> Chunk Size = 3 (MAX_LOCAL_TICKERS)
3. **INCREMENTAL FEATURE EXTRACTION**:
   - For `Chunk i`:
     - Load Prices & Volumes
     - Load Financials & News
     - Extract Factors & Sentiment
     - Run Fundamental Deep-Dive RAG
   - Append factors/prices/results to memory-safe aggregated lists.
   - Force memory cleanup `MemoryGuard.check_and_cleanup()`.
4. **GLOBAL MERGE**:
   - Concatenate all aggregated chunks into global DataFrames.
5. **GLOBAL RANKING**:
   - Apply Cross-Sectional Standardization over the *combined* array.
6. **RISK-ADJUSTED PORTFOLIO CONSTRUCTION**:
   - Top 5 + Watchlist 5 selection via `PortfolioEngine`.

## CAPITAL AWARENESS
Capital limits are maintained by scaling the portfolio target weights against the provided `target_aum`. 

## REUSABILITY
The bounded processing queue established here in `main.py` is identical to the sequential block-level processing necessary for the planned P6-12C PIT Historical Data Coverage Recovery. The memory cleanup hooks remain globally shared.
