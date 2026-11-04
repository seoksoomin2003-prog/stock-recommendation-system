# P6-12C Parameter Traceability Hardening Report

## Executive Summary

During the P6-12C Post-Implementation Pipeline Audit, two specific parameters were explicitly identified as `RESEARCH_REQUIRED`. These parameters were introduced during the P6-11B implementation phase without a dedicated multiple-testing-aware out-of-sample statistical validation. 

Per the P6-12C Addendum directives, these parameters have been traced, documented, and explicitly categorized as `IMPLEMENTATION_ADDED / RESEARCH_DERIVED`. They must **not** be treated as statistically validated production invariants until a formal joint research study (P6-12) is completed.

## 1. Liquidity Hard Minimum

- **Current Value:** `500,000`
- **Unit:** Shares
- **Metric:** 20-day ADV (Average Daily Volume)
- **Classification:** `RESEARCH_REQUIRED`
- **Origin:** `IMPLEMENTATION_ADDED`
- **Status:** `FROZEN_PENDING_RESEARCH`

### Code Paths & Traceability
1. **`core/decision_engine.py:51`** - Hardcoded first-pass filtering logic during candidate ingestion. Drops candidates outright if `c.get('volume', 0) < 500000`.
2. **`utils/config.py:110`** - `EXECUTION_SETTINGS["min_volume_threshold"]` is set to `500000`.
3. **`main.py:322`** - Fetches `min_volume_threshold` from `EXECUTION_SETTINGS` before execution allocation. Calculates ADV using `adv_20d = raw_volumes.tail(20).mean()`.
4. **`execution/execution_engine.py:59`** - `filter_by_liquidity` applies the final safeguard where `volumes[t] > threshold` drops invalid/NaN liquidity safely without fabricating data.

### Notes
- The 500k liquidity minimum was introduced to prevent "Paper Profit" illusion in micro-cap and low-liquidity names.
- It was NOT established through a dedicated multiple-testing-aware out-of-sample statistical parameter study. 
- It MUST NOT be changed or optimized without a formal validation process.

---

## 2. BEAR Market Regime Alpha Entry Threshold

- **Current Value:** `0.75`
- **Unit:** Percentile
- **Metric:** Alpha Percentile Ranking (`alpha_percentile >= 0.75`) (Top 25% strictness)
- **Classification:** `RESEARCH_REQUIRED`
- **Origin:** `IMPLEMENTATION_ADDED`
- **Status:** `FROZEN_PENDING_RESEARCH`

### Code Paths & Traceability
1. **`core/decision_engine.py:213`** - Hardcoded threshold value in `_rank_candidates`. Used exclusively in `BEAR` regime routing.
2. **`utils/config.py:129`** - `DECISION_SETTINGS["bear_alpha_threshold"]` is set to `0.75`.

### Notes
- The 75th percentile requirement is intended to be a strictness hurdle during BEAR markets, ensuring the system requires exceptional alpha to enter any long position.
- This parameter MUST be cross-validated across market regimes to verify it does not induce unintended selection bias or false negatives.

---

## Future Joint Research Contract (P6-12 Specification)

To properly validate these parameters, the upcoming P6-12 Full-Coverage Joint Statistical Validation task must adhere to the following contract:

1. **Full-Coverage Validation:** The study must utilize the fully available, PIT-safe historical universe. It cannot rely on arbitrary subsampling (e.g., 200-ticker subsets) merely for performance reasons.
2. **Computation-Backed:** The results must be derived from actual computation, not simulated or conceptual outputs.
3. **Multiple-Testing Control:** Because both liquidity and BEAR thresholds affect the cross-sectional ranking and regime behavior jointly, they must be tested together to control for Multiple Testing Bias.
4. **No Implementation Changes:** Until this validation concludes, `500000` (Liquidity) and `0.75` (BEAR Threshold) are absolutely frozen in production code.
