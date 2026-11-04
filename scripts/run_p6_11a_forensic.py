import json
import os

def create_reports():
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)

    # 1. Dependency Graph
    dep_graph = {
        "nodes": [
            {"id": "DATA", "type": "Source"},
            {"id": "YFinanceMarketProvider", "type": "Adapter"},
            {"id": "YFinanceFinancialProvider", "type": "Adapter"},
            {"id": "SECProviderAdapter", "type": "Adapter"},
            {"id": "FactorEngine", "type": "Engine"},
            {"id": "ScoringEngine", "type": "Engine"},
            {"id": "RankingEngine", "type": "Engine"},
            {"id": "PortfolioEngine", "type": "Engine"},
            {"id": "DecisionEngine", "type": "Engine"}
        ],
        "edges": [
            {"source": "DATA", "target": "YFinanceMarketProvider"},
            {"source": "DATA", "target": "YFinanceFinancialProvider"},
            {"source": "DATA", "target": "SECProviderAdapter"},
            {"source": "YFinanceMarketProvider", "target": "FactorEngine"},
            {"source": "YFinanceFinancialProvider", "target": "FactorEngine"},
            {"source": "SECProviderAdapter", "target": "FactorEngine"},
            {"source": "FactorEngine", "target": "ScoringEngine"},
            {"source": "ScoringEngine", "target": "RankingEngine"},
            {"source": "RankingEngine", "target": "PortfolioEngine"},
            {"source": "PortfolioEngine", "target": "DecisionEngine"}
        ]
    }
    with open(f"{reports_dir}/P6-11A_EXISTING_ENGINE_DEPENDENCY_GRAPH.json", "w") as f:
        json.dump(dep_graph, f, indent=4)

    # 2. Forensic Matrix
    matrix = [
        {
            "component": "Momentum Factor", "file": "core/factor_engine.py", "class": "FactorEngine", "function": "calculate_momentum",
            "role": "Alpha Factor", "input": "prices", "output": "pd.Series", "formula": "(ret_12m - ret_1m).shift(1) on monthly data",
            "data_source": "YFinance", "timestamp_semantics": "Monthly resampled, shifted by 1 month", "pit_status": "PASS",
            "current_status": "USED", "weight": "0.35 (MODEL_0)", "normalization": "Robust", "missing_policy": "Median Fill",
            "regime_dependency": "Adjusted in RegimeEngine", "capital_dependency": "NONE", "liquidity_dependency": "NONE",
            "sector_dependency": "NONE", "research_reference": "MODEL_0 Baseline", "production_usage": "YES", "duplicate_of": "NONE",
            "risk_level": "P2 MEDIUM", "finding": "Monthly shift(1) causes 1-month lag, which is overly conservative for daily trading.", "recommended_action": "INVESTIGATE"
        },
        {
            "component": "Value Factor", "file": "core/factor_engine.py", "class": "FactorEngine", "function": "calculate_value",
            "role": "Alpha Factor", "input": "financial_data", "output": "pd.Series", "formula": "1/PER + 1/PBR",
            "data_source": "YFinance / SEC", "timestamp_semantics": "Dependent on provider", "pit_status": "FAIL (if YFinance)",
            "current_status": "USED", "weight": "0.20 (MODEL_0)", "normalization": "Robust", "missing_policy": "Median Fill",
            "regime_dependency": "Adjusted in RegimeEngine", "capital_dependency": "NONE", "liquidity_dependency": "NONE",
            "sector_dependency": "NONE", "research_reference": "MODEL_0 Baseline", "production_usage": "YES", "duplicate_of": "NONE",
            "risk_level": "P0 CRITICAL", "finding": "YFinanceFinancialProvider uses current info.get('trailingPE') which leaks future data if used in backtest.", "recommended_action": "REPAIR_REQUIRED"
        },
        {
            "component": "YFinanceMarketProvider", "file": "providers/adapters.py", "class": "YFinanceMarketProvider", "function": "fetch",
            "role": "Market Data", "input": "ticker", "output": "NormalizedData", "formula": "N/A",
            "data_source": "yfinance", "timestamp_semantics": "Daily Close", "pit_status": "FAIL",
            "current_status": "USED", "weight": "N/A", "normalization": "N/A", "missing_policy": "Dropna",
            "regime_dependency": "NONE", "capital_dependency": "NONE", "liquidity_dependency": "NONE",
            "sector_dependency": "NONE", "research_reference": "N/A", "production_usage": "YES", "duplicate_of": "NONE",
            "risk_level": "P0 CRITICAL", "finding": "auto_adjust=True leaks future corporate actions into historical prices.", "recommended_action": "REPAIR_REQUIRED"
        },
        {
            "component": "PortfolioEngine Sector Cap", "file": "core/portfolio_engine.py", "class": "PortfolioEngine", "function": "_apply_sector_constraints",
            "role": "Risk Constraint", "input": "weights, sectors", "output": "pd.Series", "formula": "Proportional reduction",
            "data_source": "N/A", "timestamp_semantics": "N/A", "pit_status": "PASS",
            "current_status": "USED", "weight": "N/A", "normalization": "N/A", "missing_policy": "N/A",
            "regime_dependency": "NONE", "capital_dependency": "NONE", "liquidity_dependency": "NONE",
            "sector_dependency": "YES", "research_reference": "40% Tech Cap", "production_usage": "YES", "duplicate_of": "NONE",
            "risk_level": "P1 HIGH", "finding": "Config uses 0.35 (35%) max_sector_exposure instead of the approved 0.40 (40%).", "recommended_action": "REPAIR_REQUIRED"
        },
        {
            "component": "PortfolioEngine Sizing Cap", "file": "core/portfolio_engine.py", "class": "PortfolioEngine", "function": "_apply_concentration_limit",
            "role": "Risk Constraint", "input": "weights", "output": "pd.Series", "formula": "Iterative clipping",
            "data_source": "N/A", "timestamp_semantics": "N/A", "pit_status": "PASS",
            "current_status": "USED", "weight": "N/A", "normalization": "N/A", "missing_policy": "N/A",
            "regime_dependency": "NONE", "capital_dependency": "NONE", "liquidity_dependency": "NONE",
            "sector_dependency": "NONE", "research_reference": "30% hard ceiling", "production_usage": "YES", "duplicate_of": "NONE",
            "risk_level": "P1 HIGH", "finding": "Config uses 0.20 (20%) max_individual_weight instead of the approved 0.30 (30%).", "recommended_action": "REPAIR_REQUIRED"
        },
        {
            "component": "MODEL_RANK_E Implementation", "file": "core/decision_engine.py", "class": "DecisionEngine", "function": "_rank_candidates",
            "role": "Ranking", "input": "candidates", "output": "ranked candidates", "formula": "alpha*0.6 + entry_readiness*0.4",
            "data_source": "N/A", "timestamp_semantics": "N/A", "pit_status": "PASS",
            "current_status": "MOCKED", "weight": "N/A", "normalization": "N/A", "missing_policy": "N/A",
            "regime_dependency": "YES", "capital_dependency": "FAIL", "liquidity_dependency": "FAIL",
            "sector_dependency": "NONE", "research_reference": "MODEL_RANK_E", "production_usage": "YES", "duplicate_of": "NONE",
            "risk_level": "P1 HIGH", "finding": "MODEL_RANK_E does not exist in RankingEngine. It is heavily simplified/mocked in DecisionEngine without Capital/Liquidity inputs.", "recommended_action": "REPAIR_REQUIRED"
        }
    ]
    with open(f"{reports_dir}/P6-11A_EXISTING_ENGINE_FORENSIC_MATRIX.json", "w") as f:
        json.dump(matrix, f, indent=4)

    # 3. MD Report
    md = """# Executive Summary
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
"""
    with open(f"{reports_dir}/P6-11A_EXISTING_ENGINE_FORENSIC_AUDIT.md", "w") as f:
        f.write(md)

if __name__ == "__main__":
    create_reports()
