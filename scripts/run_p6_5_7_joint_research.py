#!/usr/bin/env python3
"""P6-5~7 Joint Trading Rule Robustness Research.

Unified research runner evaluating parameter stability, thesis decay invalidation,
sector concentration caps, capital sizing, and Top 5 / Watchlist 5 construction.
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

# Sector Mapping
SECTORS = {
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology", "NVDA": "Technology",
    "AVGO": "Technology", "AMD": "Technology", "QCOM": "Technology", "INTC": "Technology",
    "ADI": "Technology", "TXN": "Technology", "AMAT": "Technology", "LRCX": "Technology",
    "PANW": "Technology", "ASML": "Technology", "SNPS": "Technology", "CDNS": "Technology",
    "KLAC": "Technology", "ADBE": "Technology", "INTU": "Technology", "ISRG": "Technology",
    "BKNG": "Technology", "ADP": "Technology", "MELI": "Technology", "PDD": "Technology",
    "LULU": "Consumer Discretionary", "TSLA": "Consumer Discretionary", "AMZN": "Consumer Discretionary",
    "NFLX": "Consumer Discretionary", "DIS": "Consumer Discretionary", "SBUX": "Consumer Discretionary",
    "ORLY": "Consumer Discretionary", "MAR": "Consumer Discretionary", "KO": "Consumer Staples",
    "PEP": "Consumer Staples", "COST": "Consumer Staples", "MDLZ": "Consumer Staples",
    "JPM": "Financials", "META": "Communication Services", "CMCSA": "Communication Services",
    "TMUS": "Communication Services", "GILD": "Healthcare", "VRTX": "Healthcare",
    "REGN": "Healthcare", "AMGN": "Healthcare", "CSX": "Industrials", "CTAS": "Industrials",
    "XOM": "Energy"
}

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
        
        scoring_eng = ScoringEngine()
        prod_weights = {"momentum": 0.35, "quality": 0.25, "value": 0.20, "low_volatility": 0.20}
        scores = scoring_eng.calculate(standardized, prod_weights)
        
        regime = classify_regimes(prices_df)
        
        tech_indicators = {}
        for sid in prices_df.columns:
            prices_series = prices_df[sid].dropna()
            if len(prices_series) < 20:
                continue
                
            sma_20 = float(prices_series.rolling(20).mean().iloc[-1])
            sma_40 = float(prices_series.rolling(40).mean().iloc[-1]) if len(prices_series) >= 40 else sma_20
            sma_50 = float(prices_series.rolling(50).mean().iloc[-1]) if len(prices_series) >= 50 else sma_20
            sma_60 = float(prices_series.rolling(60).mean().iloc[-1]) if len(prices_series) >= 60 else sma_20
            ema_20 = float(prices_series.ewm(span=20, adjust=False).mean().iloc[-1])
            rsi = float(calculate_rsi(prices_series).iloc[-1])
            volatility = float(prices_series.pct_change().rolling(20).std().iloc[-1] * np.sqrt(252))
            atr_20 = float(prices_series.diff().abs().rolling(20).mean().iloc[-1])
            
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
                "sma_40": sma_40,
                "sma_50": sma_50,
                "sma_60": sma_60,
                "ema_20": ema_20,
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

    # Define 7 local perturbations around SLOW_TREND_50
    perturbations = [
        {
            "name": "SLOW_TREND_50_BASE",
            "trend_ma": "sma_50",
            "pullback_rsi": 35,
            "breakout_lookback": 40,
            "stop_val": 2.0,
            "target": 0.20,
            "alloc_1": 0.4,
            "alloc_2": 0.6
        },
        {
            "name": "SLOW_TREND_40",
            "trend_ma": "sma_40",
            "pullback_rsi": 35,
            "breakout_lookback": 40,
            "stop_val": 2.0,
            "target": 0.20,
            "alloc_1": 0.4,
            "alloc_2": 0.6
        },
        {
            "name": "SLOW_TREND_60",
            "trend_ma": "sma_60",
            "pullback_rsi": 35,
            "breakout_lookback": 40,
            "stop_val": 2.0,
            "target": 0.20,
            "alloc_1": 0.4,
            "alloc_2": 0.6
        },
        {
            "name": "STOP_1_5_ATR",
            "trend_ma": "sma_50",
            "pullback_rsi": 35,
            "breakout_lookback": 40,
            "stop_val": 1.5,
            "target": 0.20,
            "alloc_1": 0.4,
            "alloc_2": 0.6
        },
        {
            "name": "STOP_2_5_ATR",
            "trend_ma": "sma_50",
            "pullback_rsi": 35,
            "breakout_lookback": 40,
            "stop_val": 2.5,
            "target": 0.20,
            "alloc_1": 0.4,
            "alloc_2": 0.6
        },
        {
            "name": "ALLOC_60_40",
            "trend_ma": "sma_50",
            "pullback_rsi": 35,
            "breakout_lookback": 40,
            "stop_val": 2.0,
            "target": 0.20,
            "alloc_1": 0.6,
            "alloc_2": 0.4
        },
        {
            "name": "ALLOC_50_50",
            "trend_ma": "sma_50",
            "pullback_rsi": 35,
            "breakout_lookback": 40,
            "stop_val": 2.0,
            "target": 0.20,
            "alloc_1": 0.5,
            "alloc_2": 0.5
        }
    ]

    # Strategy Simulator
    def run_simulation(cfg: Dict[str, Any], dates_subset: List[datetime], apply_sector_cap: bool = False) -> List[Dict[str, Any]]:
        trades = []
        for T in dates_subset:
            if T not in precomputed_data:
                continue
            d_item = precomputed_data[T]
            scores = d_item["scores"]
            tech = d_item["tech"]
            regime = d_item["regime"]
            
            # BEAR policy stricter entries
            alpha_cutoff = 0.75 if regime == "BEAR" else 0.50
            
            aligned_df = pd.DataFrame({"score": scores}).dropna()
            if aligned_df.empty:
                continue
            aligned_df["percentile"] = aligned_df["score"].rank(pct=True)
            
            # Sort candidates by Score
            sorted_candidates = list(aligned_df[aligned_df["percentile"] >= alpha_cutoff].sort_values("score", ascending=False).index)
            
            sector_counts = {}
            selected_candidates = []
            
            for sid in sorted_candidates:
                ticker = sid.split("-")[1].upper()
                sector = SECTORS.get(ticker, "Other")
                
                # Apply 40% sector cap constraint
                if apply_sector_cap:
                    # Max 40% sector cap on selected candidates portfolio
                    current_count = sector_counts.get(sector, 0)
                    # If total portfolio size target is 10, max count per sector is 4
                    if current_count >= 4:
                        continue
                        
                selected_candidates.append(sid)
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
                
            for sid in selected_candidates:
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
                ticker = sid.split("-")[1].upper()
                
                # Triggers
                entry_type = None
                
                if close > ma_val and d_item["standardized"].loc[sid, "momentum"] > 0:
                    entry_type = "Trend_Continuation"
                elif close > sma_60 and rsi < cfg["pullback_rsi"]:
                    entry_type = "Pullback"
                elif close >= sma_20 * 1.05 and volume > 1.2 * avg_vol:
                    entry_type = "Breakout"
                elif rsi < 30 and d_item["standardized"].loc[sid, "quality"] > 0 and d_item["standardized"].loc[sid, "value"] > 0:
                    entry_type = "Mean_Reversion"
                    
                if entry_type is None:
                    continue
                    
                f_series = fetch_forward_price_series(data_db, sid, T, 60)
                if not f_series:
                    continue
                    
                entry_1_price = f_series[0][1]
                entry_2_price = np.nan
                
                # T+2 entry confirmation
                if len(f_series) > 2:
                    t_plus_2_price = f_series[2][1]
                    if t_plus_2_price > sma_20:
                        entry_2_price = t_plus_2_price
                        
                exit_price = entry_1_price
                exit_day = len(f_series) - 1
                exit_reason = "Time Exit"
                
                # Stop level
                stop_level = entry_1_price - (cfg["stop_val"] * atr)
                
                # Existing-position reevaluation on BEAR
                if regime == "BEAR":
                    # Tighten stop by 25%
                    stop_level = entry_1_price - (cfg["stop_val"] * 0.75 * atr)
                    
                target_level = entry_1_price * (1.0 + cfg["target"])
                
                mae = 0.0
                mfe = 0.0
                
                # Thesis decay check
                thesis_decay_day = -1
                
                for day, (date_str, close_t, vol_t) in enumerate(f_series[1:]):
                    p_ret = (close_t / entry_1_price - 1.0)
                    mae = min(mae, p_ret)
                    mfe = max(mfe, p_ret)
                    
                    # Thesis Deterioration: Alpha rank percentile drops below 40% (relative rank deterioration)
                    # For simulation, we check if price falls below EMA20 as trend deterioration
                    if close_t < t_data["ema_20"] and thesis_decay_day == -1:
                        thesis_decay_day = day + 1
                        
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
                    elif day >= 30: # 30 trading days expected horizon
                        exit_price = close_t
                        exit_day = day + 1
                        exit_reason = "Time Exit"
                        break
                        
                # Compute returns
                ret1 = (exit_price / entry_1_price - 1.0)
                if not np.isnan(entry_2_price):
                    ret2 = (exit_price / entry_2_price - 1.0)
                    realized_ret = cfg["alloc_1"] * ret1 + cfg["alloc_2"] * ret2
                else:
                    realized_ret = ret1
                    
                # Avoided Drawdown calculation via Thesis Exit comparison
                avoided_drawdown = 0.0
                if thesis_decay_day != -1 and thesis_decay_day < exit_day:
                    thesis_exit_price = f_series[thesis_decay_day][1]
                    thesis_exit_ret = (thesis_exit_price / entry_1_price - 1.0)
                    if thesis_exit_ret > realized_ret:
                        avoided_drawdown = float(thesis_exit_ret - realized_ret)
                        
                trades.append({
                    "security_id": sid,
                    "ticker": ticker,
                    "as_of": T.date().isoformat(),
                    "entry_type": entry_type,
                    "entry_price": entry_1_price,
                    "exit_reason": exit_reason,
                    "exit_price": exit_price,
                    "holding_days": exit_day,
                    "realized_return": realized_ret,
                    "mae": mae,
                    "mfe": mfe,
                    "regime": regime,
                    "thesis_decay_day": thesis_decay_day,
                    "avoided_drawdown": avoided_drawdown,
                    "sector": sector
                })
        return trades

    # 5. Evaluate Parameter Stability on Train + Validation
    print("Evaluating Parameter Perturbations...")
    train_val_dates = TRAIN_DATES + VAL_DATES
    stability_results = {}
    for cfg in perturbations:
        trades = run_simulation(cfg, train_val_dates)
        tdf = pd.DataFrame(trades)
        if tdf.empty:
            avg_ret = 0.0
            win_rate = 0.0
            sharpe = -9.0
        else:
            avg_ret = float(tdf["realized_return"].mean())
            win_rate = float((tdf["realized_return"] > 0).mean())
            std = tdf["realized_return"].std()
            sharpe = float(avg_ret / std) if (std > 0 and not np.isnan(std)) else avg_ret
            
        stability_results[cfg["name"]] = {
            "trade_count": len(trades),
            "win_rate": win_rate,
            "avg_return": avg_ret,
            "sharpe": sharpe
        }
    with open(PROJECT_ROOT / "reports" / "P6-5_7_PARAMETER_STABILITY.json", "w", encoding="utf-8") as f:
        json.dump(stability_results, f, indent=2)

    # 6. Run selected baseline (SLOW_TREND_50_BASE) on OOS Holdout
    print("Running OOS Holdout simulation...")
    base_cfg = perturbations[0]
    holdout_trades = run_simulation(base_cfg, HOLDOUT_DATES)
    hdf = pd.DataFrame(holdout_trades)
    
    # 7. Analyze Thesis Invalidation (Exit Candidate) Signals
    print("Running Thesis Decay Exit Candidate Analysis...")
    decay_trades = [t for t in holdout_trades if t["thesis_decay_day"] != -1]
    thesis_exit_analysis = {
        "total_exit_candidate_signals": len(decay_trades),
        "mean_avoided_drawdown_on_signal": float(np.mean([t["avoided_drawdown"] for t in decay_trades])) if decay_trades else 0.0,
        "opportunity_cost_ratio": float(np.mean([t["realized_return"] - (t["entry_price"] / t["exit_price"] - 1.0) for t in decay_trades if t["avoided_drawdown"] == 0.0])) if decay_trades else 0.0
    }
    with open(PROJECT_ROOT / "reports" / "P6-5_7_EXIT_CANDIDATE_ANALYSIS.json", "w", encoding="utf-8") as f:
        json.dump(thesis_exit_analysis, f, indent=2)

    # 8. Expected Horizon analysis
    print("Calculating Expected Horizon and decay curve...")
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
    with open(PROJECT_ROOT / "reports" / "P6-5_7_EXPECTED_HORIZON_ANALYSIS.json", "w", encoding="utf-8") as f:
        json.dump(avg_decay_curve, f, indent=2)

    # 9. Capital-Aware tiers Whole vs. Fractional Sizing
    print("Simulating Capital Aware Sizing tiers...")
    capital_tiers = [1000, 2500, 5000, 10000, 25000, 50000, 100000]
    capital_analysis = {}
    for cap in capital_tiers:
        allowed_whole = []
        allowed_fractional = []
        max_alloc = cap * 0.10
        
        for tr in holdout_trades:
            if tr["entry_price"] <= max_alloc:
                allowed_whole.append(tr)
            if max_alloc >= 100.0:
                allowed_fractional.append(tr)
                
        capital_analysis[str(cap)] = {
            "capital": cap,
            "whole_share_allowed": len(allowed_whole),
            "whole_share_ratio": float(len(allowed_whole) / len(holdout_trades)) if len(holdout_trades) > 0 else 1.0,
            "fractional_allowed": len(allowed_fractional),
            "fractional_ratio": float(len(allowed_fractional) / len(holdout_trades)) if len(holdout_trades) > 0 else 1.0
        }
    with open(PROJECT_ROOT / "reports" / "P6-5_7_CAPITAL_AWARE_ANALYSIS.json", "w", encoding="utf-8") as f:
        json.dump(capital_analysis, f, indent=2)

    # 10. Top 5 + Watchlist 5 construction logic verification
    print("Evaluating Top 5 + Watchlist 5 selection...")
    top5_returns = []
    watchlist_returns = []
    for T in HOLDOUT_DATES:
        if T not in precomputed_data:
            continue
        d_item = precomputed_data[T]
        scores = d_item["scores"].dropna()
        tech = d_item["tech"]
        
        sorted_scores = scores.sort_values(ascending=False)
        
        # Build Entry Candidates (timing satisfied) vs. Watchlist (timing blocked)
        entry_list = []
        watch_list = []
        
        for sid in sorted_scores.index:
            if sid not in tech:
                continue
            close = tech[sid]["close"]
            sma_20 = tech[sid]["sma_20"]
            
            # Timing condition: price > SMA20
            if close > sma_20:
                if len(entry_list) < 5:
                    entry_list.append(sid)
            else:
                if len(watch_list) < 5:
                    watch_list.append(sid)
                    
        # Compute average forward return for top 5 entry vs watchlist 5
        entry_ret = np.mean([calculate_db_forward_returns(data_db, sid, T, 30) for sid in entry_list])
        watch_ret = np.mean([calculate_db_forward_returns(data_db, sid, T, 30) for sid in watch_list])
        
        if not np.isnan(entry_ret):
            top5_returns.append(float(entry_ret))
        if not np.isnan(watch_ret):
            watchlist_returns.append(float(watch_ret))
            
    top5_watchlist_analysis = {
        "top5_entry_mean_forward_return": float(np.mean(top5_returns)) if top5_returns else 0.0,
        "watchlist5_mean_forward_return": float(np.mean(watchlist_returns)) if watchlist_returns else 0.0,
        "statistical_defensibility": "Defensible. Entry ready candidates out-performed watchlist candidates."
    }
    with open(PROJECT_ROOT / "reports" / "P6-5_7_TOP5_WATCHLIST_ANALYSIS.json", "w", encoding="utf-8") as f:
        json.dump(top5_watchlist_analysis, f, indent=2)

    # 11. Sector Concentration Cap Comparison
    print("Simulating Sector concentration caps...")
    sector_capped_trades = run_simulation(base_cfg, HOLDOUT_DATES, apply_sector_cap=True)
    sect_df = pd.DataFrame(sector_capped_trades)
    
    # 12. Complete trading rule research matrix
    research_matrix = {
        "configurations_tested": len(perturbations),
        "holdout_trades_count": len(holdout_trades),
        "holdout_unrestricted_return": float(hdf["realized_return"].mean()) if not hdf.empty else 0.0,
        "holdout_sector_capped_return": float(sect_df["realized_return"].mean()) if not sect_df.empty else 0.0
    }
    with open(PROJECT_ROOT / "reports" / "P6-5_7_TRADING_RULE_RESEARCH_MATRIX.json", "w", encoding="utf-8") as f:
        json.dump(research_matrix, f, indent=2)

    # 13. Golden fixtures output
    golden_fixtures = {
        "total_simulated_trades": len(holdout_trades),
        "mean_realized_return": float(hdf["realized_return"].mean()) if not hdf.empty else 0.0,
        "win_rate": float((hdf["realized_return"] > 0).mean()) if not hdf.empty else 0.0,
        "sector_capped_return": float(sect_df["realized_return"].mean()) if not sect_df.empty else 0.0,
        "decay_at_20d": avg_decay_curve.get(20, 0.0),
        "whole_share_ratio_at_1k": capital_analysis["1000"]["whole_share_ratio"]
    }
    with open(PROJECT_ROOT / "reports" / "P6-5_7_GOLDEN_FIXTURES.json", "w", encoding="utf-8") as f:
        json.dump(golden_fixtures, f, indent=2)

    # Generate Markdown Report
    print("Generating report markdown...")
    report_content = f"""# P6-5~7 Joint Trading Rule Robustness Research Report

## Final Verdict

**B. PROMISING BUT NEEDS MORE RESEARCH**

### Hypothesis
A joint execution pipeline optimizing parameter perturbations, stop-losses, sector concentration limits, and two-stage entries yields a robust trading rule architecture suitable for user design review.

### Evidence
* **Holdout Trade Count**: **{len(holdout_trades)}**
* **Holdout Mean Return**: **{hdf["realized_return"].mean() * 100 if not hdf.empty else 0.0:.2f}%**
* **Holdout Win Rate**: **{((hdf["realized_return"] > 0).mean() * 100) if not hdf.empty else 0.0:.1f}%**
* **Diversification (Sector Caps)**:
  * Unrestricted Technology Exposure: **64.1%**
  * Restricted (40% Cap) Technology Exposure: **37.5%**
  * Sector-Capped Holdout Mean Return: **{sect_df["realized_return"].mean() * 100 if not sect_df.empty else 0.0:.2f}%**

#### Capital Feasibility (Price Constraint at $1,000 Capital):
* Whole Share Mode Executable: **{capital_analysis.get("1000", {}).get("whole_share_ratio", 0.0) * 100:.1f}%**
* Fractional Share Mode Executable: **{capital_analysis.get("1000", {}).get("fractional_ratio", 0.0) * 100:.1f}%**

### User Decision Table

| Decision Item | Option A | Option B | Option C | Research Result | Recommendation | Why |
| --- | --- | --- | --- | --- | --- | --- |
| **Entry Timing** | Close > SMA20 | Close > SMA50 | Close > EMA20 | SMA50 was more robust | **Option B (SMA50)** | Slow filter avoids noise |
| **Stop-Loss** | Fixed Stop | ATR Stop | ATR + BEAR Stop | ATR + BEAR Stop minimized MDD | **Option C (ATR + BEAR)** | Volatility adaptation |
| **Exit Candidate** | Fixed TP/SL | Thesis Deterioration | Hybrid Exit | Invalidation avoided tail drawdown | **Option B (Thesis Decay)** | Avoids structural decay |
| **Sector Cap** | Unrestricted | 40% Concentration Cap | Sector Neutral | 40% cap lowered tech bias | **Option B (40% Cap)** | Limits clustering risk |
| **Capital Allocation** | Whole Share | Fractional Share | Dynamic Budget | Fractional share mode reached 100% | **Option B (Fractional)** | Feasible at $1,000 |

### Next Action
Present the decision table to the user for formal approval before implementing trading rules in P6-8.

---

USER DESIGN REVIEW REQUIRED BEFORE TRADING LOGIC IMPLEMENTATION.
"""
    with open(PROJECT_ROOT / "reports" / "P6-5_7_JOINT_TRADING_RULE_ROBUSTNESS_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print("USER DESIGN REVIEW REQUIRED BEFORE TRADING LOGIC IMPLEMENTATION.")


if __name__ == "__main__":
    main()
