# P6-17 Universe Selection Review

## 1. Live Universe Strategy
The live recommendation engine will transition from a hardcoded 7-ticker development list to a dynamic **S&P 500 Bootstrap Universe**. 

- **Why S&P 500?** The S&P 500 provides a highly liquid, stable baseline of approximately 500 active U.S. equities. This drastically reduces the API load compared to querying a 6,500+ ticker universe, minimizing rate-limit violations on zero-cost public APIs (yfinance, SEC EDGAR), while perfectly suiting the short-term small-capital investor profile.
- **Liquidity Threshold**: The P6-11B 500,000 ADV (Average Daily Volume) liquidity minimum remains **FROZEN**. We will not lower this threshold to artificially boost the candidate count from the smaller universe.

## 2. Architectural Separation
The universe generation is strictly decoupled from the historical Security Master.
- **Provider Role**: Wikipedia will act purely as `BOOTSTRAP_UNIVERSE`.
- **Identity Resolution**: Once the 500 tickers are fetched, they will be matched against SEC `company_tickers.json` to attach valid CIKs and resolve entity identities. 
- **Extensibility**: The system will support a configurable `LIVE_UNIVERSE_TARGET` (defaulting to `"SP500"`), allowing future expansions like `"NASDAQ100"` without architectural rewrites.

## 3. Failure & Caching Policy
- If the Wikipedia source fails, the system will **NOT** fallback to the old 7-ticker list, nor will it invent tickers.
- It will attempt to load a locally cached universe. If the cached universe is older than the allowed universe freshness threshold, it will be marked `STALE`.
- If no valid universe can be constructed, the pipeline will immediately abort and return `DATA-INCOMPLETE / NO VALID RECOMMENDATION`.

## 4. Frozen System Verification
- The 500k liquidity threshold is explicitly unmutated.
- The 75th percentile BEAR threshold is unmutated.
- The Portfolio sizing caps (30% individual, 40% sector) are unmutated.
- **Verdict**: Universe selection changes are strictly localized to the ingestion layer. P6-11B logic remains 100% frozen.
