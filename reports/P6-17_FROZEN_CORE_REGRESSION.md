# P6-17 Frozen Core Regression Baseline

## Deterministic Baseline Execution
A deterministic fixture (`scripts/generate_golden_baseline.py`) was executed to capture the exact mathematical output of the frozen P6-11B core **before** any P6-17 modifications.

### Golden Candidates & Baseline Behavior
1. **T_HIGH_ALPHA**: Volume 1M, High Alpha (9.32) -> Passed all gates -> **TOP5 Allocation (20%)**
2. **T_LOW_ALPHA**: Volume 1M, Low Alpha (-12.32) -> Failed 75th percentile -> **REJECTED_BEAR_PERCENTILE**
3. **T_LIQ_FAIL_400K**: Volume 400k -> Failed liquidity -> **REJECTED_LIQUIDITY**
4. **T_LIQ_FAIL_ZERO**: Volume 0 -> Failed liquidity -> **REJECTED_LIQUIDITY**
5. **T_LIQ_FAIL_NAN**: Volume NaN -> Failed liquidity -> **REJECTED_LIQUIDITY**
6. **T_SECTOR_B, T_SECTOR_E**: High Alpha, Passed liquidity -> **TOP5 Allocation (20%)**
7. **T_SECTOR_A, C, D**: Low Alpha -> **REJECTED_BEAR_PERCENTILE**

### Post-Implementation Contract
After P6-17 live data architecture is implemented, this identical deterministic fixture MUST be re-run.
The outputs (`alpha`, `alpha_percentile`, `status`, `allocation`) must match this baseline down to the exact floating-point value. If any value drifts, it proves P6-11B was accidentally modified, triggering an immediate rollback.
