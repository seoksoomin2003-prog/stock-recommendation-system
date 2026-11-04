"""External data access for the terminal (Yahoo, SEC EDGAR, FRED).  All free, public, no keys except the
SEC fair-access identity (``SEC_USER_AGENT``), which is never echoed anywhere.

Each function returns JSON-serialisable data or raises; the cache layer turns failures into
STALE / UNAVAILABLE.  Missing values are ``None`` (never 0).
"""
import csv
import io
import math
import os
import threading
import time
from typing import Dict, List, Optional

import requests

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SEC_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"
GENERIC_UA = "QuantStockEngine-Terminal/1.0 (local personal research tool)"

_sec_lock = threading.Lock()
_sec_last = [0.0]
SEC_MIN_INTERVAL = 0.15          # < 10 requests/second (SEC fair access)


class SecNotConfigured(RuntimeError):
    pass


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ----------------------------------------------------------------------------- Yahoo
def _yf_download(symbols: List[str], period: str, interval: str = "1d"):
    import yfinance as yf
    return yf.download(list(symbols), period=period, interval=interval, auto_adjust=False, actions=False,
                       progress=False, group_by="column", threads=False)


def yahoo_history(symbols: List[str], period: str = "1y", download=_yf_download) -> Dict[str, List[Dict]]:
    """Daily bars per symbol: date, open, high, low, close, adj_close, volume (split-adjusted by Yahoo)."""
    import pandas as pd
    data = download(symbols, period)
    if data is None or data.empty:
        return {}
    if not isinstance(data.columns, pd.MultiIndex):
        data.columns = pd.MultiIndex.from_product([data.columns, symbols[:1]])
    out = {}
    for s in symbols:
        if ("Close", s) not in data.columns:
            continue
        rows = []
        for ts, r in data.xs(s, axis=1, level=1).iterrows():
            c = _num(r.get("Close"))
            if c is None or c <= 0:
                continue
            rows.append({"date": pd.Timestamp(ts).strftime("%Y-%m-%d"), "open": _num(r.get("Open")),
                         "high": _num(r.get("High")), "low": _num(r.get("Low")), "close": c,
                         "adj_close": _num(r.get("Adj Close")), "volume": _num(r.get("Volume"))})
        if rows:
            out[s] = rows
    return out


INFO_FIELDS = ("longName", "shortName", "sector", "industry", "exchange", "currency", "marketCap",
               "trailingPE", "forwardPE", "priceToBook", "dividendYield", "beta", "fiftyTwoWeekHigh",
               "fiftyTwoWeekLow", "sharesOutstanding", "averageVolume", "website", "longBusinessSummary")


def _yf_info(ticker: str) -> Dict:
    import yfinance as yf
    return yf.Ticker(ticker).info or {}


def yahoo_info(ticker: str, fetch=_yf_info) -> Dict:
    info = fetch(ticker)
    out = {k: info.get(k) for k in INFO_FIELDS if info.get(k) not in (None, "", "Infinity")}
    for k in ("marketCap", "trailingPE", "forwardPE", "priceToBook", "dividendYield", "beta",
              "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "sharesOutstanding", "averageVolume"):
        if k in out:
            out[k] = _num(out[k])
    return {k: v for k, v in out.items() if v is not None}


# ----------------------------------------------------------------------------- SEC
def sec_user_agent() -> str:
    from utils.runtime_config import sec_configured
    if not sec_configured():
        raise SecNotConfigured("SEC_USER_AGENT not configured")
    return os.getenv("SEC_USER_AGENT", "").strip()


def _sec_get(url: str, http=requests):
    headers = {"User-Agent": sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
    with _sec_lock:
        wait = SEC_MIN_INTERVAL - (time.time() - _sec_last[0])
        if wait > 0:
            time.sleep(wait)
        _sec_last[0] = time.time()
    r = http.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"SEC HTTP_{r.status_code}")        # never includes the identity
    return r.json()


_ticker_map = []


def sec_cik(ticker: str) -> Optional[str]:
    """CIK via SEC company_tickers.json; loaded once per process (live when configured, else the cache)."""
    from core.universe_provider import SecTickerMap
    if not _ticker_map:
        _ticker_map.append(SecTickerMap().load())
    c = _ticker_map[0].cik(ticker.upper().replace(".", "-"))
    return str(c).zfill(10) if c else None


def sec_companyfacts(cik: str, http=requests) -> Dict:
    return _sec_get(SEC_FACTS.format(cik=str(cik).zfill(10)), http)


def sec_submissions(cik: str, http=requests) -> Dict:
    return _sec_get(SEC_SUBMISSIONS.format(cik=str(cik).zfill(10)), http)


# ----------------------------------------------------------------------------- FRED
def fred_series(series_id: str, start: str, http=requests) -> List[List]:
    """[[date, value|None], ...] from FRED's public CSV download (no key).  '.' = missing."""
    r = http.get(FRED_CSV, params={"id": series_id, "cosd": start}, headers={"User-Agent": GENERIC_UA},
                 timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"FRED HTTP_{r.status_code}")
    rows = list(csv.reader(io.StringIO(r.text)))
    if not rows or len(rows[0]) < 2 or rows[0][1] != series_id:
        raise ValueError("FRED layout not recognised")
    return [[d, _num(v) if v not in (".", "") else None] for d, v in rows[1:] if d]
