---
name: Free Market Data Provider Engineering
description: Actionable guidelines for acquiring, rate-limiting, caching, and cross-validating financial data from free providers under memory-bounded environments.
---

# Free Market Data Provider Engineering

This skill defines the adapter principles, rate limit compliance, memory bounds, and cross-validation procedures for free financial data sources.

---

## 1. Provider Hierarchy & Roles

Always implement connections using independent adapters matching these roles:

| Tier | Provider | Primary Data | Limitations / Rules |
| --- | --- | --- | --- |
| **Tier 1** | `SEC EDGAR` | Official PIT Fundamentals, CIKs, Accession Numbers | Must include valid User-Agent header; limited to 10 requests/sec. |
| **Tier 2** | `yfinance` | Current financials, auxiliary recommendations, market data (OHLCV, splits, dividends) | No direct PIT guarantees on financials. Subject to rate limits and missing dependencies (e.g. `lxml`, `scipy`). |
| **Tier 3** | `Alpha Vantage Free` | Price, listing, and corporate action validation | Limited to 5 requests/min and 500 requests/day. Use as secondary source. |
| **Tier 4** | `Genuinely Free Sources` | Sentiment, news, alternative factors | Subject to fallback handling if API keys are inactive. |

---

## 2. Core Engineering Principles

### A. Rate Limiting & Ethics
* **Entitlements**: Never attempt to bypass premium paywalls or write wrappers to scrape premium endpoints.
* **Rate Limits**: Honor rate limits explicitly using serialize locks or time delay gaps (e.g., 0.5s wait between SEC requests).
* **Failure Handling**: If a provider fails (e.g., yfinance returns 404 or 429), treat the data as `UNAVAILABLE` and let the scoring engine renormalize. Do not raise exceptions that crash the pipeline.

### B. Persistent Identity & Ticker Safety
* **Identity Mapping**: Never use ticker alone (e.g., "AAPL") as a persistent database key. Map to `security_id` incorporating source and CIK (e.g., `sec-aapl-320193`).
* **Ticker Reuse**: Keep security records dated to handle corporate action actions (e.g. mergers, ticker changes, delistings) without identity collision.

### C. Resource & MacBook M2 8GB Constraints
* **Bounded Queries**: Filter database queries by date and security ID in SQL. Never load entire historical tables into memory.
* **Sequential Scraping**: Acquire facts sequentially for tickers. Do not run multi-threaded scrapers with concurrency > 2.
* **Local Cache**: Cache retrieved raw JSON payloads locally with a defined TTL (e.g., 1 day) to reduce API hits.

---

## 3. yfinance Capabilities Audit Checklist

When implementing new factors or signal features, refer to this endpoint availability map:

* **history(period, auto_adjust)**: Supported. Splits and dividends must be stored separately from raw close.
* **get_income_stmt() / get_balance_sheet()**: Available. Lacks filing dates and contains restated figures; block from historical backtest inputs.
* **get_shares_full(start, end)**: Available. Useful for market capitalization denominator calculation.
* **get_earnings_dates()**: Requires `lxml` package. Check environment dependencies before calling.
* **analyst_price_targets / get_recommendations()**: Available for current research. Useful for auxiliary live scoring.
* **news**: Available. Useful for alternative sentiment signals.
