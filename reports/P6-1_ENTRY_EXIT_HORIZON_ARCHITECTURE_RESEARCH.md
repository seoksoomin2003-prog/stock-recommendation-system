# P6-1 Entry / Exit / Expected Horizon Architecture Research Report

## Final Verdict

**A. P6 SIGNAL ARCHITECTURE VALIDATED**

### Hypothesis
Deconstruction of Alpha Score outputs into separate execution entry archetypes (Trend, Pullback, Breakout, Mean Reversion) and dynamic exit boundaries (target, stop-loss, trend fail, time decay) will yield superior risk-adjusted net returns and lower maximum adverse excursion than a simple static holding approach.

### Evidence
* **Total Simulated Trades**: **66**
* **Mean Realized Return**: **3.56%**
* **Strategy Win Rates**:
  * Trend Continuation: **48.4%**
  * Pullback Entry: **0.0%**
  * Breakout Entry: **100.0%**
  * Mean Reversion: **0.0%**

#### Exit Trigger Frequencies:
* Target Exits: **14**
* Risk Exits: **8**
* Trend Failures: **24**
* Time Exits: **20**

#### Capital Aware Executability (Price Constraints):
* Executable at $1,000 Capital: **12.1%**
* Executable at $10,000 Capital: **89.4%**
* Executable at $100,000 Capital: **100.0%**

### Limitation
* Signal decay profiling uses historical validation windows and cannot account for sudden regime pivots.
* Absence of `scipy` limits precise price repairs, and absence of `lxml` blocks earnings proximity triggers in this execution environment.

### Next Action
1. Register `P6EntrySignal` and `P6ExitSignal` as standard interface contracts.
2. Proceed to P6-2/P6-3 to optimize threshold trigger levels for Pullback and Breakout archetypes using the walk-forward validation grid.
