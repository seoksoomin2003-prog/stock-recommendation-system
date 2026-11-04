---
name: P6 Entry Exit Expected Horizon Research
description: Guidelines for researching trading entry, exit boundaries, expected holding horizons, and investability constraints under historical walk-forward constraints.
---

# P6 Entry Exit Expected Horizon Research

> [!IMPORTANT]
> This skill governs upcoming strategy research in the P6 phase. The implementation of trading rules, entry triggers, exit boundaries, and expected horizons is a future research target and must follow chronological walk-forward validation prior to production promotion.

This skill governs the research boundary, signal components, target formulations, and walk-forward verification steps for P6 execution strategies.


---

## 1. Separation of Concerns (P5 vs. P6)

* **P5 (Alpha Factor Model)**: Focuses on ranking securities by expected relative returns over a fixed horizon (e.g. 20D) using point-in-time fundamentals and market signals.
* **P6 (Trading Strategy Model)**: Focuses on absolute execution rules, entry timing, expected holding horizons, stop loss limits, and transaction cost constraints.
* **Rule**: Never tune P5 factor weights inside a P6 trading simulation. P5 factor outputs must be treated as frozen input signals by P6.

---

## 2. Decoupled Prediction Targets

Do not define entry/exit rules based on the Alpha Score alone. Entry, Exit, and Horizon are distinct targets that must be modeled and evaluated independently:

### A. Entry Timing (BUY / WATCH / AVOID)
* **Target**: Find optimal entry window when the asset is undervalued, showing upward factor momentum, and experiencing low price target dispersion.
* **Signal Inputs**: Alpha score, trend momentum, analyst estimate revisions, news sentiment, and liquidity bounds.
* **Evaluation**: Compare entry signal accuracy using forward trade return distributions and drawdowns within $T+5$ days.

### B. Expected Holding Horizon
* **Target**: Estimate the expected duration (e.g. 10D, 20D, 60D) before the alpha rank decays or transaction friction erodes profits.
* **Signal Inputs**: Volatility regime, macro conditions, and upcoming earnings event proximity.
* **Evaluation**: Horizon accuracy is evaluated by rank decay analysis (measuring how long a stock remains in the top scoring quartile).

### C. Exit Boundaries (Target, Risk, and Partial Liquidations)
* **Target**: Define target price ranges, risk invalidation boundaries (stop loss), and partial exit thresholds.
* **Signal Inputs**: Historical volatility, expected downside (VaR), and support/resistance trend levels.
* **Evaluation**: Compare execution performance of fixed horizon exits vs. dynamic stop-loss/take-profit boundaries using net returns and maximum drawdown (MDD).

---

## 3. Walk-Forward Trading Strategy Verification

* **Historical Backtesting**: All entry/exit rules must be backtested chronologically using walk-forward simulation.
* **Promotion Rule**: Never promote a trading rule to production based on high performance in a single validation window or current live results. It must demonstrate statistical robustness (t-stat, Sharpe ratio after transaction fees) across multiple market regimes (BULL, BEAR, SHOCK).
* **Cost Deduction**: Deduct execution slippage and commissions sequentially for all trade entries and exits.
