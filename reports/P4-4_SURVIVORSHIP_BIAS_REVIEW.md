# P4-4 SURVIVORSHIP BIAS REVIEW REPORT

---

## 1. Executive Summary
This report presents a read-only forensic audit of the **Survivorship Bias** profile inside the current Quantitative Stock Prediction / Alpha Scoring System database (`data/tickers.db`). 
Because the local database contains only active listed securities with no delisted history or corporate action logging, the system is classified as **C. CURRENT_ONLY_UNIVERSE**. 
We determine that while a full **Survivorship-Free Predictive Validation (Level 2)** is impossible under current data constraints, a **Limited Diagnostic Validation (Level 1)** is permitted to verify technical point-in-time correctness and mathematical integrity. The final predictive power verdict is marked as **NOT ESTABLISHED**.

---

## 2. Current Universe Audit
We inspected the `securities` table in `data/tickers.db`:
- **Actual Security Count**: **12**
- **Tickers List**: `['005930.KS', 'AAPL', 'AMZN', 'GOOGL', 'JPM', 'KO', 'META', 'MSFT', 'NFLX', 'NVDA', 'TSLA', 'XOM']`
- **Asset Type**: All 12 are currently active, highly liquid, large-cap equities.
- **Sector Spread**: Concentrated in Technology, Finance, Consumer Defensive, and Energy.

---

## 3. Historical Universe Availability
- **Listing Date**: **NOT PRESENT** in `securities` schema.
- **Delisting Date**: **NOT PRESENT** in `securities` schema.
- **Valid-From / Valid-To Dates**: `ticker_history` table exists but is **completely empty** (`[]`).
- **Conclusion**: There is no point-in-time mapping of which securities were active on past decision dates.

---

## 4. Delisted Security Coverage
- **Status**: **0% coverage**. No delisted securities exist in the local database.
- **yfinance Inherent Limitation**: Yahoo Finance does not maintain a reliable archive of historical prices or valuation metrics for companies that have been delisted due to bankruptcy, acquisition, or private transitions.

---

## 5. Ticker History Coverage
- **Status**: **0% coverage**. The `ticker_history` database table is unpopulated. Ticker changes over time (e.g. FB $\rightarrow$ META, GOOG $\rightarrow$ GOOGL) are handled via ad-hoc resolver aliases but are not tracked as time-varying records.

---

## 6. Corporate Action Coverage
- **Status**: **0% coverage**. Split adjustment is delegated to the market provider (using yfinance's `auto_adjust=True`), but merger, acquisition, spin-off, and restructuring histories are completely absent.

---

## 7. Survivorship Bias Risk Assessment
Evaluating the model exclusively on the 12 survivor giants introduces a massive **Survivorship Bias**:
- **Risk Level**: **CRITICAL (HIGH RISK OF OVERFITTING)**.
- **Effect**: If the model is run historically on this universe, it will appear highly profitable because the universe is pre-selected for companies that successfully survived and outperformed from 2023 to 2026. Companies that went bankrupt or were merged out are ignored.

---

## 8. Point-in-Time Integrity Assessment
Despite the universe limitations, the code's point-in-time calculation mechanics are highly robust:
1. **Feature Timestamps**: Core logic filters news by `published_at <= T`, SEC ownerships by `filed_at <= T`, and market prices by date $\le T$.
2. **Adversarial Gate**: Future-dated data is blocked by `ValueError("look_ahead_data_rejected")`.
3. **Cross-Sectional Normalization**: Standardization is recalculated dynamically at each decision date $T$ using only the sub-universe available on that day.

---

## 9. P4-4 Execution Eligibility
- **Verdict**: **P4-4 LIMITED DIAGNOSTIC VALIDATION = ALLOWED**
- **Justification**: Although we cannot draw predictive conclusions, we can use the 12-ticker universe to verify the technical and mathematical stability of the point-in-time pipeline over rolling windows.

---

## 10. Allowed Validation Scope (Level 1)
- [x] Verification of `as_of` timestamp propagation.
- [x] Verification of Z-score normalization math over rolling dates.
- [x] Verification of row-by-row dynamic weight renormalization (Option B).
- [x] Verification of hard gates and clipping limits.
- [x] Verification of look-ahead adversarial gates.

---

## 11. Forbidden Conclusions
The following claims are **strictly prohibited** in any validation reports derived from the current dataset:
*   ❌ *"The alpha scoring model is verified to yield profitable signals."*
*   ❌ *"The composite factor has positive predictive information coefficient (IC)."*
*   ❌ *"The strategy outperformance is statistically significant."*
*   
Instead, any statistical results must be marked:
> **"Diagnostic evidence within the currently available survivor-only universe. Survivorship bias unresolved."**

---

## 12. Historical Data Requirements for Level 2
To upgrade the system to a true **Survivorship-Free Historical Validation (Level 2)**, we require:

| Domain | Minimum Required Schema / Specification |
| :--- | :--- |
| **Security Identity** | Permanent ID mapping, listing/delisting dates, ticker history logs. |
| **Historical Universe** | Point-in-time index constituent logs (e.g. S&P 500 constituents at date $T$). |
| **Market Data** | Split-adjusted prices for all active and delisted securities. |
| **Financials** | Real point-in-time quarterly statement availability dates (`filed_at` dates). |
| **Corporate Actions** | Stock splits, mergers, acquisitions, name changes, cash payouts. |

---

## 13. Candidate External Data Sources
We evaluated the main institutional-grade options for survivorship-free integration:

| Source | Delisted Coverage | PIT Fundamentals | Cost | Local Integration |
| :--- | :--- | :--- | :--- | :--- |
| **CRSP** | Complete | Excellent (with Compustat) | Very High | High (Requires database ingest) |
| **Sharadar** | Complete (16k+ names) | Excellent (daily PIT) | Medium (~$1k/yr) | Easy (Nasdaq Data Link API) |
| **Norgate Data** | Complete | Limited | Low | Easy (Python library + local sync) |
| **Bloomberg** | Complete | Excellent | Very High | Medium-High (Bloomberg terminal Link) |

---

## 14. Recommended Next Step
1. Proceed with the **Level 1 Current-Survivor Universe Diagnostic** to verify the mathematical soundness and point-in-time integrity of the canonical orchestrator.
2. In the next development cycle (Phase 5), procure a Nasdaq Data Link subscription for **Sharadar** to import a survivorship-free historical universe and run **Level 2 validation**.

---

## 15. Final Decision
- **Q1: 현재 data/tickers.db만으로 P4-4를 실행할 수 있는가?**
  - **Yes**, but only as a Level 1 technical diagnostic validation.
- **Q2: 실행한다면 어떤 수준까지 신뢰할 수 있는가?**
  - Only for verifying technical pipelining correctness and math. No predictive validity can be trusted.
- **Q3: 현재 결과를 predictive validation으로 인정할 수 있는가?**
  - **No**.
- **Q4: Survivorship bias를 해결하기 위해 historical universe 구축이 지금 즉시 필요한가?**
  - **No**, it can be deferred to Phase 5.
- **Q5: 아니라면 현재 P4-4를 diagnostic validation으로 진행해도 되는가?**
  - **Yes**.
- **Q6: 최종 predictive validation 전에 반드시 확보해야 할 데이터는 무엇인가?**
  - Point-in-time listing/delisting logs, delisted stock price history, and Compustat or Sharadar point-in-time fundamentals.

---

## Final Classification Verdict
**A. DIAGNOSTIC ONLY — SURVIVORSHIP BIAS UNRESOLVED**
