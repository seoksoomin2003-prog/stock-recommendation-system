import pandas as pd
import numpy as np
import json
from datetime import datetime, timezone, timedelta
from core.factor_engine import FactorEngine
from core.decision_engine import DecisionEngine

def generate_deterministic_data():
    np.random.seed(42)
    # 10 Tickers
    tickers = ["T_HIGH_ALPHA", "T_LOW_ALPHA", "T_LIQ_FAIL_400K", "T_LIQ_FAIL_ZERO", "T_LIQ_FAIL_NAN", 
               "T_SECTOR_A", "T_SECTOR_B", "T_SECTOR_C", "T_SECTOR_D", "T_SECTOR_E"]
    
    # 500 days of price data to satisfy momentum lookback
    dates = pd.date_range(end=datetime.now(timezone.utc), periods=500, freq="B")
    
    prices_dict = {}
    volumes_dict = {}
    
    for t in tickers:
        base_price = 100.0
        # Deterministic random walk
        returns = np.random.normal(0.0005, 0.015, len(dates))
        if "HIGH_ALPHA" in t:
            returns = np.random.normal(0.002, 0.01, len(dates)) # Strong momentum, low vol
        elif "LOW_ALPHA" in t:
            returns = np.random.normal(-0.002, 0.03, len(dates)) # Negative momentum, high vol
            
        prices = base_price * np.exp(np.cumsum(returns))
        prices_dict[t] = prices
        
        # Volumes
        if "400K" in t:
            volumes_dict[t] = np.full(len(dates), 400_000.0)
        elif "ZERO" in t:
            volumes_dict[t] = np.full(len(dates), 0.0)
        elif "NAN" in t:
            volumes_dict[t] = np.full(len(dates), np.nan)
        else:
            volumes_dict[t] = np.full(len(dates), 1_000_000.0)
            
    df_prices = pd.DataFrame(prices_dict, index=dates)
    df_volumes = pd.DataFrame(volumes_dict, index=dates)
    
    financials = pd.DataFrame([
        {'ticker': "T_HIGH_ALPHA", 'per': 10, 'pbr': 1.5, 'roe': 0.25, 'profitMargin': 0.20},
        {'ticker': "T_LOW_ALPHA", 'per': 50, 'pbr': 5.0, 'roe': 0.05, 'profitMargin': 0.02},
        {'ticker': "T_LIQ_FAIL_400K", 'per': 15, 'pbr': 2.0, 'roe': 0.15, 'profitMargin': 0.10},
        {'ticker': "T_LIQ_FAIL_ZERO", 'per': 15, 'pbr': 2.0, 'roe': 0.15, 'profitMargin': 0.10},
        {'ticker': "T_LIQ_FAIL_NAN", 'per': 15, 'pbr': 2.0, 'roe': 0.15, 'profitMargin': 0.10},
        {'ticker': "T_SECTOR_A", 'per': 12, 'pbr': 1.8, 'roe': 0.18, 'profitMargin': 0.12},
        {'ticker': "T_SECTOR_B", 'per': 12, 'pbr': 1.8, 'roe': 0.18, 'profitMargin': 0.12},
        {'ticker': "T_SECTOR_C", 'per': 12, 'pbr': 1.8, 'roe': 0.18, 'profitMargin': 0.12},
        {'ticker': "T_SECTOR_D", 'per': 12, 'pbr': 1.8, 'roe': 0.18, 'profitMargin': 0.12},
        {'ticker': "T_SECTOR_E", 'per': 12, 'pbr': 1.8, 'roe': 0.18, 'profitMargin': 0.12},
    ]).set_index('ticker')
    
    sector_map = {
        "T_HIGH_ALPHA": "Technology",
        "T_LOW_ALPHA": "Technology",
        "T_LIQ_FAIL_400K": "Finance",
        "T_LIQ_FAIL_ZERO": "Finance",
        "T_LIQ_FAIL_NAN": "Finance",
        "T_SECTOR_A": "Energy", # Group to test 40% sector cap
        "T_SECTOR_B": "Energy",
        "T_SECTOR_C": "Energy",
        "T_SECTOR_D": "Energy",
        "T_SECTOR_E": "Energy"
    }
    
    return df_prices, df_volumes, financials, sector_map

def run_baseline():
    print("Generating deterministic data...")
    prices, volumes, financials, sector_map = generate_deterministic_data()
    
    fe = FactorEngine()
    print("Calculating factors...")
    factors = fe.get_factor_matrix(prices, financials)
    
    candidates = []
    # Create valid candidate dicts
    for t in prices.columns:
        c = {
            "security_id": t,
            "ticker": t,
            "close": prices[t].iloc[-1],
            "volume": volumes[t].iloc[-1],
            "atr": prices[t].diff().abs().rolling(14).mean().iloc[-1],
            "ema20": prices[t].ewm(span=20).mean().iloc[-1],
            "sector": sector_map[t]
        }
        # Simplified scoring for test (using factor summation)
        raw_alpha = (factors.loc[t, 'momentum'] + factors.loc[t, 'value'] + 
                     factors.loc[t, 'quality'] + factors.loc[t, 'low_volatility'])
        c['alpha'] = raw_alpha if not pd.isna(raw_alpha) else -999.0
        c['confidence'] = 0.9 # High confidence
        candidates.append(c)
        
    de = DecisionEngine()
    
    # Calculate Alpha Percentile prior to DecisionEngine (Simulating ScoringEngine output)
    valid_alphas = [c['alpha'] for c in candidates if not pd.isna(c['alpha'])]
    for c in candidates:
        if not pd.isna(c['alpha']):
            # Percentilerank
            c['alpha_percentile'] = sum(1 for a in valid_alphas if a <= c['alpha']) / len(valid_alphas)
        else:
            c['alpha_percentile'] = 0.0

    print("Running DecisionEngine in BEAR regime...")
    decision = de.evaluate_portfolio(as_of=datetime.now(timezone.utc), capital=1000000.0, market_regime="BEAR", candidates_data=candidates)
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "candidates": {}
    }
    
    # Trace candidates
    for c in candidates:
        status = "ELIGIBLE"
        quarantine = []
        if c['volume'] < 500000 or pd.isna(c['volume']):
            status = "REJECTED_LIQUIDITY"
            quarantine.append("LIQUIDITY")
        elif c['alpha_percentile'] < 0.75:
            status = "REJECTED_BEAR_PERCENTILE"
            quarantine.append("BEAR_75TH")
            
        alloc = 0.0
        for top in decision.top5:
            if top.ticker == c['ticker']:
                status = "TOP5"
                alloc = top.target_notional / decision.capital
                break
                
        report["candidates"][c['ticker']] = {
            "volume": c['volume'],
            "alpha": c['alpha'],
            "alpha_percentile": c['alpha_percentile'],
            "status": status,
            "allocation": alloc
        }
    
    print(json.dumps(report, indent=2))
    
    with open("reports/P6-17_FROZEN_CORE_REGRESSION_BASELINE.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Baseline saved to reports/P6-17_FROZEN_CORE_REGRESSION_BASELINE.json")

if __name__ == "__main__":
    run_baseline()
