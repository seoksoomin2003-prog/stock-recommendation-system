# P6-15 Zero-Cost Provider Matrix
No single provider holds the complete dataset. A combination approach is required:
- **SEC EDGAR:** Solves PIT fundamentals and can technically reconstruct the historical universe (by identifying all active CIKs on a given historical date).
- **yfinance:** Serves current live execution and backfilling survivor OHLCV.
- **Missing Link:** A zero-cost provider for delisted OHLCV.
