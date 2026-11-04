# P6-13 PIT DATA CONTRACT

## 1. Core Requirements
To safely execute P6-12D White's Reality Check across the full universe without lookahead bias, the following Point-In-Time (PIT) data contract must be satisfied.

## 2. Required Fields
- **OHLCV**: `open`, `high`, `low`, `close`, `volume`. Must be raw or correctly adjusted for corporate actions up to the `as_of` date.
- **Derived Metrics**: 
  - `EMA20`, `ATR`: Requires contiguous daily price history.
  - `20D ADV`: Requires contiguous daily volume history.
  - `Momentum (12M - 1M)`: Requires at least 13 months of historical lookback.
- **Fundamentals**: `per`, `pbr`, `roe`, `profitMargin`. Must strictly use the SEC Filing Acceptance Date (`as_of` timestamp) to guarantee the data was publicly knowable.
- **Security Master**: Stable CUSIP/FIGI identifiers, mapping historical tickers to current entities, including delisted entities to prevent survivorship bias.

## 3. PIT Integrity Contract
- Data MUST NOT be updated retroactively. If an earnings report is restated, the original report must remain the active value until the restatement filing date.
- `MOCK` or `SYNTHETIC` data is strictly prohibited from entering historical vectors.
