# P6-13 LIVE RECOMMENDATION FORENSIC

## 1. Zero Candidates Root Cause Analysis
The previous execution outputted `Factor coverage = 0.0%`, `Variance = nan`, and ultimately `Liquidity Filter: 7 -> 0 tickers`. 
**Root Cause Chain**:
1. `DataLoader._download_yf` encountered a `YFDataException` (e.g., rate limit, timeout, or parsing error).
2. The `try/except` block caught the exception and returned a fallback `pd.DataFrame()`.
3. `get_volume_data` received the empty DataFrame and returned a dummy DataFrame of all zeros (`pd.DataFrame(0, ...)`).
4. `get_price_data` may have received partial cached data or NaNs.
5. In `main.py`, the NaN Firewall evaluated `has_volume = not (raw_volumes[t] == 0).all()`. This condition failed for all 7 tickers (since all values were 0), blocking them from entering the calculation. However, if the condition evaluated to True due to an edge case (like `get_price_data` partially succeeding), it entered the `FactorEngine`.
6. Inside `FactorEngine`, `calculate_momentum` requires 13 months of historical data due to `prices.resample('ME').last().pct_change(12)`. Since `MAX_LOCAL_LOOKBACK_DAYS` is set to 365, it lacks the required 13-month depth. Thus, `Momentum` resulted in `NaN` (0.0% coverage).
7. More critically, the 0s in `raw_volumes` were passed down the pipeline. `ExecutionEngine.filter_by_liquidity` calculated the 20-day Average Daily Volume (`adv_20d`) as `0`.
8. The filter condition `volume > 500,000` failed (0 > 500,000 is False), thereby dropping all 7 tickers.
9. Portfolio Optimizer received 0 candidates -> `Assets = 0`.

## 2. Live Universe Source
The live universe evaluates exactly 7 tickers: `["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]`.
**Source**: This is a deliberately hardcoded smoke-test list located in `main.py` at line 576 within the `if __name__ == '__main__':` execution block. It is not a configuration limitation but a local development default.

## 3. Data Flow Integrity
- **NaN Propagation**: If a single factor is NaN (e.g., Momentum), `ScoringEngine` redistributes weights among the valid factors (Value, Quality, Low-Vol). While resilient, it alters the strategy's expected multi-factor risk profile.
- **Liquidity Filter**: Accurately performs its safety function. A fallback volume of 0 correctly halts execution instead of recommending an untradable asset.
