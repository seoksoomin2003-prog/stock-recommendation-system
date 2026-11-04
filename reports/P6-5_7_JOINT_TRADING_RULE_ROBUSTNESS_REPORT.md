# P6-5~7 Joint Trading Rule Robustness Research Report

## Final Verdict

**B. PROMISING BUT NEEDS MORE RESEARCH**

### Hypothesis
A joint execution pipeline optimizing parameter perturbations, stop-losses, sector concentration limits, and two-stage entries yields a robust trading rule architecture suitable for user design review.

### Evidence
* **Holdout Trade Count**: **32**
* **Holdout Mean Return**: **4.78%**
* **Holdout Win Rate**: **50.0%**
* **Diversification (Sector Caps)**:
  * Unrestricted Technology Exposure: **64.1%**
  * Restricted (40% Cap) Technology Exposure: **37.5%**
  * Sector-Capped Holdout Mean Return: **3.85%**

#### Capital Feasibility (Price Constraint at $1,000 Capital):
* Whole Share Mode Executable: **12.5%**
* Fractional Share Mode Executable: **100.0%**

### User Decision Table

| Decision Item | Option A | Option B | Option C | Research Result | Recommendation | Why |
| --- | --- | --- | --- | --- | --- | --- |
| **Entry Timing** | Close > SMA20 | Close > SMA50 | Close > EMA20 | SMA50 was more robust | **Option B (SMA50)** | Slow filter avoids noise |
| **Stop-Loss** | Fixed Stop | ATR Stop | ATR + BEAR Stop | ATR + BEAR Stop minimized MDD | **Option C (ATR + BEAR)** | Volatility adaptation |
| **Exit Candidate** | Fixed TP/SL | Thesis Deterioration | Hybrid Exit | Invalidation avoided tail drawdown | **Option B (Thesis Decay)** | Avoids structural decay |
| **Sector Cap** | Unrestricted | 40% Concentration Cap | Sector Neutral | 40% cap lowered tech bias | **Option B (40% Cap)** | Limits clustering risk |
| **Capital Allocation** | Whole Share | Fractional Share | Dynamic Budget | Fractional share mode reached 100% | **Option B (Fractional)** | Feasible at $1,000 |

### Next Action
Present the decision table to the user for formal approval before implementing trading rules in P6-8.

---

USER DESIGN REVIEW REQUIRED BEFORE TRADING LOGIC IMPLEMENTATION.
