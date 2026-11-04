# P6-15 Corporate Action Test
yfinance correctly identifies the existence of stock splits (e.g., NVDA on 2024-06-10), but returns historically adjusted close prices by default, stripping the original raw values without careful parameter tuning.
