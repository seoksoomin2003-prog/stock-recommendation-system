# P6-13 DATA FORENSIC REPORT

## 1. Local Database Inventory
- **`data/historical_data.db`**: Contains `historical_price_bars` table with ~531,061 rows. Covers only 50 distinct tickers from 2018-01-02 to 2026-08-14. Missing ~6,450 tickers of the U.S. universe.
- **`data/historical_security.db`**: Contains 50 security states.
- **`data/tickers.db`**: Contains 12 canonical tickers.
- **`data/research_cache.db`**: 106 cache rows, not a canonical historical store.

## 2. Forensic Findings
- **Date Coverage**: 2018-2026 is present for the 50 tickers.
- **Missing Tickers**: 6,450 / 6,500 target universe.
- **Delisted Securities**: None represented. Survivorship bias is inherently 100%.
- **Fundamentals**: `historical_data.db` lacks historical fundamental tables for the full universe; `yfinance` snapshots are used dynamically in live mode, injecting future lookahead bias if used historically.
- **Corporate Actions**: Table `historical_corporate_actions` exists but is not populated across the universe.

## 3. Verdict
**INSUFFICIENT HISTORICAL DATA**
The current data architecture completely lacks the density and breadth required to execute the P6-12D statistical validation.
