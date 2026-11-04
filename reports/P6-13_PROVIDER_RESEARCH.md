# P6-13 PROVIDER RESEARCH REPORT

## 1. SEC EDGAR (Existing Custom Adapter / Open API)
- **Strengths**: Authoritative source for Point-In-Time (PIT) historical fundamentals. Timestamps exactly represent the public filing availability date (`as_of` semantics). Completely free.
- **Weaknesses**: Extracted financial data requires complex normalization. Does not provide OHLCV market data.
- **Suitability**: **CRITICAL** for PIT fundamentals.

## 2. Tiingo
- **Strengths**: Explicitly distinguishes raw and adjusted historical EOD prices. Robust handling of corporate actions (splits/dividends). Retains historical data for delisted and recycled symbols using `permaTicker`. Offers stable identifiers.
- **Weaknesses**: Full historical US equities dataset may require a premium subscription depending on the access tier.
- **Suitability**: **HIGHLY RECOMMENDED** for OHLCV and historical Security Master data.

## 3. Alpha Vantage
- **Strengths**: Provides Daily EOD prices (Raw & Adjusted).
- **Weaknesses**: Extensive historical depth requires premium tiers. Delisted ticker semantics and PIT fundamentals mapping can be ambiguous compared to Tiingo's permaTicker.
- **Suitability**: **MODERATE**. Usable, but Tiingo is structurally safer for PIT research.

## 4. yfinance (Current Implementation)
- **Strengths**: Free, easy integration for live current snapshots.
- **Weaknesses**: NO stable identifiers. NO delisted tickers (100% survivorship bias). NO Point-In-Time fundamentals (overwrites historical periods with current restatements or leaves them blank). High risk of API rate limiting on multi-GB downloads.
- **Suitability**: **UNACCEPTABLE** for P6-12D Historical Statistical Research. Restricted to Live/Current execution only.

## 5. Nasdaq Data Link (Quandl)
- **Strengths**: Institutional-grade PIT databases (e.g., Sharadar). Complete mapping of delisted entities.
- **Weaknesses**: High cost, often prohibitive for personal quant systems.
- **Suitability**: **LOW** (Due to budget constraints).
