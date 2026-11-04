# Data Pipeline Stability (P2) Report

This document details the query combination strategies, caching frameworks (fresh vs stale), official SEC endpoint mappings, look-ahead bias filters, and the metadata-rich contract tracking schemas implemented for Google Trends and SEC EDGAR.

---

## 1. Google Trends Resilient Architecture
- **Normal Path**: Resolves tickers to names and constructs multi-keyword OR queries:
  `[ticker, f"{ticker} stock", f"{ticker} share price", company_name]`
- **Caching Layer**: Implements memory caches with a fresh TTL = 1 hour.
- **Retry Strategy**: Employs connect/read timeouts (5s/10s) and bounded retries (max 2 attempts) with backoff on failures.
- **Fail-Safe Fallback**: If the pytrends vendor class is missing or rate limits (429) exhaust retries:
  - Check if stale cache exists: Return stale score with status `"STALE"` and confidence `0.5`.
  - If no cache exists: Return a deterministic neutral score of `50.0` with status `"FALLBACK"` and confidence `0.0`.
  - Never crash the pipeline or fabricate fake random data.

---

## 2. SEC EDGAR Resilient Architecture
- **CIK Resolution**: Resolves tickers to official Central Index Key (CIK) mappings downloaded from `sec.gov/files/company_tickers.json` with local offline fallbacks for popular tickers.
- **Submissions Mapping**: Queries the official JSON submissions endpoint:
  `https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json`
- **Filing Extraction**: Programmatically extracts filings (10-K, 10-Q, 8-K, Form 4) and formats primary document URLs.
- **Form 4 Insider Scoring**: Analyzes insider transaction metadata (`transaction` type, `amount`, `date`) to construct a net volume signal mapped to `[-1.0, 1.0]`.
- **Local Cache**: Caches downloaded submissions JSON files in `data/sec_cache/` (fresh TTL = 1 day) to protect EDGAR connection limits.
- **Compliance User-Agent**: Identifies requests with:
  `User-Agent: AlphaScoringEngine/2.0 (<contact e-mail>)`
- **Look-Ahead Bias Protection**: Filters out filings whose `filingDate` is in the future relative to the simulation/backtest date.

---

## 3. Data Quality Logging & Schema
Both engines return a metadata dictionary:
```json
{
    "value": float,
    "status": "OK|STALE|FALLBACK|NO_DATA",
    "confidence": float,
    "source": "google_trends_api|sec_api|sec_stale_cache|trends_fallback|sec_fallback"
}
```
In `alpha_engine/system.py`, these values are unpacked:
1. Raw float scores (`value`) are passed to the multi-factor scoring dataframe (ensuring 100% backward compatibility and zero score regressions).
2. Full quality dictionaries are logged inside the `self.data_quality_report` state tracker, allowing backtesters to filter or weight signals dynamically.

---

## 4. Verification Outcomes
All test cases implemented in `tests/test_data_stability.py` pass successfully:
- **TEST 1 — Normal Trends Response**: `[PASS]`
- **TEST 2 — Trends Timeout Fallback (50.0)**: `[PASS]`
- **TEST 3 — Trends 429 Retry Fallback**: `[PASS]`
- **TEST 4 — SEC CIK Resolution Mapping**: `[PASS]`
- **TEST 5 — SEC Normal Submissions Fetch**: `[PASS]`
- **TEST 6 — SEC Timeout Fallback (0.0)**: `[PASS]`
- **TEST 7 — SEC Stale Cache Recovery**: `[PASS]`
- **TEST 8 — Insider Engine Fallback Reset**: `[PASS]`
- **TEST 9 — Look-Ahead Bias Prevention**: `[PASS]`
- **TEST 10 — Scoring Pipeline Integration**: `[PASS]`
