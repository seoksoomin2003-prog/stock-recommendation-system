# P6-12D DATA AVAILABILITY FORENSIC

## 1. Executive Summary
A forensic inventory was conducted on the local SQLite databases (`data/historical_data.db`, `data/historical_security.db`, `data/tickers.db`, `data/research_cache.db`) to determine if the local environment holds the required point-in-time (PIT) historical data covering the entire U.S. tradable universe (~6,500 tickers) necessary for the P6-12D Liquidity × BEAR Joint Statistical Revalidation.

**The required full-universe PIT dataset is NOT locally available.**

## 2. Database Inventory
- `data/historical_data.db` (64 MB)
  - Contains `historical_price_bars` table.
  - Rows: ~531,061
  - Date Range: `2018-01-02` to `2026-08-14`
  - **Distinct Tickers: 50** (Severely limited coverage)
- `data/historical_security.db` (64 KB)
  - Contains `historical_security_states` table.
  - Rows: 50
- `data/tickers.db` (10 MB)
  - Contains `tickers` table.
  - Distinct Tickers: 12
- `data/research_cache.db` (1.1 MB)
  - Used for short-term fetch caching. Not a valid historical PIT repository.

## 3. Data Contract Status
- **20-day ADV**: MISSING for universe. (Available only for 50 tickers)
- **EMA20**: MISSING for universe.
- **ATR**: MISSING for universe.
- **BEAR cross-sectional percentile**: NOT COMPUTABLE (cross-sectional size of 50 is statistically invalid).

## 4. Verdict
**NOT_COMPUTABLE — FULL PIT DATA UNAVAILABLE**
The current local MacBook environment only stores 50 historical price streams. It lacks the massive, multi-GB 6,500-ticker dataset required to perform the P6-12D Joint Statistical Revalidation securely. The task is gated to prevent synthetic data usage, arbitrary subsampling, or lookahead biases.
