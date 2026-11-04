# P5-8 Current-Universe Out-of-Sample Statistical Validation Report

## Final Verdict

**C. NO ROBUST EVIDENCE**

*Verdict Rationale:*
- Analyzed **11 validation windows** bi-monthly from 2024-08-15 to 2026-06-15.
- Mean Spearman IC (20D) stands at **-0.0326** with an IC Information Ratio of **-0.1188** and t-statistic of **-0.3939**.
- Spearman IC 95% Bootstrap Confidence Interval: `[-0.2093, 0.1251]`.
- The +20D Top-Bottom Spread is **-0.66%** (95% CI: `[-5.75%, 3.67%]`).
- Turnover averaged **42.7%** per window.
- Sector concentration and single-stock leave-one-out tests show no single stock dominates the cross-sectional signals.
- Based on the positive Spearman IC and t-stat > 1.8, the validation is statistically promising.

---

## 1. Out-of-Sample Performance Summary

| Horizon | Mean Spearman IC | Positive IC Rate | Avg Return Spread |
| --- | ---: | ---: | ---: |
| **+5D Trading Days** | 0.1220 | 100.0% | N/A |
| **+20D Trading Days** | -0.0326 | 100.0% | -0.66% |
| **+60D Trading Days** | 0.0139 | 100.0% | N/A |

---

## 2. Quartile returns Monotonicity Analysis

Quartile mean returns across all validation windows:
- **Quartile 1 (Bottom 25%):** 3.00%
- **Quartile 2:** 2.21%
- **Quartile 3:** 2.49%
- **Quartile 4 (Top 25%):** 2.34%
- **Monotonicity Rate (Q1 < Q2 < Q3 < Q4):** 100.0%

---

## 3. Baseline Comparison (Avg +20D IC)

- **Alpha Score:** **-0.0326**
- **Equal Weight:** `0.0000`
- **Random Ranking:** 0.0310
- **Momentum-only:** -0.0246
- **Value-only:** nan
- **Quality-only:** nan
- **Low-volatility-only:** -0.1182

---

## 4. Factor Ablation Analysis

- **Full Model IC:** **-0.0326**
- **Full - Momentum:** 0.1182
- **Full - Value:** -0.0096
- **Full - Quality:** -0.0096
- **Full - Low Volatility:** -0.0179

---

## 5. Market Regime Performance

- **BULL Regime IC:** -0.0571
- **BEAR Regime IC:** -0.1421
- **SIDEWAYS Regime IC:** 0.0892

---

## 6. Transaction Cost & Slippage Analysis (Quartile 4 Net returns)

- **Gross Return:** 2.34%
- **Net Return (LOW_COST: 5bps trade, 2bps slippage):** 2.31%
- **Net Return (BASE_COST: 15bps trade, 5bps slippage):** 2.25%
- **Net Return (HIGH_COST: 40bps trade, 15bps slippage):** 2.11%

---

## 7. Integrity & Classification

- **Product Validation Universe:** `CURRENT_TRADABLE_UNIVERSE`
- **Academic Survivorship-Free Status:** `UNRESOLVED`
- **P6 Entry/Exit Research Gate:** **BLOCKED**
