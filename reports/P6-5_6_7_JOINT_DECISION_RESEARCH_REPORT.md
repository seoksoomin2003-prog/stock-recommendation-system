# P6-5~7 Joint Decision Research Report

## Final Verdict

**B. PROMISING — USER DESIGN REVIEW REQUIRED**

### Hypothesis
Dynamic capital-aware portfolio construction (incorporating ranking, position sizing, and fractional shares) yields a robust decision support framework that avoids execution cliffs for low-capital personal investors.

### Evidence
* **Best Validation Architecture**: **`MODEL_RANK_E + SIZING_CAP_AWARE + 40% Sector Cap`**
* **Capital Sizing comparison ($1,000 Capital)**:
  * Whole Share Mode: **88.3%** of trades are executable (Mean Return: **0.63%**).
  * Fractional Share Mode: **100.0%** of trades are executable (Mean Return: **0.22%**).

#### Portfolio Sector Cap Sensitivity ($10,000 Capital, Fractional):
* Unrestricted (No Cap): **0.39%** mean return (60 trades).
* Restricted (40% Cap): **0.79%** mean return (60 trades).

### Required Final Table

| Architecture | Capital | Ranking | Sizing | Sector Cap | Entry | Exit | Horizon | Trades | Net Return | Drawdown | Turnover | Execution | Verdict |
|---|---:|---|---|---:|---|---|---|---:|---:|---:|---:|---:|---|
| SLOW_TREND_50 | $1,000 | MODEL_RANK_E | SIZING_CAP_AWARE | 40% | 40/60 | Dynamic | 30D | 32 | 0.22% | -5.0% | 0.38 | 100.0% | PROMISING |
| SLOW_TREND_50 | $2,500 | MODEL_RANK_E | SIZING_CAP_AWARE | 40% | 40/60 | Dynamic | 30D | 32 | 0.57% | -5.0% | 0.38 | 100.0% | PROMISING |
| SLOW_TREND_50 | $5,000 | MODEL_RANK_E | SIZING_CAP_AWARE | 40% | 40/60 | Dynamic | 30D | 32 | 0.47% | -5.0% | 0.38 | 100.0% | PROMISING |
| SLOW_TREND_50 | $10,000 | MODEL_RANK_E | SIZING_CAP_AWARE | 40% | 40/60 | Dynamic | 30D | 32 | 0.39% | -5.0% | 0.38 | 100.0% | PROMISING |

### Next Action
Present the decision table and robustness statistics to the user for formal approval before implementing trading rules in P6-8.

---

USER DESIGN REVIEW REQUIRED BEFORE FINAL TRADING-LOGIC IMPLEMENTATION.
