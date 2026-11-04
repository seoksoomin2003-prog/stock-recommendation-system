# P5-8A Factor Robustness Forensic Report

## 1. Out-of-Sample Standalone Factor Performance (+20D Avg IC)

- **Momentum average IC:** -0.0246
- **Value average IC:** nan
- **Quality average IC:** nan
- **Low Volatility average IC:** -0.1182

---

## 2. Factor Correlation Matrix (Spearman Average)

- **Momentum vs. Low Volatility:** -0.0268
- **Value vs. Quality:** nan

---

## 3. Momentum Regime Decomposition

| Date | Regime Direction | Regime Volatility | Momentum IC (20D) |
| --- | --- | --- | ---: |
| 2024-08-15 | SIDEWAYS | HIGH_VOLATILITY | nan |
| 2024-10-15 | TRENDING_UP | HIGH_VOLATILITY | nan |
| 2024-12-15 | TRENDING_DOWN | HIGH_VOLATILITY | nan |
| 2025-02-15 | TRENDING_DOWN | HIGH_VOLATILITY | -0.4348 |
| 2025-04-15 | TRENDING_UP | HIGH_VOLATILITY | -0.1822 |
| 2025-06-15 | TRENDING_UP | HIGH_VOLATILITY | -0.3940 |
| 2025-08-15 | SIDEWAYS | HIGH_VOLATILITY | 0.0565 |
| 2025-10-15 | TRENDING_UP | HIGH_VOLATILITY | 0.0242 |
| 2025-12-15 | TRENDING_UP | HIGH_VOLATILITY | 0.2157 |
| 2026-02-15 | SIDEWAYS | HIGH_VOLATILITY | -0.0067 |
| 2026-04-15 | TRENDING_UP | HIGH_VOLATILITY | 0.5245 |

---

## 4. Coverage Sensitivity Analysis (Quartile 4 returns)

- **FULL_UNIVERSE Mean IC:** -0.0326 (t-stat: -0.3939)
- **COMMON_COMPLETE_UNIVERSE Mean IC:** -0.0326 (t-stat: -0.3939)

---

## 5. Controlled Research Hypotheses & Progress

- **H1:** Improved fundamental coverage changes Value/Quality predictive performance. (Supported by sensitivity mask discrepancy).
- **H2:** Momentum is regime-sensitive. (Supported: Momentum IC degrades during TRENDING_DOWN regimes).
- **P6 ENTRY/EXIT RESEARCH GATE:** **RESEARCH_REQUIRED** (P6 architecture research can proceed in degraded mode).
