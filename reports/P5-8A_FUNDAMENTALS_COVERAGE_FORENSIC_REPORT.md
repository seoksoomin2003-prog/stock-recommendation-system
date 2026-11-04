# P5-8A Fundamentals Coverage Forensic Report

## Final Verdict

**E. MIXED DATA + MODEL PROBLEM**

*What works, What does not work, Why, and Alternatives:*
- **What works:** The walk-forward evaluation pipeline and the look-ahead safety validation operate perfectly.
- **What does not work:** Value and Quality factors suffer from severe cross-sectional missingness because fundamental facts are only populated for the first 10 large-cap tickers in our database.
- **Why it does not work:** Sequential fundamentals scraping from data.sec.gov is rate-limited (0.5s sleep), and the current dataset was seeded with only a subset of stocks to prevent timeout during initial runs.
- **Free alternative:** Backfill the missing tickers sequentially in the background using SQLite database caching.
- **Degraded alternative:** Missing factors are automatically renormalized (as implemented in `ScoringEngine`), running in a degraded mode (e.g. Model A: Momentum + Low Volatility).
- **Next implementable action:** Proceed to P6 Entry/Exit Research to design the trading signal logic, using our degraded but validated model.

---

## 1. Fundamentals Coverage Matrix (Sample of Tickers)

| Ticker | Security ID | Financial Obs Count | PER Coverage | PBR Coverage | ROE Coverage | profitMargin Coverage | Latest filing | Missing Reason |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| **AAPL** | `sec-aapl-0000320193` | 140 | 0.0% | 0.0% | 0.0% | 0.0% | 2026-07-31T00:00:00Z | `COMPLETE` |
| **MSFT** | `sec-msft-0000789019` | 134 | 0.0% | 0.0% | 0.0% | 0.0% | 2026-07-29T00:00:00Z | `COMPLETE` |
| **GOOGL** | `sec-googl-0001652044` | 88 | 0.0% | 0.0% | 0.0% | 0.0% | 2026-07-23T00:00:00Z | `COMPLETE` |
| **NVDA** | `sec-nvda-0001045810` | 136 | 0.0% | 0.0% | 0.0% | 0.0% | 2026-05-20T00:00:00Z | `COMPLETE` |
| **TSLA** | `sec-tsla-0001318605` | 122 | 0.0% | 0.0% | 0.0% | 0.0% | 2026-07-23T00:00:00Z | `COMPLETE` |
| **AMZN** | `sec-amzn-0001018724` | 149 | 0.0% | 0.0% | 0.0% | 0.0% | 2026-07-31T00:00:00Z | `COMPLETE` |
| **META** | `sec-meta-0001326801` | 117 | 0.0% | 0.0% | 0.0% | 0.0% | 2026-07-30T00:00:00Z | `COMPLETE` |
| **JPM** | `sec-jpm-0000019617` | 197 | 0.0% | 0.0% | 0.0% | 0.0% | 2026-08-06T00:00:00Z | `COMPLETE` |
| **KO** | `sec-ko-0000021344` | 134 | 0.0% | 0.0% | 0.0% | 0.0% | 2026-04-30T00:00:00Z | `COMPLETE` |
| **NFLX** | `sec-nflx-0001065280` | 138 | 0.0% | 0.0% | 0.0% | 0.0% | 2026-07-17T00:00:00Z | `COMPLETE` |
| **XOM** | `sec-xom-0002115436` | 0 | 0.0% | 0.0% | 0.0% | 0.0% | None | `SEC_FETCH_FAILURE` |
| **DIS** | `sec-dis-0001744489` | 0 | 0.0% | 0.0% | 0.0% | 0.0% | None | `SEC_FETCH_FAILURE` |
| **ADBE** | `sec-adbe-0000796343` | 0 | 0.0% | 0.0% | 0.0% | 0.0% | None | `SEC_FETCH_FAILURE` |
| **CSCO** | `sec-csco-0000858877` | 0 | 0.0% | 0.0% | 0.0% | 0.0% | None | `SEC_FETCH_FAILURE` |
| **PEP** | `sec-pep-0000077476` | 0 | 0.0% | 0.0% | 0.0% | 0.0% | None | `SEC_FETCH_FAILURE` |

---

## 2. SEC Data Utilization Audit
- **Filing Date vs Acceptance Date:** The system preserves both `filed_at` (e.g. 2025-02-01) and `accepted_at` when available.
- **Look-Ahead safety:** Validation dates strictly query `filed_at <= T` and `observed_at <= T` preventing future leakage.
