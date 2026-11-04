# P6-16 OPTIONAL REWEIGHT REVIEW

## Forensic Audit Results

### 1. Which factors are truly OPTIONAL?
The optional data sources added in V2 / P6-16 are defined in `utils/config.py` under `HYBRID_WEIGHTS`:
- `fundamental` (LLM/RAG based fundamental analysis) - Declared Weight: 20%
- `sentiment` (News sentiment) - Declared Weight: 15%
- `alt_data` (Google Trends/Social) - Declared Weight: 15%

### 2. Which factors are P6-11B CORE?
The core factors are defined in `utils/config.py` under `DEFAULT_FACTOR_WEIGHTS`:
- `momentum` - Declared Weight: 35%
- `quality` - Declared Weight: 25%
- `value` - Declared Weight: 20%
- `low_volatility` - Declared Weight: 20%

These are combined by `ScoringEngine` into a single `factor_score`, which represents the core P6-11B model and carries a 50% target weight in the `HYBRID_WEIGHTS` ensemble.

### 3. Which factors may be dynamically reweighted?
Only the optional ensemble factors inside `MetaAlphaEngine` may be dynamically reweighted:
- `fundamental`
- `sentiment`
- `alt_data`

### 4. Which factors must never be dynamically reweighted?
The core P6-11B factors (`momentum`, `quality`, `value`, `low_volatility`) must NEVER be dynamically reweighted by the P6-16 optional degradation layer. Their internal weighting logic inside `ScoringEngine` is frozen.

### 5. What happens when each optional factor is unavailable?
Currently, in `MetaAlphaEngine.combine_scores()`, missing optional factors are silently replaced with `0.0` (using `.fillna(0.0)`), effectively injecting fabricated neutral data and artificially dragging down the score, all while retaining their original weights (e.g., a 15% weight applied to 0.0). 
**Correction Plan**: The `.fillna(0.0)` will be completely removed. When unavailable, an optional factor's contribution will be mathematically 0, its effective runtime weight will drop to 0, and the remaining valid ensemble weights will be proportionally normalized.

### 6. What happens when each core factor is unavailable?
Currently, in `ScoringEngine.calculate()`, if a core factor (e.g., `momentum`) is missing (NaN), the engine automatically ignores it and renormalizes the weights among the remaining core factors for that specific candidate. This behavior is frozen and already established within the P6-11B logic. We will not touch it. If all core factors are missing, `ScoringEngine` returns NaN, which propagates up. Furthermore, `main.py` enforces a strict firewall dropping candidates missing prices, volumes, or basic financials altogether before they even reach `ScoringEngine`.

### 7. What minimum effective coverage is defensible?
The original P6-11B model was driven entirely by the core `factor_scores` (Momentum, Quality, Value, Low Volatility). Therefore, the absolute minimum effective coverage must be **50%** (i.e., the declared weight of the `factor` component in the hybrid ensemble). If a candidate cannot even provide the core `factor` score, or if the available weights sum to less than 50% of the hybrid model, it should be marked `DATA-INCOMPLETE`.

### 8. Does the proposed behavior preserve MODEL_RANK_E?
Yes. The internal mathematics of `ScoringEngine`, `RankingEngine`, and the base alpha logic remain mathematically untouched. The changes strictly isolate the P6-16 ensemble combinations inside `MetaAlphaEngine`. We will introduce a transparent runtime provenance record (e.g., `effective_runtime_weights` and `effective_weight_coverage`) attached to each candidate to separate the base `MODEL_RANK_E` identity from runtime data availability.

### 9. Does it preserve the declared P6-11B weights?
Yes. We will not modify `utils/config.py`. The dynamic normalization will calculate purely candidate-local `effective_runtime_weights` inside the `MetaAlphaEngine.combine_scores()` evaluation scope without persisting or overwriting global configurations.

### 10. Does it preserve 500k liquidity?
Yes. `EXECUTION_SETTINGS['min_volume_threshold']` remains 500,000, and `ExecutionEngine.filter_by_liquidity()` is unchanged.

### 11. Does it preserve 75th-percentile BEAR?
Yes. The `RegimeEngine` and strategy selection (`bear_alpha_threshold: 0.75`) logic are explicitly preserved.

### 12. Does it preserve 30% individual cap?
Yes. `PORTFOLIO_SETTINGS['max_individual_weight']` remains 0.30.

### 13. Does it preserve 40% sector cap?
Yes. `PORTFOLIO_SETTINGS['max_sector_exposure']` remains 0.40.

---

## Conclusion & Implementation Decision
**IMPLEMENT**.
The forensic audit proves that the optional-provider reweighting layer can be fully constrained within `MetaAlphaEngine`, sitting cleanly on top of and outside the frozen P6-11B core model (`ScoringEngine` / `RankingEngine`). The core factor NaN semantics will remain untouched. Minimum effective model coverage is safely set to 50% (requiring the core `factor` to be present).
