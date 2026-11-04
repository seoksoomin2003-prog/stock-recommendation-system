# P6-17 Frozen Core Baseline

## 1. 500,000 Liquidity Minimum
- **File**: `core/decision_engine.py`
- **Class/Function**: `DecisionEngine.generate_decisions()`
- **Line**: 76
- **Current Logic**: `if c.get('volume', 0) < 500000:`
- **Semantics**: Hard minimum of 500,000 shares. If missing (NaN) or 0, defaults to `0`, triggering rejection with `LIQUIDITY_REJECTED` flag.

## 2. 75th Percentile BEAR Threshold
- **File**: `core/decision_engine.py`
- **Class/Function**: `DecisionEngine._rank_candidates()`
- **Line**: 254-258
- **Current Logic**: `if regime == "BEAR": threshold = 0.75 ... if c.get('alpha_percentile', 1.0) >= threshold`
- **Semantics**: Candidates with an Alpha percentile score lower than the 75th percentile are strictly dropped prior to `MODEL_RANK_E` scoring.

## 3. Portfolio Exposure Caps
- **File**: `core/decision_engine.py` & `core/portfolio_engine.py`
- **Current Logic**: 
  - `technology_cap` / `max_sector_exposure` = 0.40 (40%)
  - `security_hard_ceiling` / `max_individual_weight` = 0.30 (30%)

## 4. MODEL_RANK_E Aggregation
- **File**: `core/ranking_engine.py`
- **Class/Function**: `RankingEngine.calculate_model_rank_e()`
- **Semantics**: Merges Volatility, Confidence, Capital, and Liquidity into a unified composite ranking model. Called strictly on Candidates passing the BEAR and Liquidity filters.
