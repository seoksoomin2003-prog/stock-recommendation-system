# Executive Summary
The existing engine is functional but contains critical Point-in-Time (PIT) leakage risks regarding `yfinance` usage. Additionally, there is significant drift between the research-approved parameters (e.g., 40% Sector Cap, 30% Individual Cap) and the production configuration (35% Sector Cap, 20% Individual Cap). `MODEL_RANK_E` is completely absent from the actual RankingEngine and is only mocked in the DecisionEngine.

# 1. Current Production Decision Path
`DATA` -> `YFinanceMarketProvider` / `SECProviderAdapter` -> `FactorEngine` -> `ScoringEngine` -> `PortfolioEngine`

# 2. Existing Alpha Engine Audit
Delegated directly to `FactorEngine`.

# 3. Existing Factor Engine Audit
- **Momentum**: `(ret_12m - ret_1m).shift(1)` on monthly data. Highly lagged.
- **Value**: `1/PER + 1/PBR`. Relies on current stats if YFinance is used.
- **Quality**: `ROE + ProfitMargin`.
- **Low Volatility**: `returns.rolling(22).std().shift(1)`.

# 4. Existing Scoring Engine Audit
Uses `DEFAULT_FACTOR_WEIGHTS` (Momentum 0.35, Quality 0.25, Value 0.20, Low Vol 0.20). Applies Adaptive Deduction Model for tail risks (MDD, Volatility, Skewness).

# 5. MODEL_0 Audit
`DEFAULT_FACTOR_WEIGHTS` matches the approved `MODEL_0` perfectly.

# 6. MODEL_RANK_E Audit
**MISSING**. The `RankingEngine` class has standard percentile/z-score logic, but no actual `MODEL_RANK_E` implementation.

# 7. QuantInputAdapter Audit
Data is piped through `providers/adapters.py`.

# 8. PIT / Timestamp Audit
**FAIL**. `YFinanceMarketProvider` uses `auto_adjust=True`, meaning historical prices are retroactively modified for future splits, leaking future data into historical runs.

# 9. yfinance Governance Audit
**CRITICAL**. `YFinanceFinancialProvider` fetches current `info.get('trailingPE')` and returns it as historical data. This completely ruins backtest validity.

# 10. Regime Audit
`RegimeEngine` adjusts factor weights based on Bull/Bear.

# 11. Ranking Audit
`RankingEngine` exists but lacks the requested dual-ranking and capital awareness.

# 12. Capital-Aware Audit
Absent from `PortfolioEngine`. 

# 13. Liquidity Audit
`EXECUTION_SETTINGS` uses a 1,000,000 min volume limit. `DecisionEngine` uses 500,000. Drift identified.

# 14. Sector Constraint Audit
`PORTFOLIO_SETTINGS` enforces 35% max sector. Research approved 40%.

# 15. Alpha vs Entry Timing Separation Audit
Alpha and Entry Timing are structurally separated up until `DecisionEngine` mixes them.

# 16. Research vs Production Drift
**YES**. Configuration drift (caps, weights, liquidity thresholds).

# 17. Duplicate / Legacy / Dead Code
`RankingEngine.construct_long_short_portfolio` is legacy dead code.

# 18. Test Quality
Tests generally assert structural existence but fail to detect PIT data leakage.

# 19. Performance / Memory
Uses simple Pandas operations. Efficient enough for small universes.

# 20. Security / Secrets
`utils/config.py` contains hardcoded `NEWS_API_KEY`.

# 21. Critical Findings
- `auto_adjust=True` in `YFinanceMarketProvider`.
- `info.get('trailingPE')` in `YFinanceFinancialProvider` used historically.

# 22. Repair Candidates
- `providers/adapters.py` (Remove auto_adjust, block historical financial fetch from yf).
- `utils/config.py` (Update caps to 30%/40%).
- `core/ranking_engine.py` (Implement actual `MODEL_RANK_E`).

# 23. Removal Candidates
- Dead code in `RankingEngine`.

# 24. Recommended Repair Order
1. Fix PIT leakages in providers.
2. Update Config to match User-Approved constraints.
3. Build `MODEL_RANK_E` in `RankingEngine`.

# 25. Final Verdict
C. REPAIR REQUIRED BEFORE P6-11B
