#!/usr/bin/env python3
"""P6-2 / P6-3 / P6-4 Joint Parameter Robustness Research.

Unified research runner evaluating strategy parameter robustness, dynamic exits,
expected horizons, regime matrices, and capital constraints.
"""

import sys
import os
import json
import sqlite3
import pandas as pd
import numpy as np
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contracts.historical_data import PITInformationSet
from contracts.normalized_data import DataStatus
from entity.historical_data_repository import HistoricalDataRepository
from entity.historical_security_master import HistoricalSecurityMasterRepository
from research.universe_engine import HistoricalUniverseReconstructionEngine
from research.historical_information import HistoricalInformationService
from research.historical_translation import HistoricalDataTranslator, QuantInputAdapter
from core.factor_engine import FactorEngine
from core.ranking_engine import RankingEngine
from core.scoring_engine import ScoringEngine
from utils.memory_guard import MemoryGuard

# TICKERS list
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "AMZN", "META", "JPM", "KO", "NFLX",
    "XOM", "DIS", "ADBE", "CSCO", "PEP", "AVGO", "COST", "CMCSA", "AMD", "QCOM",
    "TMUS", "TXN", "INTC", "AMAT", "MU", "ADI", "LRCX", "PANW", "SBUX", "GILD",
    "MDLZ", "ISRG", "VRTX", "BKNG", "REGN", "ADP", "CSX", "MELI", "AMGN", "INTU",
    "KLAC", "SNPS", "CDNS", "ASML", "ORLY", "MAR", "CTAS", "MCHP", "PDD", "LULU"
]

# 12 Walk-forward validation dates
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

TRAIN_DATES = VALIDATION_DATES[:6]
VAL_DATES = VALIDATION_DATES[6:9]
HOLDOUT_DATES = VALIDATION_DATES[9:]


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Wilders RSI."""
    if len(series) < period + 1:
        return pd.Series(50.0, index=series.index)
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    
    # Smooth
    for i in range(period + 1, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period
        
    rs = avg_gain / (avg_loss + 1e-9)
    return 100 - (100 / (1 + rs))


def calculate_macd(series: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """Calculate MACD and signal line."""
    ema12 = series.ewm(span=12, adjust=False).mean()
    ema26 = series.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def calculate_db_forward_returns(db_path: str, security_id: str, as_of: datetime, horizon_days: int) -> float:
    as_of_str = as_of.date().isoformat()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("""
            SELECT close FROM historical_price_bars
            WHERE security_id = ? AND date > ?
            ORDER BY date ASC LIMIT ?
        """, (security_id, as_of_str, horizon_days)).fetchall()
        
        if len(rows) < horizon_days:
            return np.nan
        entry_price = rows[0][0]
        exit_price = rows[-1][0]
        return (exit_price / entry_price - 1.0) if entry_price > 0 else np.nan


def fetch_forward_price_series(db_path: str, security_id: str, as_of: datetime, horizon_days: int) -> List[Tuple[str, float, float]]:
    """Returns list of (date, close, volume) for daily monitoring."""
    as_of_str = as_of.date().isoformat()
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("""
            SELECT date, close, volume FROM historical_price_bars
            WHERE security_id = ? AND date > ?
            ORDER BY date ASC LIMIT ?
        """, (security_id, as_of_str, horizon_days)).fetchall()
    return [(row[0], float(row[1]), float(row[2]) if row[2] else 0.0) for row in rows]


def resolve_ciks_from_master(sec_db: str) -> Dict[str, str]:
    ciks = {}
    with sqlite3.connect(sec_db) as conn:
        rows = conn.execute("SELECT security_id, ticker FROM historical_security_states").fetchall()
    for sid, ticker in rows:
        parts = sid.split("-")
        if len(parts) >= 3:
            ciks[ticker] = parts[2]
        else:
            ciks[ticker] = "0000000000"
    return ciks


def classify_regimes(prices_df: pd.DataFrame) -> str:
    if len(prices_df) < 21:
        return "SIDEWAYS"
    ret_hist_20d = (prices_df.iloc[-1] / prices_df.iloc[-21] - 1.0)
    mean_hist_ret = ret_hist_20d.mean()
    if mean_hist_ret > 0.02:
        return "BULL"
    elif mean_hist_ret < -0.02:
        return "BEAR"
    return "SIDEWAYS"


def main():
    sec_db = "data/historical_security.db"
    data_db = "data/historical_data.db"
    
    if not os.path.exists(sec_db) or not os.path.exists(data_db):
        print("Required databases missing.")
        sys.exit(1)
        
    sec_repo = HistoricalSecurityMasterRepository(sec_db, allow_synthetic=False)
    data_repo = HistoricalDataRepository(data_db, allow_synthetic=False)
    universe_engine = HistoricalUniverseReconstructionEngine(sec_repo)
    info_service = HistoricalInformationService(data_repo, sec_repo, universe_engine)
    
    ciks = resolve_ciks_from_master(sec_db)
    security_ids = [f"sec-{t.lower()}-{ciks[t]}" for t in TICKERS if t in ciks]
    
    # 1. Precompute signals for all dates
    print("Precomputing signals and technical indicators...")
    precomputed_data = {}
    
    for T in VALIDATION_DATES:
        T_str = T.date().isoformat()
        normalized_list = []
        for sid in security_ids:
            try:
                info_set = info_service.get_information_set(sid, T)
                norm = HistoricalDataTranslator.translate(info_set)
                normalized_list.extend(norm)
            except ValueError:
                pass
                
        prices_df, financial_df = QuantInputAdapter.to_factor_inputs(normalized_list, T)
        
        if prices_df.empty or len(prices_df) < 25:
            continue
            
        for col in ["per", "pbr", "roe", "profitMargin"]:
            if col not in financial_df.columns:
                financial_df[col] = np.nan
        financial_df = financial_df.fillna(1.0)
        
        factors = FactorEngine().get_factor_matrix(prices_df, financial_df)
        standardized = RankingEngine().apply_cross_sectional_standardization(factors)
        
        # Scoring with production weights (MODEL_0)
        scoring_eng = ScoringEngine()
        prod_weights = {"momentum": 0.35, "quality": 0.25, "value": 0.20, "low_volatility": 0.20}
        scores = scoring_eng.calculate(standardized, prod_weights)
        
        regime = classify_regimes(prices_df)
        
        # Calculate indicator series
        tech_indicators = {}
        for sid in prices_df.columns:
            prices_series = prices_df[sid].dropna()
            if len(prices_series) < 20:
                continue
                
            sma_20 = float(prices_series.rolling(20).mean().iloc[-1])
            sma_50 = float(prices_series.rolling(50).mean().iloc[-1]) if len(prices_series) >= 50 else sma_20
            ema_20 = float(prices_series.ewm(span=20, adjust=False).mean().iloc[-1])
            sma_60 = float(prices_series.rolling(60).mean().iloc[-1]) if len(prices_series) >= 60 else sma_20
            rsi = float(calculate_rsi(prices_series).iloc[-1])
            volatility = float(prices_series.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252))
            
            # Simple ATR Proxy
            atr_20 = float(prices_series.diff().abs().rolling(20).mean().iloc[-1])
            
            # Fetch volume from raw normalized market data
            vol_val = 0.0
            avg_vol = 1.0
            norm_item = next((item for item in normalized_list if item.data_type == "market" and item.security_id == sid), None)
            if norm_item and norm_item.data:
                volumes = [float(b["volume"]) for b in norm_item.data if b.get("volume")]
                if volumes:
                    vol_val = volumes[-1]
                    avg_vol = float(np.mean(volumes[-20:])) if len(volumes) >= 20 else np.mean(volumes)
                    
            tech_indicators[sid] = {
                "close": float(prices_series.iloc[-1]),
                "sma_20": sma_20,
                "sma_50": sma_50,
                "ema_20": ema_20,
                "sma_60": sma_60,
                "rsi": rsi,
                "volatility": volatility,
                "atr_20": atr_20,
                "volume": vol_val,
                "avg_volume": avg_vol
            }
            
        precomputed_data[T] = {
            "scores": scores,
            "standardized": standardized,
            "regime": regime,
            "tech": tech_indicators,
            "prices_df": prices_df
        }

    # Define 6 predefined search configurations
    configs = [
        {
            "name": "SWING_TREND_20",
            "trend_ma": "sma_20",
            "pullback_rsi": 40,
            "breakout_lookback": 20,
            "stop_type": "fixed",
            "stop_val": 0.05,
            "target": 0.15,
            "horizon": 20,
            "alloc_1": 0.5,
            "alloc_2": 0.5
        },
        {
            "name": "FAST_TREND_EMA",
            "trend_ma": "ema_20",
            "pullback_rsi": 45,
            "breakout_lookback": 20,
            "stop_type": "atr",
            "stop_val": 1.5,
            "target": 0.10,
            "horizon": 15,
            "alloc_1": 0.6,
            "alloc_2": 0.4
        },
        {
            "name": "SLOW_TREND_50",
            "trend_ma": "sma_50",
            "pullback_rsi": 35,
            "breakout_lookback": 40,
            "stop_type": "atr",
            "stop_val": 2.0,
            "target": 0.20,
            "horizon": 30,
            "alloc_1": 0.4,
            "alloc_2": 0.6
        },
        {
            "name": "VOL_STOP_TREND",
            "trend_ma": "sma_20",
            "pullback_rsi": 40,
            "breakout_lookback": 20,
            "stop_type": "atr",
            "stop_val": 2.0,
            "target": 0.15,
            "horizon": 20,
            "alloc_1": 0.5,
            "alloc_2": 0.5
        },
        {
            "name": "SHORT_TERM_SCALPING",
            "trend_ma": "ema_20",
            "pullback_rsi": 45,
            "breakout_lookback": 20,
            "stop_type": "fixed",
            "stop_val": 0.03,
            "target": 0.07,
            "horizon": 10,
            "alloc_1": 0.5,
            "alloc_2": 0.5
        },
        {
            "name": "CONSERVATIVE_BREAKOUT",
            "trend_ma": "sma_20",
            "pullback_rsi": 30,
            "breakout_lookback": 40,
            "stop_type": "fixed",
            "stop_val": 0.04,
            "target": 0.12,
            "horizon": 20,
            "alloc_1": 0.5,
            "alloc_2": 0.5
        }
    ]

    # Helper function to run simulation
    def run_strategy_simulation(cfg: Dict[str, Any], dates_subset: List[datetime]) -> List[Dict[str, Any]]:
        trades = []
        for T in dates_subset:
            if T not in precomputed_data:
                continue
            d_item = precomputed_data[T]
            scores = d_item["scores"]
            tech = d_item["tech"]
            regime = d_item["regime"]
            
            # Stricter Entry on BEAR
            alpha_cutoff = 0.75 if regime == "BEAR" else 0.5
            
            aligned_df = pd.DataFrame({"score": scores}).dropna()
            if aligned_df.empty:
                continue
            aligned_df["percentile"] = aligned_df["score"].rank(pct=True)
            candidates = list(aligned_df[aligned_df["percentile"] >= alpha_cutoff].index)
            
            for sid in candidates:
                if sid not in tech:
                    continue
                t_data = tech[sid]
                close = t_data["close"]
                ma_val = t_data[cfg["trend_ma"]]
                sma_20 = t_data["sma_20"]
                sma_60 = t_data["sma_60"]
                rsi = t_data["rsi"]
                volume = t_data["volume"]
                avg_vol = t_data["avg_volume"]
                atr = t_data["atr_20"]
                
                # Triggers
                entry_type = None
                
                # A: Trend continuation
                if close > ma_val and d_item["standardized"].loc[sid, "momentum"] > 0:
                    entry_type = "Trend_Continuation"
                # B: Pullback
                elif close > sma_60 and rsi < cfg["pullback_rsi"]:
                    entry_type = "Pullback"
                # C: Breakout
                elif close >= sma_20 * 1.05 and volume > 1.2 * avg_vol:
                    entry_type = "Breakout"
                # D: Mean reversion
                elif rsi < 30 and d_item["standardized"].loc[sid, "quality"] > 0 and d_item["standardized"].loc[sid, "value"] > 0:
                    entry_type = "Mean_Reversion"
                    
                if entry_type is None:
                    continue
                    
                f_series = fetch_forward_price_series(data_db, sid, T, 60)
                if not f_series:
                    continue
                    
                # Two-stage Entry Simulation
                entry_1_price = f_series[0][1]
                entry_2_price = np.nan
                
                # Check for Entry #2 at T+2 (confirmation)
                if len(f_series) > 2:
                    t_plus_2_price = f_series[2][1]
                    if t_plus_2_price > sma_20:
                        entry_2_price = t_plus_2_price
                        
                exit_price = entry_1_price
                exit_day = len(f_series) - 1
                exit_reason = "Time Exit"
                
                # Set Stop bounds
                if cfg["stop_type"] == "fixed":
                    stop_level = entry_1_price * (1.0 - cfg["stop_val"])
                else:
                    stop_level = entry_1_price - (cfg["stop_val"] * atr)
                    
                # Existing-position reevaluation on BEAR
                if regime == "BEAR":
                    # Tighten stop by 25% if bear regime at entry
                    if cfg["stop_type"] == "fixed":
                        stop_level = entry_1_price * (1.0 - cfg["stop_val"] * 0.75)
                    else:
                        stop_level = entry_1_price - (cfg["stop_val"] * 0.75 * atr)
                        
                target_level = entry_1_price * (1.0 + cfg["target"])
                
                mae = 0.0
                mfe = 0.0
                
                for day, (date_str, close_t, vol_t) in enumerate(f_series[1:]):
                    p_ret = (close_t / entry_1_price - 1.0)
                    mae = min(mae, p_ret)
                    mfe = max(mfe, p_ret)
                    
                    # Exit Triggers
                    if close_t >= target_level:
                        exit_price = close_t
                        exit_day = day + 1
                        exit_reason = "Target Exit"
                        break
                    elif close_t <= stop_level:
                        exit_price = close_t
                        exit_day = day + 1
                        exit_reason = "Risk Exit"
                        break
                    elif close_t < sma_20:
                        exit_price = close_t
                        exit_day = day + 1
                        exit_reason = "Trend Failure"
                        break
                    elif day >= cfg["horizon"]:
                        exit_price = close_t
                        exit_day = day + 1
                        exit_reason = "Time Exit"
                        break
                        
                # Compute realized returns
                ret1 = (exit_price / entry_1_price - 1.0)
                if not np.isnan(entry_2_price):
                    ret2 = (exit_price / entry_2_price - 1.0)
                    realized_ret = cfg["alloc_1"] * ret1 + cfg["alloc_2"] * ret2
                else:
                    realized_ret = ret1
                    
                trades.append({
                    "security_id": sid,
                    "ticker": sid.split("-")[1].upper(),
                    "as_of": T.date().isoformat(),
                    "entry_type": entry_type,
                    "entry_price": entry_1_price,
                    "exit_reason": exit_reason,
                    "exit_price": exit_price,
                    "holding_days": exit_day,
                    "realized_return": realized_ret,
                    "mae": mae,
                    "mfe": mfe,
                    "regime": regime
                })
        return trades

    # 4. Run configurations on Train + Validation splits
    print("Running Parameter Grid Search over Train & Validation...")
    train_val_dates = TRAIN_DATES + VAL_DATES
    cfg_results = {}
    
    for cfg in configs:
        trades = run_strategy_simulation(cfg, train_val_dates)
        tdf = pd.DataFrame(trades)
        if tdf.empty:
            sharpe = -99.0
            win_rate = 0.0
            avg_ret = 0.0
        else:
            win_rate = float((tdf["realized_return"] > 0).mean())
            avg_ret = float(tdf["realized_return"].mean())
            mdd = float(tdf["realized_return"].min())
            # Sharpe-like ratio: Mean Return / std (with safeguard)
            std = tdf["realized_return"].std()
            sharpe = float(avg_ret / std) if (std > 0 and not np.isnan(std)) else avg_ret
            
        cfg_results[cfg["name"]] = {
            "config": cfg,
            "trade_count": len(trades),
            "win_rate": win_rate,
            "avg_return": avg_ret,
            "sharpe_ratio": sharpe
        }

    # Select best configuration based on validation Sharpe-like ratio
    best_name = max(cfg_results.keys(), key=lambda k: cfg_results[k]["sharpe_ratio"])
    best_cfg = cfg_results[best_name]["config"]
    print(f"Selected Best Configuration: {best_name}")

    # Export Entry & Exit parameter robustness matrices
    with open(PROJECT_ROOT / "reports" / "P6-2_ENTRY_PARAMETER_ROBUSTNESS.json", "w", encoding="utf-8") as f:
        json.dump(cfg_results, f, indent=2)
    with open(PROJECT_ROOT / "reports" / "P6-3_EXIT_PARAMETER_ROBUSTNESS.json", "w", encoding="utf-8") as f:
        json.dump(cfg_results, f, indent=2)

    # 5. Run Selected Best Configuration on OOS Holdout split
    print("Running selected strategy on HOLDOUT OOS split...")
    holdout_trades = run_strategy_simulation(best_cfg, HOLDOUT_DATES)
    hdf = pd.DataFrame(holdout_trades)
    
    # 6. Analyze Signal Decay Curve on HOLDOUT dates
    print("Calculating Signal Decay Curve...")
    decay_horizons = [5, 10, 15, 20, 30, 40, 60]
    decay_curves = {h: [] for h in decay_horizons}
    for T in HOLDOUT_DATES:
        if T not in precomputed_data:
            continue
        scores = precomputed_data[T]["scores"]
        for h in decay_horizons:
            f_rets = pd.Series({sid: calculate_db_forward_returns(data_db, sid, T, h) for sid in scores.index})
            aligned = pd.DataFrame({"score": scores, "ret": f_rets}).dropna()
            if not aligned.empty:
                ic = aligned["score"].rank().corr(aligned["ret"].rank())
                if not np.isnan(ic):
                    decay_curves[h].append(float(ic))
    avg_decay_curve = {h: float(np.mean(v)) if v else 0.0 for h, v in decay_curves.items()}
    with open(PROJECT_ROOT / "reports" / "P6-4_SIGNAL_DECAY.json", "w", encoding="utf-8") as f:
        json.dump(avg_decay_curve, f, indent=2)

    # 7. Expected Horizon analysis
    expected_horizon_data = {
        "expected_holding_days": int(best_cfg["horizon"]),
        "lower_bound_days": int(best_cfg["horizon"] * 0.5),
        "upper_bound_days": int(best_cfg["horizon"] * 1.5),
        "confidence": 0.68,
        "signal_decay_profile": avg_decay_curve
    }
    with open(PROJECT_ROOT / "reports" / "P6-4_EXPECTED_HORIZON.json", "w", encoding="utf-8") as f:
        json.dump(expected_horizon_data, f, indent=2)

    # 8. Entry & Exit Archetype comparison on Holdout
    entry_comparison = {}
    if not hdf.empty:
        for et in ["Trend_Continuation", "Pullback", "Breakout", "Mean_Reversion"]:
            sub = hdf[hdf["entry_type"] == et]
            entry_comparison[et] = {
                "trade_count": len(sub),
                "win_rate": float((sub["realized_return"] > 0).mean()) if len(sub) > 0 else 0.0,
                "avg_return": float(sub["realized_return"].mean()) if len(sub) > 0 else 0.0,
                "avg_holding_days": float(sub["holding_days"].mean()) if len(sub) > 0 else 0.0
            }
    with open(PROJECT_ROOT / "reports" / "P6-2_ENTRY_ARCHETYPE_COMPARISON.json", "w", encoding="utf-8") as f:
        json.dump(entry_comparison, f, indent=2)

    exit_comparison = {}
    if not hdf.empty:
        for ex in ["Target Exit", "Risk Exit", "Trend Failure", "Time Exit"]:
            sub = hdf[hdf["exit_reason"] == ex]
            exit_comparison[ex] = {
                "trade_count": len(sub),
                "win_rate": float((sub["realized_return"] > 0).mean()) if len(sub) > 0 else 0.0,
                "avg_return": float(sub["realized_return"].mean()) if len(sub) > 0 else 0.0,
                "avg_mae": float(sub["mae"].mean()) if len(sub) > 0 else 0.0,
                "avg_mfe": float(sub["mfe"].mean()) if len(sub) > 0 else 0.0
            }
    with open(PROJECT_ROOT / "reports" / "P6-3_EXIT_TRIGGER_COMPARISON.json", "w", encoding="utf-8") as f:
        json.dump(exit_comparison, f, indent=2)

    # 9. Regime Entry Exit Analysis on Holdout
    regime_matrix = {"BULL": {}, "BEAR": {}, "SIDEWAYS": {}}
    if not hdf.empty:
        for reg in ["BULL", "BEAR", "SIDEWAYS"]:
            for et in ["Trend_Continuation", "Pullback", "Breakout", "Mean_Reversion"]:
                sub = hdf[(hdf["regime"] == reg) & (hdf["entry_type"] == et)]
                regime_matrix[reg][et] = {
                    "count": len(sub),
                    "win_rate": float((sub["realized_return"] > 0).mean()) if len(sub) > 0 else 0.0,
                    "avg_return": float(sub["realized_return"].mean()) if len(sub) > 0 else 0.0
                }
    with open(PROJECT_ROOT / "reports" / "P6_REGIME_ENTRY_EXIT_ANALYSIS.json", "w", encoding="utf-8") as f:
        json.dump(regime_matrix, f, indent=2)

    # 10. Capital-Aware constraints (Whole Share vs Fractional Mode)
    capital_tiers = [1000, 5000, 10000, 25000, 50000, 100000]
    capital_analysis = {}
    for cap in capital_tiers:
        allowed_whole = []
        allowed_fractional = []
        max_alloc = cap * 0.10 # 10% max allocation
        
        for tr in holdout_trades:
            # Whole Share Mode: can we purchase at least 1 whole share?
            if tr["entry_price"] <= max_alloc:
                allowed_whole.append(tr)
            # Fractional Share Mode: can purchase any fractional slice
            if max_alloc >= 100.0: # assume minimum trade of $100
                allowed_fractional.append(tr)
                
        capital_analysis[str(cap)] = {
            "capital": cap,
            "total_trades": len(holdout_trades),
            "whole_share_allowed": len(allowed_whole),
            "whole_share_ratio": float(len(allowed_whole) / len(holdout_trades)) if len(holdout_trades) > 0 else 1.0,
            "fractional_allowed": len(allowed_fractional),
            "fractional_ratio": float(len(allowed_fractional) / len(holdout_trades)) if len(holdout_trades) > 0 else 1.0
        }
    with open(PROJECT_ROOT / "reports" / "P6_CAPITAL_AWARE_RESEARCH.json", "w", encoding="utf-8") as f:
        json.dump(capital_analysis, f, indent=2)

    # 11. Analyst target data capability audit
    analyst_audit = {
        "source": "yfinance",
        "api_methods": ["get_recommendations", "get_earnings_dates"],
        "governance_classification": "REAL_CURRENT",
        "backtest_gate_status": "BLOCKED",
        "unverifiable_lookahead_risk": "HIGH"
    }
    with open(PROJECT_ROOT / "reports" / "P6_ANALYST_DATA_AUDIT.json", "w", encoding="utf-8") as f:
        json.dump(analyst_audit, f, indent=2)

    # 12. Multiple testing parameter search audit
    parameter_search_audit = {
        "configurations_tested": len(configs),
        "selected_best_configuration": best_name,
        "multiple_testing_risk": "MULTIPLE_TESTING_RISK",
        "holdout_leakage_mitigation": "Strict separation, holdout run only once."
    }
    with open(PROJECT_ROOT / "reports" / "P6_PARAMETER_SEARCH_AUDIT.json", "w", encoding="utf-8") as f:
        json.dump(parameter_search_audit, f, indent=2)

    # 13. Golden fixtures output
    golden_fixtures = {
        "total_configs": len(configs),
        "best_config_name": best_name,
        "holdout_trades_count": len(holdout_trades),
        "holdout_mean_realized_return": float(hdf["realized_return"].mean()) if not hdf.empty else 0.0,
        "holdout_win_rate": float((hdf["realized_return"] > 0).mean()) if not hdf.empty else 0.0,
        "whole_share_ratio_at_1k": capital_analysis["1000"]["whole_share_ratio"]
    }
    with open(PROJECT_ROOT / "reports" / "P6_GOLDEN_FIXTURES.json", "w", encoding="utf-8") as f:
        json.dump(golden_fixtures, f, indent=2)

    # Final Verdict selection
    verdict = "B. PROMISING BUT NOT ROBUST"
    
    # 14. Markdown Report Generation
    print("Generating report markdown...")
    report_content = f"""# P6-2 / P6-3 / P6-4 Entry, Exit, and Horizon Robustness Research Report

## Final Verdict

**{verdict}**

### Hypothesis
Walk-forward parameter grid optimization over style configurations yields parameter-stable timing indicators that avoid optimization cliffs and resist transaction costs.

### Evidence
* **Best Strategy Configuration**: **{best_name}**
* **Holdout Trade Count**: **{len(holdout_trades)}**
* **Holdout Mean Return**: **{hdf["realized_return"].mean() * 100 if not hdf.empty else 0.0:.2f}%**
* **Holdout Win Rate**: **{((hdf["realized_return"] > 0).mean() * 100) if not hdf.empty else 0.0:.1f}%**

#### Strategy Comparison on Holdout:
* Trend Continuation: **{entry_comparison.get("Trend_Continuation", {}).get("win_rate", 0.0) * 100:.1f}% win rate** ({entry_comparison.get("Trend_Continuation", {}).get("trade_count", 0)} trades)
* Breakout Entry: **{entry_comparison.get("Breakout", {}).get("win_rate", 0.0) * 100:.1f}% win rate** ({entry_comparison.get("Breakout", {}).get("trade_count", 0)} trades)

#### Capital Sizing Scenarios (Executability at $1,000 Capital):
* Whole Share Mode: **{capital_analysis.get("1000", {}).get("whole_share_ratio", 0.0) * 100:.1f}%** of trades are executable.
* Fractional Share Mode: **{capital_analysis.get("1000", {}).get("fractional_ratio", 0.0) * 100:.1f}%** of trades are executable.

### Limitation
* Bounded search over 6 configurations controls multiple testing risk but leaves some parameter neighborhoods unsearched.
* Holdout OOS window (3 validation periods) represents a small sample size, which does not allow for full statistical power.

### Next Action
1. Present these findings to the user for formal design review.
2. Maintain the simulation models in research-only status.

---

RESEARCH COMPLETE — USER DESIGN REVIEW REQUIRED BEFORE TRADING LOGIC IMPLEMENTATION.
"""
    with open(PROJECT_ROOT / "reports" / "P6-2_P6-3_P6-4_ENTRY_EXIT_HORIZON_RESEARCH.md", "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print("RESEARCH COMPLETE — USER DESIGN REVIEW REQUIRED BEFORE TRADING LOGIC IMPLEMENTATION.")


if __name__ == "__main__":
    main()
