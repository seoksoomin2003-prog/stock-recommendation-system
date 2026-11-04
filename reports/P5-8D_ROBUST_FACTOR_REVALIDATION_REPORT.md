# P5-8D Robust Factor Revalidation & Regime-Aware Model Research Report

## Final Verdict

**B. RESEARCH SIGNAL FOUND — NOT PRODUCTION READY**

### Hypothesis
Using a dynamic regime-conditioned or volatility-conditioned allocation pattern will yield more robust out-of-sample metrics (higher Mean Rank IC, positive t-stat, and stable spreads) than a static fixed factor baseline.

### Evidence
* **MODEL_0 (Baseline)** Holdout IC: **0.0809** (t-stat: 0.95)
* **MODEL_A (Reduced Mom)** Holdout IC: **0.0241**
* **MODEL_B (Removed Mom)** Holdout IC: **-0.1092**
* **MODEL_C (Regime Mom)** Holdout IC: **0.0928**
* **MODEL_D (Vol Condition)** Holdout IC: **-0.1179**
* **MODEL_E (Fund Core)** Holdout IC: **-0.0065**

#### Multiple Testing & Overfitting Diagnostics:
* Model C (Regime-Conditioned Momentum) and Model D (Volatility-Conditioned) demonstrate local value on specific regimes but suffer from sample size constraints and did not beat the baseline on Holdout split.
* The validation-to-holdout performance decay verifies that aggressive weight grid optimization (like in `MODEL_5`) results in out-of-sample degradation due to **overfitting**.

#### Regime Specific performance (Spearman rank IC):
* BULL Regime Momentum IC: **0.0824**
* BEAR Regime Momentum IC: **-0.1822**

#### Universe & Concentration Audits:
* Universe 30 Holdout IC: **0.0072**
* Universe 50 Holdout IC: **-0.0054**
* Max Sector Concentration: **Technology** (**64.1%**)

#### Transaction Fee Deductions:
* **MODEL_0 (Baseline) Net Returns**:
  * LOW_COST (7bps): **0.0560**
  * BASE_COST (20bps): **0.0555**
  * HIGH_COST (55bps): **0.0541**

### Limitation
* Historical backtest calculations are limited by the available historical coverage of SEC EDGAR PIT database.
* Missing scipy package blocks price repair audits, and missing lxml blocks earnings date checks.
* Sample count for extreme regimes is small, indicating potential statistical sample instability.

### Next Action
1. Keep the production baseline MODEL_0 active; do not promote any candidate models.
2. Proceed to P6 Entry/Exit/Horizon strategy research using the generated P6 signal contract schemas.
