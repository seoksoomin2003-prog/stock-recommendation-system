---
name: Quant Factor Research & Validation
description: Actionable guidelines for backtesting factor models, evaluating weight plateaus, detecting overfitting, and structuring chronological walk-forward validations.
---

# Quant Factor Research & Validation

This skill defines the quantitative research workflow, evaluation metrics, overfitting diagnostics, and reporting steps for factor model validation.

---

## 1. Mandatory Evaluation Metrics

Never evaluate a model or declare a factor "improved" based on a single metric (e.g. gross return). You must compute and report the following multi-dimensional metrics across TRAIN, VALIDATION, and HOLDOUT splits:

* **Spearman Rank IC (20D, 5D, 60D)**: Information Coefficient representing rank correlation with forward returns.
* **IC t-stat**: Metric representing statistical significance (aim for $|t| > 2.0$).
* **Bootstrap 95% Confidence Interval**: Re-sampled CI bounds to prove IC stability.
* **Directional Hit Rate**: Percentage of time rank correlation is positive.
* **Top-Bottom Return Spread (Q4 - Q1)**: Difference in returns between top and bottom score quartiles.
* **Monotonicity (Q1 < Q2 < Q3 < Q4)**: Verifying that returns increase monotonically across score quartiles.
* **Avg Turnover**: Portfolio turnover between dates to calculate trading friction.
* **Transaction Cost Deductions**: Report net returns under three fee tiers:
  * *LOW_COST*: 7 bps (5bps commission + 2bps slippage)
  * *BASE_COST*: 20 bps (15bps commission + 5bps slippage)
  * *HIGH_COST*: 55 bps (40bps commission + 15bps slippage)

---

## 2. Diagnostics & Classifications

* **Overfitting Identification**: If Validation performance improves but Holdout performance degrades (or t-stat falls below significance), classify the result as `OVERFITTING_SUSPECTED`.
* **Regime Sensitivity**: If a factor (e.g. Momentum) only works during specific regimes (e.g. BULL) and degrades or reverses during others (e.g. BEAR), classify it as `REGIME_SENSITIVE` and research dynamic regime weights.
* **Missing Factor Renormalization**: Never fill missing factor values with `0` or static defaults (which distorts standardizations). Always trigger dynamic weight renormalization.
* **No Robust Evidence**: If results lack statistical significance ($|t| < 1.96$) or bootstrap bounds cross zero, classify the final verdict as `NO_ROBUST_EVIDENCE` or `DATA_LIMITED_RESEARCH_CONTINUES`.

---

## 3. Chronological Walk-Forward Research Workflow

* **Baseline Preservation & Controlled Changes**: Factor formulas and weights must not be modified arbitrarily. Baseline parameter configurations are kept frozen as a control group. Model modifications or parameter optimizations are permitted ONLY through this formal 6-step Walk-Forward Research Workflow, ensuring every change is statistically validated before promotion.

Every factor research task must proceed in this exact sequence:

1. **Baseline**: Document the frozen, immutable prior results (e.g. `reports/P5-8_BASELINE_FROZEN.json` with 20D Mean Spearman IC `-0.0326`).

2. **Hypothesis**: State the research question and expected factor behavior (e.g., "Regime-conditioned Momentum reduces drawdown in BEAR markets").
3. **Validation**: Test candidate weights and parameters on TRAIN and VALIDATION splits only. Locate weight plateau regions.
4. **Holdout**: Run the final holdout split (OOS) exactly once on the best candidate configuration. **Never use holdout for weight selection.**
5. **Robustness**: Compare net returns, spreads, and regime consistency.
6. **Verdict**: Choose one of the final verdicts:
   * *A. ROBUST_MODEL_CANDIDATE_FOUND*
   * *B. BASELINE_PREFERRED*
   * *C. NO_ROBUST_MODEL_FOUND*
   * *D. DATA_LIMITED_RESEARCH_CONTINUES*
