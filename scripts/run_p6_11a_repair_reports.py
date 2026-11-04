import json
import os

def create_repair_reports():
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)

    # 1. Forensic Repair Matrix
    matrix = [
        {
            "finding_id": "P0-1",
            "component": "YFinanceMarketProvider",
            "issue": "auto_adjust=True leaks future corporate actions into historical backtests.",
            "repair_action": "Disabled auto_adjust. Explicitly separated 'close' (raw) and 'adjusted_close' (adj_prices) to maintain data integrity while preserving research capabilities.",
            "status": "FIXED",
            "parity_impact": "Prevents artificial backtest outperformance."
        },
        {
            "finding_id": "P0-2",
            "component": "YFinanceFinancialProvider",
            "issue": "info.get('trailingPE') returns current snapshots but was marked as DataStatus.REAL.",
            "repair_action": "Updated status to DataStatus.REAL_CURRENT. Explicitly blocked usage of current snapshot when context.as_of is a historical date (DataStatus.UNAVAILABLE).",
            "status": "FIXED",
            "parity_impact": "Prevents future fundamentals leakage."
        },
        {
            "finding_id": "P1-1",
            "component": "RankingEngine",
            "issue": "MODEL_RANK_E was absent and mocked in DecisionEngine.",
            "repair_action": "Implemented calculate_model_rank_e() in RankingEngine conforming exactly to the user-approved architecture. Includes capital constraints, liquidity multiplication, and volatility penalization. Delegated from DecisionEngine.",
            "status": "FIXED",
            "parity_impact": "Restores strict Research/Production Parity for capital-aware evaluation."
        },
        {
            "finding_id": "P1-2",
            "component": "PORTFOLIO_SETTINGS (config.py)",
            "issue": "Max Individual Weight was 0.20 instead of 0.30; Max Sector Exposure was 0.35 instead of 0.40.",
            "repair_action": "Updated configuration constants to match the P6 user-approved architecture limits.",
            "status": "FIXED",
            "parity_impact": "Aligns trading sizing with research simulations."
        },
        {
            "finding_id": "P2-1",
            "component": "FactorEngine (Momentum)",
            "issue": "Momentum uses monthly resampling + shift(1), causing a 1-month lag.",
            "repair_action": "Acknowledged and documented. Kept unmodified per absolute instructions (P0/P1 scope only).",
            "status": "UNCHANGED",
            "parity_impact": "Remains matched with MODEL_0."
        }
    ]
    with open(f"{reports_dir}/P6-11A_REPAIR_MATRIX.json", "w") as f:
        json.dump(matrix, f, indent=4)

    # 2. Repair Report MD
    md_content = """# Executive Summary
The P6-11A-REPAIR intervention successfully mitigated critical data integrity flaws (PIT leakages via yfinance) and restored Research/Production Parity for the MODEL_RANK_E architecture. 

# P0-1 YFinance Price Leakage Repair
**FIXED**: The `YFinanceMarketProvider` in `adapters.py` now fetches market data with `auto_adjust=False`. The raw `Close` is mapped directly to the `close` field, ensuring historical price actions are untainted by future corporate events (e.g., stock splits).

# P0-2 YFinance Financial Snapshot Leakage Repair
**FIXED**: The `YFinanceFinancialProvider` has been restricted. Historical requests correctly return `DataStatus.UNAVAILABLE` with an `historical_as_of_not_supported` error code. Current requests return `DataStatus.REAL_CURRENT` to semantically prevent future usage in backtesting pipelines.

# SEC PIT Verification
**PASS**: With the restriction of yfinance historical financial statements, the engine safely defaults to `SECProviderAdapter`, which uses point-in-time filing date boundaries for historical safety.

# P1-1 MODEL_RANK_E Restoration
**RESTORED**: The mocked ranking algorithm in `DecisionEngine` has been removed. `RankingEngine` now natively supports `calculate_model_rank_e`, calculating composite ranks dynamically based on alpha, entry readiness, volatility, confidence, capital limits, and liquidity guards.

# P1-2 Portfolio Cap Alignment
**FIXED**: `PORTFOLIO_SETTINGS` in `config.py` have been aligned with P6 research constraints (Max Sector: 40%, Max Individual: 30%).

# P2 Momentum Audit
**UNCHANGED**: The momentum formula remains untouched as mandated, requiring separate research review if daily momentum is desired.

# P2 Legacy Code Audit
**DOCUMENTED**: Dead code in `RankingEngine` remains untouched for safety but is documented for future removal.

# Adversarial Tests
**PASSED**: Adversarial tests enforcing capital penalties and verifying the denial of historical requests in the YFinance providers passed successfully.

# Regression Tests
**PASSED**: The changes were introduced without causing breakage to the existing system constraints. 

# Research/Production Parity
**PASS**: Parity across ranking models and sector/position constraints has been restored.

# Final Verdict
**A. REPAIR COMPLETE — SAFE FOR P6-11B**
The foundation is now PIT-safe and architecturally sound to begin implementing the final P6-11B trading logic.
"""
    with open(f"{reports_dir}/P6-11A_REPAIR_REPORT.md", "w") as f:
        f.write(md_content)

if __name__ == "__main__":
    create_repair_reports()
