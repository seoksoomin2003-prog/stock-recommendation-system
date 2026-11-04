# P6-2 / P6-3 / P6-4 Entry, Exit, and Horizon Robustness Research Report

## Final Verdict

**B. PROMISING BUT NOT ROBUST**

### Hypothesis
Walk-forward parameter grid optimization over style configurations yields parameter-stable timing indicators that avoid optimization cliffs and resist transaction costs.

### Evidence
* **Best Strategy Configuration**: **SLOW_TREND_50**
* **Holdout Trade Count**: **32**
* **Holdout Mean Return**: **4.78%**
* **Holdout Win Rate**: **50.0%**

#### Strategy Comparison on Holdout:
* Trend Continuation: **53.3% win rate** (30 trades)
* Breakout Entry: **0.0% win rate** (2 trades)

#### Capital Sizing Scenarios (Executability at $1,000 Capital):
* Whole Share Mode: **12.5%** of trades are executable.
* Fractional Share Mode: **100.0%** of trades are executable.

### Limitation
* Bounded search over 6 configurations controls multiple testing risk but leaves some parameter neighborhoods unsearched.
* Holdout OOS window (3 validation periods) represents a small sample size, which does not allow for full statistical power.

### Next Action
1. Present these findings to the user for formal design review.
2. Maintain the simulation models in research-only status.

---

RESEARCH COMPLETE — USER DESIGN REVIEW REQUIRED BEFORE TRADING LOGIC IMPLEMENTATION.
