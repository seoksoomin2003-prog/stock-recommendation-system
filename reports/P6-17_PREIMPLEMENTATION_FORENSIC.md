# P6-17 Pre-Implementation Forensic Audit

## 1. Hardcoded Tickers (Development Bottleneck)
- **File**: `main.py` (Line 662)
- **Finding**: The Live Universe is currently hardcoded as `sample_tickers = ["AAPL", "MSFT", "GOOGL"]`. This completely bypasses any real runtime universe generation and restricts the pipeline to these 3 entities.
- **Action Required**: Remove this hardcoded list and implement a real Live Universe provider that selects an active, liquid subset of U.S. equities at runtime.

## 2. P6-11B Core Lookback Requirements
- **File**: `core/factor_engine.py`
- **Finding**: 
  - `calculate_momentum`: Resamples to monthly (`ME`) and requires at least `14` monthly bars to calculate the 12-1 momentum with a 1-month lag (`shift(1)`).
  - `calculate_volatility`: Uses a 22-day rolling window with a 1-day lag (`shift(1)`).
- **Conclusion**: The absolute minimum market data lookback required by the frozen P6-11B core is **14 Months (~425 Days)**.
- **Action Required**: The market data loader must explicitly enforce this 14-month lookback. If `<14` months are available, `momentum` becomes `UNAVAILABLE`. 

## 3. Provider Fallbacks & MOCK Contamination
- **File**: `data/loader.py`
- **Finding**: 
  - `_download_yf`: Handles failures gracefully by returning an empty DataFrame with `np.nan`, which correctly propagates as `UNAVAILABLE`.
  - `get_news_headlines`: **CRITICAL VIOLATION**. If the News API fails or the key is absent, it automatically returns a hardcoded list of synthetic mock headlines (e.g., `"Lawsuit filed against..."`). This is strictly forbidden.
- **Action Required**: Remove the mock fallback in `get_news_headlines`. It must return an empty list or `UNAVAILABLE` state.

## 4. SEC EDGAR vs yfinance (Fundamentals)
- **File**: `data/loader.py` (`get_financial_data`)
- **Finding**: Currently, PER, PBR, ROE, and Profit Margin are fetched purely via `yfinance` (`t.info`). SEC EDGAR is not being used to populate these core fields.
- **Action Required**: Design a mapping in `P6-17_SEC_FUNDAMENTAL_MAPPING.md` to cleanly extract these metrics from SEC EDGAR (Company Facts) as the authoritative source, using yfinance solely as a secondary fallback if permissible.

## 5. Minimum Effective Model Coverage (0.50 Rule)
- **Finding**: P6-16 successfully introduced the `0.50` coverage threshold. The forensic audit confirms this represents the exact structural weight of the P6-11B core `factor` component (50%). Therefore, the `0.50` threshold is classified as: **IMPLEMENTATION_ADDED / RESEARCH_DERIVED**, as it mathematically forces the presence of the original P6-11B core before allowing any optional data to contribute.

## 6. Freshness Policy
- **Finding**: There is currently no explicit timestamp-based freshness validation for market data or fundamentals before they enter the `FactorEngine`.
- **Action Required**: Implement explicit freshness checks (e.g., Market Data must be updated within the last 1-3 trading days) or mark as **RESEARCH_REQUIRED**.
