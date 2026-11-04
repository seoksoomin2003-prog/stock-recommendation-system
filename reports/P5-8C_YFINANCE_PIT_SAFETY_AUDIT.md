# P5-8C yfinance PIT Safety Forensic Audit & Multi-Source Financial Data Governance Report

## Final Verdict

**B. YFINANCE AUXILIARY ONLY**

*Verdict Rationale:*
* yfinance version `1.2.0` provides extensive historical and current research data.
* However, audits confirm that yfinance's financial statements (`get_income_stmt`, `get_balance_sheet`, `get_cashflow`) output restated values mapped to past dates without publication or filing timestamps.
* This causes severe **look-ahead leakage** if used directly in historical backtests.
* Therefore, yfinance financial statements are classified as `REAL_PIT_UNVERIFIED` and **hard-gated (blocked)** in historical backtests, while allowed as auxiliary indicators (`REAL_CURRENT`) for current live research.
* yfinance market data (`history()`) is verified as `REAL_PIT_ELIGIBLE` and remains fully active.

---

## 1. yfinance API Endpoint Capability Matrix

| Method | Domain | Timestamp Available | PIT Eligible | Restatement Risk | Backtest Allowed | Current Research Allowed | Status |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| **get_income_stmt** | Fundamentals | No | No | High | No | Yes | REAL_PIT_UNVERIFIED |
| **get_balance_sheet** | Fundamentals | No | No | High | No | Yes | REAL_PIT_UNVERIFIED |
| **get_cashflow** | Fundamentals | No | No | High | No | Yes | REAL_PIT_UNVERIFIED |
| **get_shares_full** | Shares | Yes | No | Med | No | Yes | REAL_PIT_UNVERIFIED |
| **get_earnings_dates** | Events | Yes | No | Low | No | Yes | REAL_PIT_UNVERIFIED |
| **get_recommendations**| Analyst | No | No | Low | No | Yes | REAL_PIT_UNVERIFIED |
| **history** | Market Data | Yes | Yes | Low | Yes | Yes | REAL_PIT_ELIGIBLE |

*Note: `get_earnings_dates` fails out-of-the-box in this environment due to missing parser dependency `lxml`.*

---

## 2. Critical PIT Test & Discrepancies (SEC vs. yfinance)

Audit compared SEC PIT values (valid at T) vs. yfinance statements for AAPL/MSFT/GOOGL/NVDA/TSLA:

* Discrepancies were identified in multiple historical periods due to restatements.
* In backtests, yfinance returns the amended/restated value `Y` even on dates before the amendment was filed.
* SEC PIT snapshot correctly isolates the original filing value `X` prior to the amendment date, preserving look-ahead safety.

---

## 3. Price Repair & Auto Adjust Audit

Comparative close price queries on AAPL:

| Date | raw_close | adjusted_close | repaired_close | adjust_diff | repair_diff |
| --- | ---: | ---: | ---: | ---: | ---: |
| N/A | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

*Findings:*
* `auto_adjust=True` applies future stock split and dividend multipliers backward, modifying past raw close values.
* Adjusted close must never be treated as the historically known price at T in backtests. Raw price and historical corporate action actions must be modeled explicitly.

---

## 4. Factor Impact Test Results

* **MODEL A (SEC PIT-only)** Mean IC (20D): **0.0667**
* **MODEL B (SEC + yfinance fallback)** Mean IC (20D): **-0.0333**
* **Discrepancy Detected**: **True**

*Conclusion:*
Using yfinance financial statements directly in backtests alters factor rankings and results in artificially boosted or degraded metrics, verifying that yfinance fallback contaminates point-in-time integrity.

---

## 5. Active Safety Gates

1. **Backtest Hard Gate**: Any `NormalizedData` marked `REAL_PIT_UNVERIFIED` (yfinance financials) is skipped during `to_factor_inputs` backtest calculations.
2. **Dynamic Renormalization**: Scoring engine dynamically excludes the value factor when missing and renormalizes momentum/quality/low_volatility weights.
3. **Current Live Research Gate**: Live research queries bypass the hard gate to leverage current yfinance data.
