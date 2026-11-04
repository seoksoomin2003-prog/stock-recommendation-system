# P6-17 Freshness Policy Review

## 1. Trading-Calendar-Aware Market Freshness
The previously proposed fixed "3 calendar days" rule is officially **REJECTED**. Market data freshness must be evaluated based on the expected U.S. equity trading calendar.

- **`expected_latest_trading_session()`**: The system will dynamically compute the last completed trading day using a US holiday calendar (e.g., `pandas.tseries.holiday.USFederalHolidayCalendar`).
- **Session Lag**: The primary freshness metric is `trading_session_lag`, not calendar days. A Friday close retrieved on a Monday morning will correctly have a `trading_session_lag` of 0 (if pre-market) and is therefore `REAL_CURRENT`.
- **Intraday vs Completed**: If requested during market hours, the system will accept the latest completed daily bar. It will not fabricate an incomplete intraday bar.
- **Implementation Added Limit**: The maximum allowable `trading_session_lag` is set to **1 trading session**. If market data is older than the previous completed trading day, its status becomes `STALE`. This is an `IMPLEMENTATION_ADDED / RESEARCH_REQUIRED` safety limit to protect P6-11B logic.

## 2. Fundamental Data Freshness
- Fundamental data (SEC 10-Q/10-K) is event-driven and updates quarterly/annually.
- Market data freshness and Fundamental data freshness are evaluated **independently**.
- A fundamental dataset is not marked `STALE` simply because it is 3 months old, provided it represents the most recent legally filed financial statement (`filed_at <= runtime`). Future filings are strictly prohibited (Point-in-Time integrity).

## 3. Optional Data Freshness
- Alternative data and news have their own retrieval timestamps.
- If they fail to retrieve current information, they degrade to `UNAVAILABLE`, falling gracefully through the P6-16 optional-data degradation mechanism.

## 4. State Semantics
- `STALE`: Data exists but violates the `trading_session_lag` threshold.
- `UNAVAILABLE`: Provider failed to return data, or returned malformed/empty data.
- `MOCK`: Synthetic test data (strictly prohibited from production).
- **Rule**: `STALE` data for recommendation-critical market features automatically downgrades the candidate's status to `UNAVAILABLE_FOR_RECOMMENDATION` and guarantees quarantine.
