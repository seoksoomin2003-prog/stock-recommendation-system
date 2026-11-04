# P6-13 DATA ACQUISITION ARCHITECTURE SPEC

## 1. Overall Flow
**Provider → Raw Archive → Normalization → PIT Translation → Canonical DB → Research Runner**

## 2. Multi-Provider Synergy
Do not force one provider.
- **Historical OHLCV & Security Master**: Utilize **Tiingo** (via API) for daily prices, volumes, and corporate actions (Splits, Dividends). Leverages Tiingo's `permaTicker` to track delisted/recycled tickers.
- **Historical PIT Fundamentals**: Utilize **SEC EDGAR** for authoritative 10-Q/10-K filing timestamps.

## 3. Storage Layer
- **Live/Metadata State**: `SQLite` remains optimal for `tickers.db`, `research_cache.db`, and `historical_security.db`.
- **Historical Canonical Data**: Given M2/8GB RAM constraints and ~6,500 tickers over 10-20 years, `SQLite` (`historical_data.db`) is technically sufficient (estimated 4-5 GB), but **Parquet** partitioned by `year/month/` or `ticker/` is highly recommended for faster IO/read throughput during the chunked execution of P6-12D.

## 4. Normalization & PIT Translation
- **Raw Prices**: Store unadjusted (`raw_open`, `raw_close`, `raw_volume`).
- **Corporate Actions**: Store as a separate event table `(effective_date, ratio)`.
- **PIT Construction**: Generate `adjusted_close` dynamically backwards from the *current simulation day* during backtests, or strictly store an `adjusted_as_of` series to prevent future splits from altering past historical inputs.
- **Fundamentals**: Map SEC `acceptance_datetime` to `date`. The data becomes active on `date + 1` trading day to eliminate lookahead bias.

## 5. Incremental Updates & Deduplication
- Use `(security_id, date, source)` as the primary composite key.
- Apply `UPSERT` logic or `if_exists="replace"` at the partition level.
