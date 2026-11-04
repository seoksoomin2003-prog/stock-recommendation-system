# P6-11B Trading Logic Traceability

| Logic Component | Research Source | Approved Decision | Production Implementation | Testing |
|---|---|---|---|---|
| Alpha/Entry Sep | P6-1 | Strict separation of WHAT/WHEN | `DecisionEngine` evaluates Alpha and Readiness independently before `calculate_model_rank_e`. | `test_alpha_entry_separation` |
| Entry #1 (40%) | P6-5 | 40% allocation, Regime-Adaptive | Configured in `utils/config.py`, applied via `DecisionEngine` BEAR threshold filtering. | N/A (Regression) |
| Entry #2 (60%) | P6-6 | Close > EMA20 | Implemented in `DecisionEngine.evaluate_existing_position`. | `test_entry_2_ema_wait`, `test_entry_2_ema_trigger` |
| MODEL_RANK_E | P6-4 | Capital-aware composite | `RankingEngine.calculate_model_rank_e` | `test_p6_11a_repair` |
| Liquidity | P6-8 | Hard min + soft penalty | 500k volume hard min in `evaluate_portfolio`, soft penalty in `RankingEngine`. | N/A (Regression) |
| Hard Stop | P6-3 | 2.0 ATR absolute priority | Evaluated first in exit hierarchy. | `test_exit_hierarchy_hard_stop_priority` |
| Thesis Inval. | P6-3 | Close < EMA20 | Evaluated second in exit hierarchy. | `test_exit_hierarchy_thesis_invalidation` |
| Dynamic Trail | P6-3 | Trailing stop never loosens | Tracked in state, evaluated third. | N/A (Regression) |
| 30D Review | P6-9 | Re-underwrite, not forced exit | Evaluated using `np.busday_count`. Exits if alpha < 0. | N/A (Regression) |
| Re-entry Cooldown | P6-9 | 3 trading days | Checked in `evaluate_portfolio`, pushed to WATCHLIST. | `test_reentry_cooldown` |
| Capital Tiers | P6-2 | Support 1k, 5k, 100k+ | Sizing uses target capital weighting with fractional share support. | N/A (Regression) |
