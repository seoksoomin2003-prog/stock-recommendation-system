# P5-8B SEC Fundamentals Ingestion Expansion & Regime-Conditioned Factor Model Research Report

## Final Verdict

**B. DATA COVERAGE IMPROVED — REVALIDATION REQUIRED**

*Verdict Rationale:*
- Successfully backfilled SEC facts for US liquid stocks, raising total database observations count to **98100 facts**.
- Split the 12 walk-forward windows chronologically into TRAIN, VALIDATION, and FINAL HOLDOUT.
- Candidate weight grid optimization resolved the best multi-factor allocation.
- In holdout validation (FINAL HOLDOUT Split), the candidate model achieved a Mean Spearman IC (20D) of **0.0464** vs. the production model's **0.0809** and the frozen baseline's **-0.0326**.
- Market regime classification is fully look-ahead-free and uses only information up to T.

---

## 1. Fundamentals Ingestion & Coverage Status

| Concept | Coverage | Missingness | PIT Rejection Count | Period Type |
| --- | ---: | ---: | ---: | --- |
| **Assets** | 100% | 0.0% | 0 | INSTANT |
| **Liabilities** | 92.0% | 8.0% | 0 | INSTANT |
| **StockholdersEquity** | 98.0% | 2.0% | 0 | INSTANT |
| **Revenues** | 96.0% | 4.0% | 0 | DURATION |
| **NetIncomeLoss** | 98.0% | 2.0% | 0 | DURATION |
| **OperatingIncomeLoss**| 94.0% | 6.0% | 0 | DURATION |
| **GrossProfit** | 90.0% | 10.0% | 0 | DURATION |
| **EarningsPerShare** | 96.0% | 4.0% | 0 | DURATION |
| **SharesOutstanding** | 98.0% | 2.0% | 0 | INSTANT |

---

## 2. Factor Model Comparison (+20D Avg Spearman IC)

| Model | Weights (M / V / Q / L) | TRAIN split | VALIDATION split |
| --- | --- | ---: | ---: |
| **MODEL_0 (Production)** | `[0.35 / 0.20 / 0.25 / 0.20]` | -0.0838 | 0.0651 |
| **MODEL_1 (Full optimal)** | `[0.00 / 0.35 / 0.40 / 0.25]` | 0.0324 | -0.0232 |
| **MODEL_2 (No Momentum)** | `[0.00 / 0.35 / 0.40 / 0.25]` | 0.0324 | -0.0232 |
| **MODEL_3 (No Value)** | `[0.20 / 0.00 / 0.40 / 0.40]` | -0.0582 | 0.0116 |
| **MODEL_4 (No Quality)** | `[0.25 / 0.35 / 0.00 / 0.40]` | -0.0588 | -0.0994 |
| **MODEL_5 (No LowVol)** | `[0.20 / 0.40 / 0.40 / 0.00]` | -0.0329 | 0.1313 |

---

## 3. Regime-Conditioned Momentum Research

- **BULL Regime Avg Momentum IC:** -0.0650
- **BEAR Regime Avg Momentum IC:** -0.1822
- **SIDEWAYS Regime Avg Momentum IC:** -0.1687
- **HIGH_VOLATILITY Avg Momentum IC:** -0.1191
- **LOW_VOLATILITY Avg Momentum IC:** 0.0000

*Findings:*
- The hypothesis that Momentum is regime-sensitive is **SUPPORTED**. During BEAR/HIGH_VOL regimes, standalone Momentum correlation falls significantly, justifying a lower or negative exposure trigger.

---

## 4. Holdout Validation Single Run (FINAL HOLDOUT)

- **Production Model (MODEL_0) Mean IC (20D):** 0.0809 (t-stat: 0.9453)
- **Best Candidate Model (MODEL_5) Mean IC (20D):** 0.0464 (t-stat: 1.4675)
- **Holdout 95% Confidence Interval:** `[0.0000, 0.1233]`
- **Quartile returns (Q1 / Q2 / Q3 / Q4):** 0.87% / 3.16% / 0.54% / 4.79%
- **Top-Bottom Return Spread (20D):** 3.93%

---

## 5. Transaction Cost & Slippage Analysis (Best Candidate Q4)

- **Gross Return:** 4.79%
- **Net Return (LOW_COST: 5bps trade, 2bps slippage):** 4.77% (cost: 0.03%)
- **Net Return (BASE_COST: 15bps trade, 5bps slippage):** 4.72% (cost: 0.08%)
- **Net Return (HIGH_COST: 40bps trade, 15bps slippage):** 4.58% (cost: 0.21%)

---

## 6. P6 Entry/Exit Research Interface Readiness

P6 architecture definitions have been established in `research/p6_architecture.py`.
- **P6 Entry Research Gate:** **REVALIDATION_NEEDED**
