# KR Model Research Specification (P6-23 §5)

Status: **research complete for KR-EXP-0.1**. Script: `research/kr_factor_study.py`. Results: `reports/KR_FACTOR_STUDY_RESULTS.json` (generated 2026-11-04, data spec `KR-DATA-0.1`).

This is a factor **diagnostic**, not a backtest of the strategy. It may only decide which candidate factors are included. It must never be read as evidence of predictive power or profitability.

## 1. Pre-registered rule (fixed in code before any result was observed)

| Item | Rule |
|---|---|
| Candidates, in priority order | `MOM_6_1` (t-126 → t-21 return), `REV_1M` (minus the 21-session return), `LOWVOL_60` (minus the std of 60 daily log returns, ≥ 55 valid), `TREND_50` (close / 50-session mean − 1) |
| Cross-section | current liquid-300 (§3 bias) |
| Rebalance | every 21 KRX sessions; forward return = adjusted close t → t+20 sessions (non-overlapping) |
| Statistic | cross-sectional Spearman rank IC of the direction-adjusted factor vs forward return; mean, std, t = mean / (std/√n), hit rate |
| Drop rule 1 | drop a factor if its mean-IC t-statistic is **< −2.0**, i.e. significantly opposite to its hypothesis |
| Drop rule 2 | drop a factor if the mean absolute rank correlation with an already-kept factor is **> 0.70** (redundancy); priority order decides |
| Weights | equal over kept factors; never fitted to returns |
| Minimum cross-section | 100 names with complete factors and forward return per date |

The rule is deliberately weak, because the sample cannot support a strong one. It removes only factors that are clearly wrong or duplicated. It does not select factors because they "worked".

## 2. Results (live Yahoo data, 2023-08-24 … 2026-11-04)

Universe at study time: 300 members (KOSPI 161, KOSDAQ 139). ADTV20 cutoff 8.58 bn KRW, median 25.1 bn KRW (proxy basis).

**27 rebalance dates** (2024-03-04 … 2026-09-03), 20-session forward windows:

| Factor | Mean IC | Std IC | t-stat | Hit rate | Decision |
|---|---|---|---|---|---|
| MOM_6_1 | −0.021 | 0.165 | −0.68 | 41% | KEPT (t not < −2) |
| REV_1M | −0.023 | 0.127 | −0.93 | 41% | KEPT |
| LOWVOL_60 | +0.040 | 0.243 | +0.86 | 56% | KEPT |
| TREND_50 | −0.021 | 0.136 | −0.81 | 41% | **DROPPED**: rank correlation with REV_1M = −0.85 (redundant) |

Mean cross-sectional rank correlations:

| Pair | Correlation |
|---|---|
| REV_1M / TREND_50 | −0.85 |
| LOWVOL_60 / MOM_6_1 | −0.33 |
| MOM_6_1 / TREND_50 | +0.19 |
| LOWVOL_60 / TREND_50 | −0.09 |
| LOWVOL_60 / REV_1M | +0.06 |
| MOM_6_1 / REV_1M | −0.01 |

**Outcome:** `KR-EXP-0.1` uses MOM_6_1, REV_1M and LOWVOL_60 with equal weights of 1/3 each.

## 3. Interpretation (honest reading)

- **No factor shows evidence of predictive power.** Every |t| is below 1. With 27 periods, ICs of this size cannot be told apart from zero. Two of the three kept factors have a *negative* point estimate. This is not a validation; the model is a pre-specified, unvalidated baseline for paper observation.
- **Known biases,** each of which can only flatter the results:
  - survivorship and membership look-ahead: today's liquid-300 is projected back in time;
  - Yahoo supplementary prices and a proxy traded value;
  - no transaction costs, and no KRX sell-side transaction tax;
  - a short sample of about 2.7 years, in one market regime.
- What would be needed to **validate** the model (none of it is available at zero cost today):
  - point-in-time KOSPI/KOSDAQ membership and delisting history;
  - official KRX traded value (`KRX_API_KEY`);
  - a longer sample.

  Alternatively, the prospective record can serve as out-of-sample evidence (`KR_MODEL_SPECIFICATION.md` §6).

## 4. Fundamental factors (specified, inactive)

The following candidates require OpenDART fundamentals (`OPENDART_API_KEY`), so they are not yet active:

- earnings yield;
- book-to-price (equity_parent);
- operating-income margin (non-financial only);
- CFO/assets;
- leverage (non-financial only).

They also need `shares_outstanding`, which is UNAVAILABLE in `KR-ACCT-0.1`. Before activation, coverage must be measured per industry class, and the same pre-registered rule must be applied in a new model version (`KR-EXP-0.2`). Financial firms (BANK, INSURANCE, SECURITIES) would need class-specific definitions. They would never use the non-financial formulas.
