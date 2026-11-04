import json
import time
import argparse
import sys
from pathlib import Path

# Permit ``python scripts/...`` from any current working directory without a
# machine-specific path or an externally configured PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np
from datetime import datetime, timezone
from core.universe_provider import WikipediaSP500BootstrapProvider
from data.loader import DataLoader
from core.factor_engine import FactorEngine
from core.decision_engine import DecisionEngine
from core.scoring_engine import ScoringEngine
from utils.logger import setup_logger
from utils import config as runtime_config
from main import QuantTradingSystemV2

logger = setup_logger("P6_17_5_Validator")

def _legacy_noncanonical_validation():
    start_time = time.time()
    report = {}
    
    # 1. Universe Acquisition
    logger.info("Acquiring Live Universe...")
    u_start = time.time()
    up = WikipediaSP500BootstrapProvider()
    universe = up.get_live_universe()
    u_time = time.time() - u_start
    
    raw_tickers = universe.get("tickers", [])
    ciks = universe.get("ciks", {})
    
    report["universe"] = {
        "status": universe["status"],
        "source": universe.get("source", "UNKNOWN"),
        "retrieved_at": universe.get("retrieved_at", ""),
        "raw_universe_count": len(raw_tickers),
        "normalized_universe_count": len(set(raw_tickers)),
        "duplicate_count": len(raw_tickers) - len(set(raw_tickers)),
        "security_master_match_count": len(ciks),
        "acquisition_time_sec": u_time
    }
    
    if len(raw_tickers) < 450:
        logger.error("Universe acquisition failed or too small. Aborting full run.")
        report["pipeline_status"] = "LIVE DATA UNAVAILABLE"
        report["recommendation_status"] = "DATA-INCOMPLETE / NO VALID RECOMMENDATION"
        report["verdict"] = "LIVE_DATA_UNAVAILABLE"
        return report

    # 2. Market Data Acquisition
    logger.info("Acquiring Market Data in Chunks...")
    dl = DataLoader()
    end_date = pd.Timestamp.now().strftime('%Y-%m-%d')
    start_date = (pd.Timestamp.now() - pd.DateOffset(years=2)).strftime('%Y-%m-%d')
    
    m_start = time.time()
    
    # Process in chunks of 100 to prevent yfinance hangs and provide logging
    chunk_size = 100
    prices_list = []
    volumes_list = []
    financials_list = []
    
    for i in range(0, len(raw_tickers), chunk_size):
        chunk = raw_tickers[i:i+chunk_size]
        logger.info(f"Processing chunk {i//chunk_size + 1}/{(len(raw_tickers)//chunk_size) + 1} ({len(chunk)} tickers)...")
        
        # Prices & Volumes
        try:
            p = dl.get_price_data(chunk, start_date, end_date)
            v = dl.get_volume_data(chunk, start_date, end_date)
            prices_list.append(p)
            volumes_list.append(v)
        except Exception as e:
            logger.error(f"Error fetching market data for chunk: {e}")
            
        # SEC Financials
        try:
            f = dl.get_financial_data(chunk, ciks={k: v for k, v in ciks.items() if k in chunk})
            financials_list.append(f)
        except Exception as e:
            logger.error(f"Error fetching SEC data for chunk: {e}")
            
    m_time = time.time() - m_start
    
    raw_prices = pd.concat(prices_list, axis=1) if prices_list else pd.DataFrame()
    raw_volumes = pd.concat(volumes_list, axis=1) if volumes_list else pd.DataFrame()
    
    # Check for duplicate columns from concat
    raw_prices = raw_prices.loc[:, ~raw_prices.columns.duplicated()]
    raw_volumes = raw_volumes.loc[:, ~raw_volumes.columns.duplicated()]
    
    f_time = 0
    financials = pd.concat(financials_list) if financials_list else pd.DataFrame()
    financials = financials[~financials.index.duplicated(keep='first')]

    success_price = raw_prices.dropna(axis=1, how='all').shape[1] if not raw_prices.empty else 0
    success_vol = raw_volumes.dropna(axis=1, how='all').shape[1] if not raw_volumes.empty else 0
    
    report["market_data"] = {
        "successful_price_downloads": success_price,
        "successful_volume_downloads": success_vol,
        "acquisition_time_sec": m_time,
        "missing_columns": len(raw_tickers) - success_price
    }
    
    # 3. Factor & Fundamental Coverage
    logger.info("Calculating Factors & Extracting Fundamentals...")
    fe = FactorEngine()
    factor_start = time.time()
    factors = fe.get_factor_matrix(raw_prices, financials)
    factor_time = time.time() - factor_start
    
    # Funnel Counters
    funnel = {
        "sp500_universe": len(raw_tickers),
        "security_master_matched": len(ciks),
        "market_data_available": success_price,
        "fresh_market_data": 0,
        "volume_valid": 0,
        "above_500k_liquidity_pass": 0,
        "below_500k": 0,
        "zero_volume": 0,
        "nan_volume": 0,
        "factor_eligible": 0,
        "fundamental_real": 0,
        "fundamental_partial": 0,
        "fundamental_unavailable": 0,
        "fundamental_mock": 0,
        "final_real_candidates": 0
    }
    
    candidates = []
    
    for t in raw_tickers:
        if t not in raw_prices.columns or raw_prices[t].isna().all():
            continue
            
        funnel["fresh_market_data"] += 1
        
        vol = raw_volumes[t].iloc[-1] if t in raw_volumes.columns and not raw_volumes[t].isna().all() else np.nan
        if pd.isna(vol):
            funnel["nan_volume"] += 1
        elif vol == 0:
            funnel["zero_volume"] += 1
        elif vol < 500000:
            funnel["below_500k"] += 1
            funnel["volume_valid"] += 1
        else:
            funnel["above_500k_liquidity_pass"] += 1
            funnel["volume_valid"] += 1
            
        if t in financials.index:
            per = financials.loc[t, 'per']
            roe = financials.loc[t, 'roe']
            if not pd.isna(per) and not pd.isna(roe):
                funnel["fundamental_real"] += 1
            elif not pd.isna(per) or not pd.isna(roe):
                funnel["fundamental_partial"] += 1
            else:
                funnel["fundamental_unavailable"] += 1
        else:
            funnel["fundamental_unavailable"] += 1
            
        c = {
            "security_id": t,
            "ticker": t,
            "close": raw_prices[t].iloc[-1],
            "volume": vol,
            "atr": raw_prices[t].diff().abs().rolling(14).mean().iloc[-1],
            "ema20": raw_prices[t].ewm(span=20).mean().iloc[-1]
        }
        
        # Factor check
        raw_alpha = (factors.loc[t, 'momentum'] + factors.loc[t, 'value'] + 
                     factors.loc[t, 'quality'] + factors.loc[t, 'low_volatility']) if t in factors.index else np.nan
                     
        if not pd.isna(raw_alpha):
            funnel["factor_eligible"] += 1
            c["alpha"] = raw_alpha
            c["alpha_percentile"] = 1.0 # Will be recalculated by DecisionEngine
            
        candidates.append(c)

    report["funnel"] = funnel
    report["factor_coverage"] = {
        "valid_count": funnel["factor_eligible"],
        "unavailable_count": len(raw_tickers) - funnel["factor_eligible"],
        "calculation_time_sec": factor_time
    }
    
    # 4. Decision Engine (FROZEN CORE)
    logger.info("Executing DecisionEngine...")
    de = DecisionEngine()
    
    # We must calculate alpha_percentile first since we bypassed ScoringEngine in this mock funnel setup
    se = ScoringEngine()
    scored = se.calculate(factors)
    scored_percentile = scored.rank(pct=True)
    
    for c in candidates:
        if c['ticker'] in scored.index:
            c['alpha'] = scored.loc[c['ticker']]
            c['alpha_percentile'] = scored_percentile.loc[c['ticker']]
            
    decision_start = time.time()
    # Market Regime is dynamically evaluated in production, let's assume NEUTRAL for standard test
    port_decision = de.evaluate_portfolio(
        as_of=datetime.now(timezone.utc),
        capital=10000.0,
        market_regime="NEUTRAL",
        candidates_data=candidates
    )
    decision_time = time.time() - decision_start
    
    top5_tickers = [x.ticker for x in port_decision.top5]
    wl5_tickers = [x.ticker for x in port_decision.watchlist5]
    
    # Count final real candidates
    final_real = len([c for c in candidates if c.get('data_quality_status') == 'REAL' and 'LIQUIDITY_REJECTED' not in c.get('constraint_flags', [])])
    funnel["final_real_candidates"] = final_real
    
    report["recommendation"] = {
        "final_real_candidates": final_real,
        "TOP5": top5_tickers,
        "WATCHLIST": wl5_tickers,
        "pipeline_status": "SUCCESS" if funnel["fresh_market_data"] > 400 else "PARTIAL",
        "recommendation_status": port_decision.data_quality
    }
    
    report["performance"] = {
        "total_runtime_sec": time.time() - start_time,
        "universe_acquisition_sec": u_time,
        "market_data_acquisition_sec": m_time,
        "sec_acquisition_sec": f_time,
        "factor_calculation_sec": factor_time,
        "portfolio_construction_sec": decision_time
    }
    
    verdict = "REAL_RECOMMENDATION_READY" if "REAL RECOMMENDATION" in port_decision.data_quality else "DATA_INCOMPLETE"
    report["verdict"] = verdict
    
    return report


def run_live_validation(sample_size: int | None = None):
    """Run P6-17.5 only through the canonical production decision route.

    ``sample_size`` is for bounded provider preflight only; it never claims to
    be full-universe validation.  Omit it only for an explicitly authorised
    full P6-17.5 run in an appropriate production workload configuration.
    """
    if sample_size is None and runtime_config.APP_MODE != "production":
        return {
            "validation_scope": "full",
            "pipeline_status": "CONFIGURATION_BLOCKED",
            "recommendation_status": "DATA-INCOMPLETE / NO VALID RECOMMENDATION",
            "verdict": "FULL_VALIDATION_REQUIRES_APP_MODE_PRODUCTION",
            "reason": "Set APP_MODE=production explicitly; local workload limits are intentionally retained.",
        }
    started = time.time()
    universe = WikipediaSP500BootstrapProvider().get_live_universe()
    if universe.get("status") not in {"SUCCESS", "SUCCESS_FROM_CACHE"} or universe.get("freshness_status") != "REAL":
        return {
            "pipeline_status": "UNIVERSE_UNAVAILABLE",
            "recommendation_status": "DATA-INCOMPLETE / NO VALID RECOMMENDATION",
            "verdict": "LIVE_DATA_UNAVAILABLE",
            "universe": universe,
            "validation_scope": "bounded" if sample_size else "full",
        }

    tickers = universe["tickers"]
    if sample_size is not None:
        tickers = tickers[:sample_size]
    result = QuantTradingSystemV2(mode="live", run_research=False).run_live_cycle(
        tickers, ciks=universe.get("ciks", {})
    )
    return {
        "validation_scope": "bounded" if sample_size is not None else "full",
        "requested_tickers": len(tickers),
        "universe": {
            "status": universe["status"], "freshness_status": universe.get("freshness_status"),
            "source": universe.get("source"), "retrieved_at": universe.get("retrieved_at"),
        },
        "pipeline_status": result.get("pipeline_status", result.get("status")),
        "recommendation_status": result.get("recommendation_status"),
        "model_version": result.get("model_version"),
        "eligible_candidates_count": result.get("eligible_candidates_count", 0),
        "final_tradable_candidates_count": result.get("final_tradable_candidates_count", 0),
        "quarantined_candidates": result.get("quarantined_candidates", []),
        "diagnostics": result.get("diagnostics", {}),
        "elapsed_seconds": time.time() - started,
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Canonical P6-17.5 live validation")
    parser.add_argument("--sample-size", type=int, default=None,
                        help="bounded provider preflight only; omit only for a full authorised run")
    args = parser.parse_args()
    rep = run_live_validation(sample_size=args.sample_size)
    with open("reports/P6-17.5_CANDIDATE_FUNNEL.json", "w") as f:
        json.dump(rep, f, indent=2, default=str)
    print("Validation finished. Writing markdown report...")
    with open("reports/P6-17.5_FINAL_VERDICT.md", "w") as f:
        f.write("# P6-17.5 Canonical Validation Result\n\n")
        for key, value in rep.items():
            f.write(f"## {key}\n\n{value}\n\n")
