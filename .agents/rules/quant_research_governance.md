# Rule: Quant Research Governance

This rule governs data safety, point-in-time integrity, and model evaluation decisions across the project.

## 1. Project Objective & Universe Scope
* **Objective**: Build a free/open-source personal Bloomberg-level stock analysis and decision system.
* **Universe Policy**: Focus on currently tradable US equities. Do not include delisted equities in current trading recommendations.
* **Separation**: Distinguish between academic survivorship-free research and current tradable portfolio allocation. Do not block current tradable stock research because of survivorship bias validation limits.

## 2. Data Source Hierarchy & Trust levels
* **Tier 1 (PIT Financial Gold Standard)**: `SEC EDGAR` filings. (Authorized for historical backtest factor inputs).
* **Tier 2 (Auxiliary Financial & Analyst Provider)**: `yfinance` fundamentals, analyst estimates, earnings dates. (Classified as `REAL_PIT_UNVERIFIED` for backtests).
* **Tier 3 (Market Data Provider)**: `yfinance` price bars, OHLCV, splits, dividends. (Eligible for historical close pricing).
* **Tier 4 (Cross-Provider Validation)**: `Alpha Vantage Free`. (Used for cross-validations).

## 3. Explicit Data Status Definitions
* Explicitly maintain data provenance states: `REAL_PIT_ELIGIBLE`, `REAL_PIT_UNVERIFIED`, `REAL_CURRENT`, `CACHED_PIT_ELIGIBLE`, `CACHED_PIT_UNVERIFIED`, `UNAVAILABLE`, `FALLBACK`.
* Never label unretrieved, synthetic, or mock data as `REAL`.
* Never store mock or synthetic facts in the production SQLite database.

## 4. Backtest PIT Integrity & Hard Gates
* **Look-ahead Bias Prevention**: Never use future filings, future prices, future analyst revisions, or future corporate action events in historical factor calculations.
* **Backtest Gate**: Reject `REAL_PIT_UNVERIFIED` and `CACHED_PIT_UNVERIFIED` (yfinance financials) from historical backtest inputs.
* **Dynamic Renormalization**: If a factor is rejected, do not crash the pipeline. RENORMALIZE factor weights instead.
* **Live Research Policy**: Current stock research (e.g. "analyze AAPL today") is allowed to combine SEC latest PIT data and current yfinance auxiliary estimates. Tag this provenance explicitly as `REAL_CURRENT`.

## 5. Model Evaluation & Statistical Reporting
* **Baseline Integrity**: Keep baseline factor formulas and weights frozen as a control group. Modifications or parameter optimizations for model improvements are permitted only when controlled by the chronological Walk-Forward Research Workflow, ensuring every change is statistically validated before promotion.
* **P6 Phase Status**: P6 Entry/Exit/Expected Horizon strategies are upcoming research goals (in progress/design phase) and must not be treated as already implemented production trading rules.
* Never claim predictive validity without statistical significance (IC mean, t-stat, bootstrap CI, spreads, cost deductions).
* Do not choose models based solely on validation window performance; holdout data must be run once and never used for weight tuning.
* All research reports must strictly adhere to the following structure:
  1. **Hypothesis**: The target relationship or adjustment.
  2. **Evidence**: The quantitative statistics and backtest results.
  3. **Limitation**: Missing data, proxies, or dependency issues.
  4. **Verdict**: Clear decision (e.g. Robust model found vs. Auxiliary only).
  5. **Next Action**: Concrete engineering or research steps.

