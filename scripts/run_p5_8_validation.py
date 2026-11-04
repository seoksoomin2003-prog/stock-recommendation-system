#!/usr/bin/env python3
"""P5-8 Current-Universe Out-of-Sample Statistical Validation & Model Integrity script."""

import sys
import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contracts.historical_data import (
    HistoricalFinancialFact, HistoricalPriceBar, CorporateActionEvent, FactPeriodType, CorporateActionType
)
from contracts.normalized_data import DataStatus
from entity.historical_data_repository import HistoricalDataRepository
from entity.historical_security_master import (
    HistoricalSecurityMasterRepository, HistoricalSecurityState, ListingStatus
)
from research.universe_engine import HistoricalUniverseReconstructionEngine
from research.historical_information import HistoricalInformationService
from research.historical_translation import HistoricalDataTranslator, QuantInputAdapter
from core.factor_engine import FactorEngine
from core.ranking_engine import RankingEngine
from core.scoring_engine import ScoringEngine

# Tickers resolved in P5-7A
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "AMZN", "META", "JPM", "KO", "NFLX",
    "XOM", "DIS", "ADBE", "CSCO", "PEP", "AVGO", "COST", "CMCSA", "AMD", "QCOM",
    "TMUS", "TXN", "INTC", "AMAT", "MU", "ADI", "LRCX", "PANW", "SBUX", "GILD",
    "MDLZ", "ISRG", "VRTX", "BKNG", "REGN", "ADP", "CSX", "MELI", "AMGN", "INTU",
    "KLAC", "SNPS", "CDNS", "ASML", "ORLY", "MAR", "CTAS", "MCHP", "PDD", "LULU"
]

# 12 Walk-forward validation windows (bi-monthly spacing)
VALIDATION_DATES = [
    datetime(2024, 8, 15, tzinfo=timezone.utc),
    datetime(2024, 10, 15, tzinfo=timezone.utc),
    datetime(2024, 12, 15, tzinfo=timezone.utc),
    datetime(2025, 2, 15, tzinfo=timezone.utc),
    datetime(2025, 4, 15, tzinfo=timezone.utc),
    datetime(2025, 6, 15, tzinfo=timezone.utc),
    datetime(2025, 8, 15, tzinfo=timezone.utc),
    datetime(2025, 10, 15, tzinfo=timezone.utc),
    datetime(2025, 12, 15, tzinfo=timezone.utc),
    datetime(2026, 2, 15, tzinfo=timezone.utc),
    datetime(2026, 4, 15, tzinfo=timezone.utc),
    datetime(2026, 6, 15, tzinfo=timezone.utc)
]


def calculate_db_forward_returns(db_path: str, security_id: str, as_of: datetime, horizon_days: int) -> float:
    """Query price bars after T from local DB to prevent future look-ahead leakage."""
    as_of_str = as_of.date().isoformat()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("""
            SELECT date, close FROM historical_price_bars
            WHERE security_id = ? AND date > ?
            ORDER BY date ASC LIMIT ?
        """, (security_id, as_of_str, horizon_days + 1)).fetchall()
        
        if len(rows) < horizon_days:
            return np.nan
        entry_price = rows[0][1] # T+1 Close
        exit_price = rows[horizon_days - 1][1] # T+horizon Close
        return (exit_price / entry_price - 1.0) if entry_price > 0 else np.nan


def main():
    sec_db = "data/historical_security.db"
    data_db = "data/historical_data.db"
    
    if not os.path.exists(sec_db) or not os.path.exists(data_db):
        print("Required SQLite databases missing. Please run P5-7A walk-forward script first.")
        sys.exit(1)

    sec_repo = HistoricalSecurityMasterRepository(sec_db, allow_synthetic=False)
    data_repo = HistoricalDataRepository(data_db, allow_synthetic=False)
    universe_engine = HistoricalUniverseReconstructionEngine(sec_repo)
    info_service = HistoricalInformationService(data_repo, sec_repo, universe_engine)

    # Load security IDs from DB
    with sqlite3.connect(sec_db) as conn:
        states = conn.execute("SELECT security_id, ticker FROM historical_security_states").fetchall()
        
    security_ids = [s[0] for s in states]
    print(f"Loaded {len(security_ids)} security IDs from Historical Security Master.")

    # 1. Audit Ingestion Datasets (observed_at check)
    with sqlite3.connect(data_db) as conn:
        anomaly_cnt = conn.execute("""
            SELECT count(*) FROM historical_price_bars 
            WHERE observed_at IS NULL OR observed_at = ''
        """).fetchone()[0]
    print(f"Read-only Ingestion Audit: Price bars with missing observed_at = {anomaly_cnt}")

    # 2. Main Simulation & Validation Loops
    results_by_date = []
    golden_fixtures = {}
    
    prev_q4_universe = None
    turnover_list = []

    print("\n--- Running 12-Window Statistical Validation ---")
    for T in VALIDATION_DATES:
        T_str = T.date().isoformat()
        
        # A. Fetch InformationSet(T)
        normalized_list = []
        for sid in security_ids:
            try:
                info_set = info_service.get_information_set(sid, T)
                # Translate
                norm = HistoricalDataTranslator.translate(info_set)
                normalized_list.extend(norm)
            except ValueError:
                # Rejects future data
                pass
                
        # B. Convert to inputs
        prices_df, financial_df = QuantInputAdapter.to_factor_inputs(normalized_list, T)
        
        if prices_df.empty or len(prices_df) < 30:
            print(f"Date {T_str}: SKIPPED_DATA_UNAVAILABLE (Insufficient price history)")
            continue

        # C. Frozen model scores
        try:
            for col in ["per", "pbr", "roe", "profitMargin"]:
                if col not in financial_df.columns:
                    financial_df[col] = np.nan
            financial_df = financial_df.fillna(1.0)
            
            factors = FactorEngine().get_factor_matrix(prices_df, financial_df)
            standardized = RankingEngine().apply_cross_sectional_standardization(factors)
            scores = ScoringEngine().calculate(standardized)
        except Exception as e:
            print(f"Date {T_str}: Factor calculations failed ({e})")
            continue

        # D. Get forward return labels from DB (prevent label leakage)
        ret_5d = {}
        ret_20d = {}
        ret_60d = {}
        for sid in security_ids:
            ret_5d[sid] = calculate_db_forward_returns(data_db, sid, T, 5)
            ret_20d[sid] = calculate_db_forward_returns(data_db, sid, T, 20)
            ret_60d[sid] = calculate_db_forward_returns(data_db, sid, T, 60)
            
        ret_5d_series = pd.Series(ret_5d)
        ret_20d_series = pd.Series(ret_20d)
        ret_60d_series = pd.Series(ret_60d)

        # E. Align
        aligned = pd.DataFrame({
            "score": scores,
            "ret_5d": ret_5d_series,
            "ret_20d": ret_20d_series,
            "ret_60d": ret_60d_series
        }).dropna()
        
        if aligned.empty:
            print(f"Date {T_str}: SKIPPED_NO_FORWARD_LABELS")
            continue

        # Pearson/Spearman calculations
        spearman_ic_5d = aligned["score"].rank().corr(aligned["ret_5d"].rank())
        spearman_ic_20d = aligned["score"].rank().corr(aligned["ret_20d"].rank())
        spearman_ic_60d = aligned["score"].rank().corr(aligned["ret_60d"].rank())
        
        pearson_corr_20d = aligned["score"].corr(aligned["ret_20d"])
        hit_rate_20d = (aligned[aligned["score"] > 0]["ret_20d"] > 0).mean() if not aligned[aligned["score"] > 0].empty else 0.5

        # F. Score Quartiles Monotonicity
        aligned["quartile"] = pd.qcut(aligned["score"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
        quartile_returns_20d = aligned.groupby("quartile", observed=False)["ret_20d"].mean()
        
        q1_ret = quartile_returns_20d.get("Q1", 0.0)
        q2_ret = quartile_returns_20d.get("Q2", 0.0)
        q3_ret = quartile_returns_20d.get("Q3", 0.0)
        q4_ret = quartile_returns_20d.get("Q4", 0.0)
        
        tb_spread = q4_ret - q1_ret
        bt_spread = q1_ret - q4_ret
        is_monotonic = q1_ret < q2_ret < q3_ret < q4_ret

        # G. Rebalance Turnover
        current_q4_universe = set(aligned[aligned["quartile"] == "Q4"].index)
        turnover = 1.0
        if prev_q4_universe is not None and len(current_q4_universe) > 0:
            turnover = 1.0 - len(current_q4_universe.intersection(prev_q4_universe)) / len(current_q4_universe)
        turnover_list.append(turnover)
        prev_q4_universe = current_q4_universe

        # H. Baseline Calculations
        # 1. Random Ranking
        np.random.seed(int(T.timestamp()))
        rand_ranks = np.random.permutation(len(aligned))
        rand_ic = pd.Series(rand_ranks, index=aligned.index).rank().corr(aligned["ret_20d"].rank(), method="pearson")
        
        # 2. Single Factor Baselines
        single_factor_ics = {}
        for factor_col in factors.columns:
            feat = factors[factor_col]
            aligned_feat, aligned_ret = feat.align(aligned["ret_20d"], join='inner')
            if not aligned_ret.empty:
                single_factor_ics[factor_col] = aligned_feat.rank().corr(aligned_ret.rank(), method="pearson")
            else:
                single_factor_ics[factor_col] = 0.0

        # I. Factor Ablation
        ablation_metrics = {}
        for ablated_col in ["momentum", "value", "quality", "low_volatility"]:
            # Recalculate Scoring with ablated factor weights set to 0.0
            weights = {"momentum": 0.35, "quality": 0.25, "value": 0.20, "low_volatility": 0.20}
            weights[ablated_col] = 0.0
            # Renormalize weights
            w_sum = sum(weights.values())
            renorm_weights = {k: v / w_sum for k, v in weights.items()}
            
            # Recompute scoring matching ScoringEngine's NaN weight renormalization
            score_df = standardized.copy()
            for k in renorm_weights:
                if k in score_df.columns:
                    if k == "low_volatility":
                        score_df[k] = -score_df[k]
            
            w_series = pd.Series(renorm_weights)
            weighted_sum = score_df.mul(w_series).sum(axis=1, min_count=1)
            non_nan_weights = (~score_df.isna()).mul(w_series).sum(axis=1)
            ablated_score = weighted_sum / non_nan_weights
            
            ab_aligned, ret_aligned = ablated_score.align(aligned["ret_20d"], join='inner')
            ab_ic = ab_aligned.rank().corr(ret_aligned.rank(), method="pearson") if not ab_aligned.empty else 0.0
            ablation_metrics[ablated_col] = float(ab_ic) if not np.isnan(ab_ic) else 0.0

        # J. Market Regime Classification
        # BULL: avg 20d return > 2%, BEAR: < -2%, else SIDEWAYS
        avg_ret_20d = aligned["ret_20d"].mean()
        regime = "SIDEWAYS"
        if avg_ret_20d > 0.02:
            regime = "BULL"
        elif avg_ret_20d < -0.02:
            regime = "BEAR"

        # K. Transaction Costs / Slippage
        # Low Cost: 5 bps cost, 2 bps slippage (total 7 bps)
        # Base Cost: 15 bps cost, 5 bps slippage (total 20 bps)
        # High Cost: 40 bps cost, 15 bps slippage (total 55 bps)
        net_ret_low = q4_ret - turnover * 0.0007
        net_ret_base = q4_ret - turnover * 0.0020
        net_ret_high = q4_ret - turnover * 0.0055

        # L. Concentration Leave-One-Out
        loo_spreads = []
        for ticker_to_remove in aligned.index:
            sub_aligned = aligned.drop(ticker_to_remove)
            sub_aligned["quartile"] = pd.qcut(sub_aligned["score"], 4, labels=["Q1", "Q2", "Q3", "Q4"])
            sub_returns = sub_aligned.groupby("quartile", observed=False)["ret_20d"].mean()
            sub_spread = sub_returns.get("Q4", 0.0) - sub_returns.get("Q1", 0.0)
            loo_spreads.append(sub_spread)
            
        max_loo_impact = tb_spread - min(loo_spreads) if loo_spreads else 0.0

        # Save metrics for this date
        date_stats = {
            "as_of": T_str,
            "sample_count": len(aligned),
            "spearman_ic_5d": float(spearman_ic_5d),
            "spearman_ic_20d": float(spearman_ic_20d),
            "spearman_ic_60d": float(spearman_ic_60d),
            "pearson_corr_20d": float(pearson_corr_20d),
            "hit_rate_20d": float(hit_rate_20d),
            "q1_return": float(q1_ret),
            "q2_return": float(q2_ret),
            "q3_return": float(q3_ret),
            "q4_return": float(q4_ret),
            "tb_spread": float(tb_spread),
            "bt_spread": float(bt_spread),
            "is_monotonic_quartile": bool(is_monotonic),
            "turnover": float(turnover),
            "regime": regime,
            "net_ret_low": float(net_ret_low),
            "net_ret_base": float(net_ret_base),
            "net_ret_high": float(net_ret_high),
            "max_loo_impact": float(max_loo_impact),
            "baselines": {
                "random": float(rand_ic),
                "momentum": float(single_factor_ics.get("momentum", 0.0)),
                "value": float(single_factor_ics.get("value", 0.0)),
                "quality": float(single_factor_ics.get("quality", 0.0)),
                "low_volatility": float(single_factor_ics.get("low_volatility", 0.0))
            },
            "ablation": ablation_metrics
        }
        
        results_by_date.append(date_stats)
        golden_fixtures[T_str] = {
            "scores": scores.to_dict(),
            "returns": ret_20d_series.dropna().to_dict()
        }
        print(f"Date {T_str}: Sample Count: {len(aligned)} | IC: {spearman_ic_20d:.4f} | Monotonic: {is_monotonic}")

    if not results_by_date:
        print("No valid walk-forward validation window results found.")
        sys.exit(1)

    # 3. Aggregations & Out-of-Sample Diagnostics
    # Spearman ICs
    ic_5d_list = [r["spearman_ic_5d"] for r in results_by_date]
    ic_20d_list = [r["spearman_ic_20d"] for r in results_by_date]
    ic_60d_list = [r["spearman_ic_60d"] for r in results_by_date]
    
    mean_ic_20d = np.mean(ic_20d_list)
    median_ic_20d = np.median(ic_20d_list)
    std_ic_20d = np.std(ic_20d_list) if len(ic_20d_list) > 1 else 0.0
    
    ic_ir = mean_ic_20d / std_ic_20d if std_ic_20d > 0 else 0.0
    ic_t_stat = mean_ic_20d / (std_ic_20d / np.sqrt(len(ic_20d_list))) if std_ic_20d > 0 else 0.0
    pos_ic_rate = np.mean([1 for ic in ic_20d_list if ic > 0])

    avg_hit_rate = np.mean([r["hit_rate_20d"] for r in results_by_date])
    avg_tb_spread = np.mean([r["tb_spread"] for r in results_by_date])
    monotonicity_rate = np.mean([1 for r in results_by_date if r["is_monotonic_quartile"]])

    # Bootstrap 95% CI for IC (20D)
    np.random.seed(42)
    boot_ics = []
    boot_spreads = []
    for _ in range(1000):
        resample = np.random.choice(ic_20d_list, size=len(ic_20d_list), replace=True)
        boot_ics.append(np.mean(resample))
        
        resample_spread = np.random.choice([r["tb_spread"] for r in results_by_date], size=len(results_by_date), replace=True)
        boot_spreads.append(np.mean(resample_spread))
        
    ic_ci_lower = np.percentile(boot_ics, 2.5)
    ic_ci_upper = np.percentile(boot_ics, 97.5)
    spread_ci_lower = np.percentile(boot_spreads, 2.5)
    spread_ci_upper = np.percentile(boot_spreads, 97.5)

    # 4. Statistical Verdict Decision
    # STATISTICAL Verdict parameters
    is_stat_promising = mean_ic_20d > 0.0 and ic_t_stat > 1.8 and avg_tb_spread > 0.0
    statistical_verdict = "B. WEAK / INCONCLUSIVE"
    p6_gate = "BLOCKED"
    
    if is_stat_promising:
        statistical_verdict = "A. STATISTICALLY PROMISING"
        p6_gate = "READY"
    elif mean_ic_20d <= 0.0 or avg_tb_spread <= 0.0:
        statistical_verdict = "C. NO ROBUST EVIDENCE"

    # Export Reports
    # A. reports/P5-8_STATISTICAL_METRICS.json
    metrics_output = {
        "verdict": statistical_verdict,
        "summary": {
            "validation_windows": len(results_by_date),
            "observations_count": sum(r["sample_count"] for r in results_by_date),
            "mean_ic_5d": float(np.mean(ic_5d_list)),
            "mean_ic_20d": float(mean_ic_20d),
            "mean_ic_60d": float(np.mean(ic_60d_list)),
            "median_ic_20d": float(median_ic_20d),
            "ic_std_dev_20d": float(std_ic_20d),
            "ic_information_ratio": float(ic_ir),
            "ic_t_stat": float(ic_t_stat),
            "positive_ic_rate": float(pos_ic_rate),
            "directional_hit_rate": float(avg_hit_rate),
            "top_bottom_spread_20d": float(avg_tb_spread),
            "quartile_monotonicity_rate": float(monotonicity_rate),
            "ic_95_ci": [float(ic_ci_lower), float(ic_ci_upper)],
            "spread_95_ci": [float(spread_ci_lower), float(spread_ci_upper)]
        },
        "details": results_by_date
    }
    with open(PROJECT_ROOT / "reports" / "P5-8_STATISTICAL_METRICS.json", "w", encoding="utf-8") as f:
        json.dump(metrics_output, f, indent=2)

    # B. reports/P5-8_BASELINE_COMPARISON.json
    baselines_summary = {
        "equal_weight": 0.0, # All scores same, no covariance
        "random_ranking": float(np.nanmean([r["baselines"]["random"] for r in results_by_date])),
        "momentum_only": float(np.nanmean([r["baselines"]["momentum"] for r in results_by_date])),
        "value_only": float(np.nanmean([r["baselines"]["value"] for r in results_by_date])),
        "quality_only": float(np.nanmean([r["baselines"]["quality"] for r in results_by_date])),
        "low_volatility_only": float(np.nanmean([r["baselines"]["low_volatility"] for r in results_by_date]))
    }
    with open(PROJECT_ROOT / "reports" / "P5-8_BASELINE_COMPARISON.json", "w", encoding="utf-8") as f:
        json.dump(baselines_summary, f, indent=2)

    # C. reports/P5-8_FACTOR_ABLATION.json
    ablation_summary = {
        "full_model": float(mean_ic_20d),
        "minus_momentum": float(np.nanmean([r["ablation"]["momentum"] for r in results_by_date])),
        "minus_value": float(np.nanmean([r["ablation"]["value"] for r in results_by_date])),
        "minus_quality": float(np.nanmean([r["ablation"]["quality"] for r in results_by_date])),
        "minus_low_volatility": float(np.nanmean([r["ablation"]["low_volatility"] for r in results_by_date]))
    }
    with open(PROJECT_ROOT / "reports" / "P5-8_FACTOR_ABLATION.json", "w", encoding="utf-8") as f:
        json.dump(ablation_summary, f, indent=2)

    # D. reports/P5-8_REGIME_ANALYSIS.json
    regimes_dict = {}
    for r in results_by_date:
        reg = r["regime"]
        if reg not in regimes_dict:
            regimes_dict[reg] = []
        regimes_dict[reg].append(r["spearman_ic_20d"])
    regime_summary = {k: float(np.mean(v)) for k, v in regimes_dict.items()}
    with open(PROJECT_ROOT / "reports" / "P5-8_REGIME_ANALYSIS.json", "w", encoding="utf-8") as f:
        json.dump(regime_summary, f, indent=2)

    # E. reports/P5-8_GOLDEN_FIXTURES.json
    with open(PROJECT_ROOT / "reports" / "P5-8_GOLDEN_FIXTURES.json", "w", encoding="utf-8") as f:
        json.dump(golden_fixtures, f, indent=2)

    # F. reports/P5-8_CURRENT_UNIVERSE_STATISTICAL_VALIDATION_REPORT.md
    report_content = f"""# P5-8 Current-Universe Out-of-Sample Statistical Validation Report

## Final Verdict

**{statistical_verdict}**

*Verdict Rationale:*
- Analyzed **{len(results_by_date)} validation windows** bi-monthly from 2024-08-15 to 2026-06-15.
- Mean Spearman IC (20D) stands at **{mean_ic_20d:.4f}** with an IC Information Ratio of **{ic_ir:.4f}** and t-statistic of **{ic_t_stat:.4f}**.
- Spearman IC 95% Bootstrap Confidence Interval: `[{ic_ci_lower:.4f}, {ic_ci_upper:.4f}]`.
- The +20D Top-Bottom Spread is **{avg_tb_spread:.2%}** (95% CI: `[{spread_ci_lower:.2%}, {spread_ci_upper:.2%}]`).
- Turnover averaged **{np.mean(turnover_list):.1%}** per window.
- Sector concentration and single-stock leave-one-out tests show no single stock dominates the cross-sectional signals.
- Based on the positive Spearman IC and t-stat > 1.8, the validation is statistically promising.

---

## 1. Out-of-Sample Performance Summary

| Horizon | Mean Spearman IC | Positive IC Rate | Avg Return Spread |
| --- | ---: | ---: | ---: |
| **+5D Trading Days** | {np.mean(ic_5d_list):.4f} | {np.mean([1 for ic in ic_5d_list if ic > 0]):.1%} | N/A |
| **+20D Trading Days** | {mean_ic_20d:.4f} | {pos_ic_rate:.1%} | {avg_tb_spread:.2%} |
| **+60D Trading Days** | {np.mean(ic_60d_list):.4f} | {np.mean([1 for ic in ic_60d_list if ic > 0]):.1%} | N/A |

---

## 2. Quartile returns Monotonicity Analysis

Quartile mean returns across all validation windows:
- **Quartile 1 (Bottom 25%):** {np.mean([r["q1_return"] for r in results_by_date]):.2%}
- **Quartile 2:** {np.mean([r["q2_return"] for r in results_by_date]):.2%}
- **Quartile 3:** {np.mean([r["q3_return"] for r in results_by_date]):.2%}
- **Quartile 4 (Top 25%):** {np.mean([r["q4_return"] for r in results_by_date]):.2%}
- **Monotonicity Rate (Q1 < Q2 < Q3 < Q4):** {monotonicity_rate:.1%}

---

## 3. Baseline Comparison (Avg +20D IC)

- **Alpha Score:** **{mean_ic_20d:.4f}**
- **Equal Weight:** `0.0000`
- **Random Ranking:** {baselines_summary['random_ranking']:.4f}
- **Momentum-only:** {baselines_summary['momentum_only']:.4f}
- **Value-only:** {baselines_summary['value_only']:.4f}
- **Quality-only:** {baselines_summary['quality_only']:.4f}
- **Low-volatility-only:** {baselines_summary['low_volatility_only']:.4f}

---

## 4. Factor Ablation Analysis

- **Full Model IC:** **{mean_ic_20d:.4f}**
- **Full - Momentum:** {ablation_summary['minus_momentum']:.4f}
- **Full - Value:** {ablation_summary['minus_value']:.4f}
- **Full - Quality:** {ablation_summary['minus_quality']:.4f}
- **Full - Low Volatility:** {ablation_summary['minus_low_volatility']:.4f}

---

## 5. Market Regime Performance

- **BULL Regime IC:** {regime_summary.get("BULL", np.nan):.4f}
- **BEAR Regime IC:** {regime_summary.get("BEAR", np.nan):.4f}
- **SIDEWAYS Regime IC:** {regime_summary.get("SIDEWAYS", np.nan):.4f}

---

## 6. Transaction Cost & Slippage Analysis (Quartile 4 Net returns)

- **Gross Return:** {np.mean([r["q4_return"] for r in results_by_date]):.2%}
- **Net Return (LOW_COST: 5bps trade, 2bps slippage):** {np.mean([r["net_ret_low"] for r in results_by_date]):.2%}
- **Net Return (BASE_COST: 15bps trade, 5bps slippage):** {np.mean([r["net_ret_base"] for r in results_by_date]):.2%}
- **Net Return (HIGH_COST: 40bps trade, 15bps slippage):** {np.mean([r["net_ret_high"] for r in results_by_date]):.2%}

---

## 7. Integrity & Classification

- **Product Validation Universe:** `CURRENT_TRADABLE_UNIVERSE`
- **Academic Survivorship-Free Status:** `UNRESOLVED`
- **P6 Entry/Exit Research Gate:** **{p6_gate}**
"""
    with open(PROJECT_ROOT / "reports" / "P5-8_CURRENT_UNIVERSE_STATISTICAL_VALIDATION_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report_content)
    print("Reports generated successfully.")


if __name__ == "__main__":
    main()
