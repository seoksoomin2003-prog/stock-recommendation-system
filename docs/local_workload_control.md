# Local Workload Control Design & Verification

This document specifies the design, pipeline execution flow, and testing outcomes of the Local Workload Control phase.

## 1. System Limits Configuration
Workload controls are centralized in `utils/config.py`:
- `MAX_LOCAL_TICKERS = 3` (Maximum allowed canonical deduplicated tickers in Local Mode)
- `MAX_LOCAL_LOOKBACK_DAYS = 365` (Maximum lookback window for historical market data in Local Mode)

---

## 2. Validation Pipeline Flow
To ensure that no data downloads or API harvests commence for unauthorized workloads, input validation is enforced immediately after Entity Resolution and before any network operations:

```
User Input (NL/List)
       ↓
Input Parsing / Tokenization
       ↓
Entity Resolution (Fuzzy / Database lookup)
       ↓
Canonical Tickers Extraction (e.g. "구글" -> GOOGL)
       ↓
Duplicate Removal (Case-insensitive deduplication)
       ↓
Local Mode Workload Limit Validation (Count > 3 check)
       ↓
If Exceeded: Abort & return LIMIT_EXCEEDED status payload (No fetch starts)
If Allowed: Execute Data Harvesting & Scored Pipeline
```

---

## 3. Implementation Details

### Entry-Point Rejections
Rejections are handled in both standard and research entry-points:
- **Scored Pipeline** (`run_research_pipeline` in [alpha_engine/system.py](file:///Users/soominseok/Desktop/퀀트 예측 프로그램/alpha_engine/system.py))
- **Live Cycle Orchestrator** (`run_live_cycle` in [main.py](file:///Users/soominseok/Desktop/퀀트 예측 프로그램/main.py))

If the validation fails, execution aborts and returns:
```python
{
    "status": "LIMIT_EXCEEDED",
    "mode": "local",
    "max_tickers": 3,
    "received": len(canonical_tickers),
    "rejected": rejected,
    "allowed": allowed,
    "executable": False,
    "message": "Local Mode supports up to 3 tickers. Rejected: ... Production Mode has no limits."
}
```

### Date Clipping
To guarantee lookback protection, we enforce date offsets at two levels:
1. **Orchestrator level** (`main.py`): Sets the `start_date` argument to `now - 365 days` if running locally (compared to 4 years in production).
2. **Provider level fail-safe** (`data/loader.py`): If the caller requests a start date older than 365 days while `APP_MODE == "local"`, the `start` parameter is clipped to `now - 365 days` before yfinance download.

---

## 4. Production Mode Immutability
Production mode remains entirely unaffected:
- No ticker limits.
- No lookback window clipping (uses the original 4-year default configured range).
- All indicators and calculations operate on full historical datasets.

---

## 5. Verification Outcomes
All tests are implemented in `tests/test_local_workload_control.py` and run fully mocked (no live network requests).

- **TEST 1 — LOCAL / 1 TICKER** (`AAPL`): `[PASS]` (Runs successfully, lookback <= 365 days).
- **TEST 2 — LOCAL / 3 TICKERS** (`AAPL, MSFT, GOOGL`): `[PASS]` (Runs successfully, lookback <= 365 days).
- **TEST 3 — LOCAL / 4 TICKERS** (`AAPL, MSFT, GOOGL, TSLA`): `[PASS]` (Rejects with `LIMIT_EXCEEDED`, asserts no yfinance download calls started).
- **TEST 4 — LOCAL DUPLICATES** (`GOOGLE, google, googl, Alphabet`): `[PASS]` (Deduplicates to single canonical ticker `GOOGL`, runs successfully).
- **TEST 5 — LOCAL NATURAL LANGUAGE** (`"구글이랑 애플 분석해줘"`): `[PASS]` (Resolves to `GOOGL, AAPL`, runs under the limit).
- **TEST 6 — PRODUCTION / MANY TICKERS**: `[PASS]` (Allows 10 tickers without limit).
- **TEST 7 — PRODUCTION LOOKBACK**: `[PASS]` (Verify lookback is not clipped and preserves 4-year duration).
