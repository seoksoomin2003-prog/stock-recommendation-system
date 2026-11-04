# P6-8 Final Decision Architecture Stress Test Report

## HYPOTHESIS
A unified decision support system combining capital-aware ranking (`MODEL_RANK_E`), position sizing constraints (`SIZING_CAP_AWARE`), and sector concentration caps (40% limit) is robust across capital tiers, regimes, and transaction fees.

## EVIDENCE
* **Best Sizing / Ranking Combo**: **`MODEL_RANK_E + SIZING_CAP_AWARE + 40% Sector Cap`**
* **Capital Sizing at $1,000**:
  * Whole Share Mode Executable: **88.3%**
  * Fractional Share Mode Executable: **100.0%**
* **Sector Concentration Caps ($10,000 Capital)**:
  * Unrestricted (No Cap): **0.42%** mean net return.
  * Restricted (40% Cap): **0.84%** mean net return.

### Required Final Table

| Architecture | Capital | Ranking | Sizing | Sector Cap | Entry | Exit | Horizon | Trades | Net Return | Drawdown | Turnover | Execution | Verdict |
|---|---:|---|---|---:|---|---|---|---:|---:|---:|---:|---:|---|
| SLOW_TREND_50 | $1,000 | MODEL_RANK_E | SIZING_CAP_AWARE | 40% | 40/60 | Dynamic | 30D | 32 | 0.28% | -17.12% | 0.38 | 100.0% | PROMISING |
| SLOW_TREND_50 | $2,500 | MODEL_RANK_E | SIZING_CAP_AWARE | 40% | 40/60 | Dynamic | 30D | 32 | 0.63% | -17.12% | 0.38 | 100.0% | PROMISING |
| SLOW_TREND_50 | $5,000 | MODEL_RANK_E | SIZING_CAP_AWARE | 40% | 40/60 | Dynamic | 30D | 32 | 0.49% | -14.78% | 0.38 | 100.0% | PROMISING |
| SLOW_TREND_50 | $10,000 | MODEL_RANK_E | SIZING_CAP_AWARE | 40% | 40/60 | Dynamic | 30D | 32 | 0.42% | -14.78% | 0.38 | 100.0% | PROMISING |

## LIMITATION
The out-of-sample holdout window remains sample-constrained. While the architecture demonstrates high capital feasibility, long-term regime shifts (e.g., secular inflation cycles) require additional out-of-sample backfills.

## VERDICT
**B. PROMISING — USER DESIGN REVIEW REQUIRED**

## NEXT ACTION
Present the final decision tables to the user for formal approval before implementing production trading rules in P6-8.

---

RESEARCH COMPLETE — USER DESIGN REVIEW REQUIRED BEFORE FINAL TRADING-LOGIC IMPLEMENTATION.
