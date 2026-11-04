# P6-15 PIT Data Contract Review
The Point-In-Time (PIT) data contract holds strong for Fundamentals and Universe Membership using the SEC's rigorous `filed_at` timestamps. It degrades for Market Data due to reliance on `yfinance` which aggressively auto-adjusts historical prices without providing PIT raw versions easily.
