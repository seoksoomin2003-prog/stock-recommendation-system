# P6-17 MODEL_RANK_E Freeze Pipeline

## Complete Execution Path
The exact execution path for a valid candidate passing from Alpha generation to Portfolio Allocation must remain mathematically identical before and after P6-17 implementation.

1. **CORE Factors (`FactorEngine`)**
   - Extracts Price/Volume and Financial inputs.
   - Calculates 4 raw core factors (`momentum`, `value`, `quality`, `low_volatility`) with Strict Lag rules.
2. **Alpha Aggregation (`ScoringEngine` / `MetaAlphaEngine`)**
   - Normalizes factors.
   - Applies base `alpha` weightings.
   - P6-16 dynamic reweighting is applied if optional factors (Sentiment, Alternative, Fundamental) are valid.
3. **Quarantine Firewall (`DecisionEngine`)**
   - Filters missing/invalid data.
   - **Liquidity Check**: Drops if volume < `500,000`.
4. **Regime Thresholding (`DecisionEngine`)**
   - **BEAR Regime**: Calculates cross-sectional `alpha_percentile`. Drops candidates where percentile < `0.75` (75th Percentile strictness).
5. **Ranking (`RankingEngine.calculate_model_rank_e`)**
   - Capital-aware composite model merging Alpha score with secondary risk metrics.
   - Outputs descending sorted ranking.
6. **Portfolio Construction (`PortfolioEngine` / `DecisionEngine`)**
   - Takes Top N.
   - Allocates risk-adjusted weights.
   - Caps individual allocation at `30%` and sector exposure at `40%`.

## Integration Rule
P6-17 Live Universe generation, Freshness validation, and Provenance metadata extraction must occur **BEFORE Step 1**. The P6-17 architecture is not permitted to mutate any step of this execution path.
