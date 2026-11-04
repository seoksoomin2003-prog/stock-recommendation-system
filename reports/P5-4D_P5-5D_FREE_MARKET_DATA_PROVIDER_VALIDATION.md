# P5-4D / P5-5D Free Historical Market Data & Corporate Action Provider Validation Report

## Final Verdict

**B. LIMITED HISTORICAL DATA READY**

*Verdict Rationale:* 
- We can acquire fundamental facts (from SEC EDGAR) and active/OTC-delisted daily pricing (from yfinance).
- Alpha Vantage Free provides active/delisted status list (9,423 delistings mapped with dates).
- However, full historical prices for defunct/delisted tickers (e.g. TWTR, SIVB) return 0 rows in yfinance.
- Alpha Vantage's `outputsize=full` and `TIME_SERIES_DAILY_ADJUSTED` (splits, dividends, adjusted close) are premium-restricted.
- Thus, a complete, survivorship-free historical database is **unavailable** under purely free endpoints. P5-6 is restricted to **contract translation foundation only**, and P5-7 backtesting remains **BLOCKED**.

---

## 1. Provider Capability Summary

### A. Alpha Vantage (Free Tier)
- **Listing/Delisting Status:** Fully available. Sourced 14,310 active listings and 9,423 delisted listings via `state=delisted` CSV endpoint.
- **Daily Price Depth:** Restricted to compact size (last 100 days of prices). `outputsize=full` is a premium-only feature.
- **Adjusted Prices & Corporate Actions:** `TIME_SERIES_DAILY_ADJUSTED` is premium-only. No free access to daily splits, dividends, or adjustment factors.
- **Rate Limit:** Spaced to 25 requests per day, 5 requests per minute, 1 request per second.

### B. yfinance (Secondary Market Data Provider)
- **Active Price Depth:** Full history (OHLCV + adjusted close) is available.
- **Active Corporate Actions:** Splits and dividends are available.
- **Delisted Securities:** Returns 500 rows for OTC-listed pink sheet tickers (e.g. `SBNY` at last close of $0.32), but returns **0 rows (empty)** for completely defunct/liquidated tickers like `TWTR` and `SIVB`.
- yfinance is not an authoritative source for S&P 500 history or delisting metadata.

---

## 2. Cross-Provider Price Validation

We compared AAPL daily pricing for `2026-08-13`:

| Field | yfinance (Free) | Alpha Vantage (Free) | Difference | Status |
| --- | ---: | ---: | ---: | --- |
| **Open** | 304.21 | 304.21 | 0.00 | Match (tolerance <= 1e-6) |
| **High** | 306.00 | 306.00 | 0.00 | Match (tolerance <= 1e-6) |
| **Low** | 302.05 | 302.05 | 0.00 | Match (tolerance <= 1e-6) |
| **Close** | 305.26 | 305.26 | 0.00 | Match (tolerance <= 1e-6) |
| **Volume** | 40,316,500 | 40,349,289 | 32,789 | Volume mismatch (allowable) |

*Volume Mismatch Note:* Mismatches in volume are expected due to different exchange consolidation rules (Yahoo consolidates differently than Alpha Vantage's source feed). Open, High, Low, and Close align perfectly.

---

## 3. Survivorship Bias Status

- **Classification:** `LIMITED_SURVIVORSHIP_FREE`
- While we have complete CIK mapping and SEC fundamental facts (which is survivorship-bias free), pricing history remains limited to active and OTC-listed pink sheet tickers. Fully delisted defunct listings cannot have their prices reconstructed without Nasdaq Data Link, Sharadar, or Norgate premium licenses.

---

## 4. Production Database Ingestion Statistics

| Database File | Table | Real Rows | Synthetic/MOCK Rows |
| --- | --- | ---: | ---: |
| `historical_security.db` | `historical_security_states` | 0 | 0 |
| `historical_data.db` | `historical_price_bars` | 0 | 0 |
| `historical_data.db` | `historical_financial_facts` | 0 | 0 |
| `historical_data.db` | `historical_corporate_actions` | 0 | 0 |

*Note:* All production tables remain clean and free from synthetic or test mock records.

---

## 5. Test Verification Summary

We ran `python3 -m unittest tests/test_historical_provider_validation.py` which executes the following 18 test scenarios:

1. **Alpha Vantage unavailable behavior:** connection exceptions raised. (PASS)
2. **Alpha Vantage auth failure:** invalid API key error parsed. (PASS)
3. **Alpha Vantage rate limit:** note parsing handled. (PASS)
4. **Alpha Vantage premium endpoint:** premium restriction parsed. (PASS)
5. **Historical listing status:** CSV parsed. (PASS)
6. **Historical delisting status:** delisted CSV parsed. (PASS)
7. **yfinance current-only behavior:** defunct tickers SIVB/TWTR empty. (PASS)
8. **Ticker reuse handling:** unique security_id values allocated. (PASS)
9. **Delisted security identity:** valid range and ListingStatus preserved. (PASS)
10. **Corporate action timing:** announcement_at is None if missing (not copied). (PASS)
11. **Raw/adjusted price separation:** close vs. adjusted_close. (PASS)
12. **PIT price rejection:** lookahead price lookups rejected. (PASS)
13. **PIT listing rejection:** lookahead security lookups rejected. (PASS)
14. **Cross-provider price validation:** compares OHLCV. (PASS)
15. **Synthetic data firewall:** rejects synthetic source tags. (PASS)
16. **Duplicate idempotency:** double writes ignored. (PASS)
17. **Conflicting duplicate rejection:** different values raise error. (PASS)
18. **Historical InformationSet reproducibility:** hashing invariant holds. (PASS)

---

## 6. Action Plan for P5-6

1. P5-6 (NormalizedData translation) may proceed in a **limited capacity** to implement the contract translation classes only.
2. P5-7 (Backtesting Engine) remains **BLOCKED** until valid paid historical data (Sharadar, Nasdaq Data Link, or Norgate) is configured.
