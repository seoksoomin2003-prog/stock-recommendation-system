"""External data access for the terminal (Yahoo, SEC EDGAR, FRED).  All free, public, no keys except the
SEC fair-access identity (``SEC_USER_AGENT``), which is never echoed anywhere.

Each function returns JSON-serialisable data or raises; the cache layer turns failures into
STALE / UNAVAILABLE.  Missing values are ``None`` (never 0).
"""
import csv
from utils import fcntl_port as fcntl
import io
import json
import math
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
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
SEC_REFUSED = (403, 429)         # how SEC answers a caller over its limit (or one it does not accept)
SEC_PAUSE_S = 10 * 60            # SEC lifts a rate block after about ten quiet minutes; asking on only renews it
# One file for every process of this program on the machine.  The limit above used to be kept per process, so the morning scan
# and the screen together could reach 13 requests a second.  The file holds the time of the last request and, after a refusal,
# the time until which nothing is asked.  It holds no identity and no address.
SEC_PACE_FILE = Path(tempfile.gettempdir()) / f"quantengine_sec_pace_{fcntl.uid()}.json"


class SecPaused(RuntimeError):
    pass


def _sec_turn(pace_file: Optional[Path]) -> None:
    """Waits until this request may go.  With a pace file the wait counts every process's requests and a pause set after a refusal
    is honoured; without one (a stand-in ``http`` in tests) or when the file cannot be used, the limit is kept in this process."""
    with _sec_lock:
        if pace_file is not None:
            try:
                with open(pace_file, "a+", encoding="utf-8") as fh:
                    fcntl.flock(fh, fcntl.LOCK_EX)
                    fh.seek(0)
                    try:
                        rec = json.loads(fh.read() or "{}")
                    except ValueError:
                        rec = {}
                    now = time.time()
                    if float(rec.get("paused_until") or 0) > now:
                        raise SecPaused("SEC PAUSED")              # a refusal a moment ago: no request is sent
                    wait = SEC_MIN_INTERVAL - (now - float(rec.get("last") or 0))
                    if 0 < wait <= SEC_MIN_INTERVAL:               # a clock set back would give a long wait: not trusted
                        time.sleep(wait)
                    fh.seek(0)
                    fh.truncate()
                    fh.write(json.dumps({"last": time.time()}))
                    _sec_last[0] = time.time()
                return
            except OSError:
                pass
        wait = SEC_MIN_INTERVAL - (time.time() - _sec_last[0])
        if wait > 0:
            time.sleep(wait)
        _sec_last[0] = time.time()


def _sec_refused(pace_file: Optional[Path]) -> None:
    if pace_file is None:
        return
    try:
        with open(pace_file, "a+", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps({"last": time.time(), "paused_until": time.time() + SEC_PAUSE_S}))
    except OSError:
        pass


def sec_pause_left() -> float:
    """Seconds until SEC is asked again; 0 when no pause is in effect."""
    try:
        return max(0.0, float(json.loads(SEC_PACE_FILE.read_text(encoding="utf-8")).get("paused_until") or 0) - time.time())
    except (OSError, ValueError, TypeError, AttributeError):
        return 0.0


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


def _yf_intraday(symbol: str):
    import yfinance as yf
    t = yf.Ticker(symbol)
    data = t.history(period="1d", interval="1m", prepost=False, auto_adjust=False, actions=False)
    return data, t.get_history_metadata()


def yahoo_intraday(symbol: str, fetch=_yf_intraday) -> Dict[str, Any]:
    """The open (or the last) session's one-minute bars in the exchange's own time: {"rows": [{time, ts, open, high, low, close,
    volume}], "prev_close"}.  Raw traded prices; no adjustment is needed inside one day."""
    import pandas as pd
    data, meta = fetch(symbol)
    rows = []
    if data is not None and not data.empty:
        for ts, r in data.iterrows():
            c = _num(r.get("Close"))
            if c is None or c <= 0:
                continue
            t = pd.Timestamp(ts)
            rows.append({"time": t.strftime("%Y-%m-%d %H:%M"), "ts": int(t.timestamp()), "open": _num(r.get("Open")),
                         "high": _num(r.get("High")), "low": _num(r.get("Low")), "close": c, "volume": _num(r.get("Volume"))})
    meta = meta or {}
    return {"rows": rows, "prev_close": _num(meta.get("chartPreviousClose") if meta.get("chartPreviousClose") is not None else meta.get("previousClose"))}


INFO_FIELDS = ("longName", "shortName", "sector", "industry", "exchange", "currency", "marketCap",
               "trailingPE", "forwardPE", "priceToBook", "dividendYield", "beta", "fiftyTwoWeekHigh",
               "fiftyTwoWeekLow", "sharesOutstanding", "averageVolume", "website", "longBusinessSummary",
               "heldPercentInsiders", "currentPrice", "regularMarketPrice")


# What the same record says about the market's expectations, positioning and dates (kept since 2026-11-22; no score reads them).
# Yahoo is not an official source and these values cannot be checked against one: they are shown and recorded as reference only.
EXPECT_NUMBERS = ("forwardEps", "epsCurrentYear", "trailingEps", "targetMeanPrice", "targetMedianPrice", "targetHighPrice", "targetLowPrice",
                  "numberOfAnalystOpinions", "recommendationMean", "sharesShort", "sharesShortPriorMonth", "shortPercentOfFloat", "shortRatio",
                  "heldPercentInstitutions", "dividendRate", "payoutRatio")
EXPECT_DATES = ("exDividendDate", "dateShortInterest", "earningsTimestampStart")
EXPECT_FIELDS = EXPECT_NUMBERS + EXPECT_DATES + ("recommendationKey",)


def _epoch_day(v) -> Optional[str]:
    """Yahoo gives these dates as seconds since 1970 (UTC midnight for a calendar date)."""
    n = _num(v)
    if n is None or n <= 0:
        return None
    try:
        return datetime.fromtimestamp(n, timezone.utc).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


def yahoo_expectations(info: Dict) -> Dict:
    """The expectation fields of a raw Yahoo record, numbers as numbers and dates as days.  A missing field stays missing."""
    out = {k: _num(info.get(k)) for k in EXPECT_NUMBERS}
    out.update({k: _epoch_day(info.get(k)) for k in EXPECT_DATES})
    key = info.get("recommendationKey")
    out["recommendationKey"] = key if isinstance(key, str) and key and key != "none" else None
    return {k: v for k, v in out.items() if v is not None}


def _yf_info(ticker: str) -> Dict:
    import yfinance as yf
    return yf.Ticker(ticker).info or {}


def yahoo_info(ticker: str, fetch=_yf_info) -> Dict:
    info = fetch(ticker)
    out = {k: info.get(k) for k in INFO_FIELDS if info.get(k) not in (None, "", "Infinity")}
    for k in ("marketCap", "trailingPE", "forwardPE", "priceToBook", "dividendYield", "beta",
              "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "sharesOutstanding", "averageVolume", "currentPrice", "regularMarketPrice"):
        if k in out:
            out[k] = _num(out[k])
    return {**{k: v for k, v in out.items() if v is not None}, **yahoo_expectations(info)}


def yahoo_earnings_dates(ticker: str) -> List[str]:
    """Upcoming earnings dates as Yahoo lists them (estimates until the company confirms); [] when none."""
    import yfinance as yf
    cal = yf.Ticker(ticker).calendar or {}
    return sorted(str(d)[:10] for d in (cal.get("Earnings Date") or []))


# ----------------------------------------------------------------------------- SEC
def sec_user_agent() -> str:
    from utils.runtime_config import sec_configured
    if not sec_configured():
        raise SecNotConfigured("SEC_USER_AGENT not configured")
    return os.getenv("SEC_USER_AGENT", "").strip()


def _sec_get(url: str, http=requests):
    headers = {"User-Agent": sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
    pace = SEC_PACE_FILE if http is requests else None      # only real requests share the machine-wide pace and pause
    _sec_turn(pace)
    r = http.get(url, headers=headers, timeout=30)
    if r.status_code in SEC_REFUSED:
        _sec_refused(pace)
    if r.status_code != 200:
        raise RuntimeError(f"SEC HTTP_{r.status_code}")        # never includes the identity
    return r.json()


def sec_text(url: str, http=requests) -> str:
    """Raw text of an EDGAR document (paced and identified like every SEC request)."""
    headers = {"User-Agent": sec_user_agent(), "Accept-Encoding": "gzip, deflate"}
    pace = SEC_PACE_FILE if http is requests else None
    _sec_turn(pace)
    r = http.get(url, headers=headers, timeout=30)
    if r.status_code in SEC_REFUSED:
        _sec_refused(pace)
    if r.status_code != 200:
        raise RuntimeError(f"SEC HTTP_{r.status_code}")
    return r.text


_ticker_map = []
_ticker_map_at: List[float] = []        # when this process loaded the table itself; empty for a table put there by a caller
_ticker_map_lock = threading.Lock()
TICKER_MAP_SECONDS = 24 * 3600          # the server lives for days: a table loaded at its start never learned a new listing
TICKER_MAP_RETRY_SECONDS = 3600         # after a failed reload the old table stays in use this long before the next try


def sec_cik(ticker: str) -> Optional[str]:
    """CIK via SEC company_tickers.json; loaded once and read again a day later (live when configured, else the cache)."""
    from core.universe_provider import SecTickerMap
    with _ticker_map_lock:
        if not _ticker_map:
            _ticker_map.append(SecTickerMap().load())
            _ticker_map_at[:] = [time.time()]
        elif _ticker_map_at and time.time() - _ticker_map_at[0] > TICKER_MAP_SECONDS:
            try:
                _ticker_map[:] = [SecTickerMap().load()]
                _ticker_map_at[:] = [time.time()]
            except Exception:                           # the table in hand keeps answering
                _ticker_map_at[:] = [time.time() - TICKER_MAP_SECONDS + TICKER_MAP_RETRY_SECONDS]
        table = _ticker_map[0]
    c = table.cik(ticker.upper().replace(".", "-"))
    return str(c).zfill(10) if c else None


def sec_companyfacts(cik: str, http=requests) -> Dict:
    return _sec_get(SEC_FACTS.format(cik=str(cik).zfill(10)), http)


# Companies whose SEC number changed while the business and the ticker carried on.  The new number holds only what was filed under
# it, so a company with no 10-K there yet has no annual figures at all.  Checked against SEC registrant names.
CIK_PREDECESSORS = {"APA": ("6769",), "APO": ("1411494",), "BG": ("1144519",), "BLK": ("1364742",), "FERG": ("1832433",), "MRVL": ("1058057",), "TPL": ("97517",), "XOM": ("34088",)}


def merge_companyfacts(current: Dict, older: Dict) -> Dict:
    """Older filings join the same concept and unit.  Every row keeps its own period and filing date, so nothing is overwritten."""
    facts = {tax: {name: {**c, "units": {u: list(rows) for u, rows in (c.get("units") or {}).items()}} for name, c in concepts.items()} for tax, concepts in (current.get("facts") or {}).items()}
    for tax, concepts in (older.get("facts") or {}).items():
        for name, c in concepts.items():
            slot = facts.setdefault(tax, {}).setdefault(name, {**c, "units": {}})
            for u, rows in (c.get("units") or {}).items():
                slot["units"].setdefault(u, []).extend(rows)
    return {**current, "facts": facts}


def facts_key(ticker: str, cik: str) -> str:
    """A cache name that cannot serve figures saved before the earlier numbers were joined."""
    older = CIK_PREDECESSORS.get(ticker, ())
    return "+".join((str(cik), *older, "2")) if older else str(cik)


def facts_with_predecessors(ticker: str, cik: str, fetch) -> Dict:
    """A failed fetch raises: the cache then keeps what it had instead of saving a thin record as if it were complete."""
    out = fetch(cik)
    for old in CIK_PREDECESSORS.get(ticker, ()):
        out = merge_companyfacts(out, fetch(old))
    return out


def sec_submissions(cik: str, http=requests) -> Dict:
    return _sec_get(SEC_SUBMISSIONS.format(cik=str(cik).zfill(10)), http)


# ----------------------------------------------------------------------------- FRED
def ecos_status() -> str:
    """CONFIGURED | NOT_CONFIGURED (a status word only)."""
    return "CONFIGURED" if os.getenv("ECOS_API_KEY", "").strip() else "NOT_CONFIGURED"


def ecos_series(stat: str, cycle: str, start: str, end: str, items: Sequence[str], http=requests, key: Optional[str] = None) -> List[List]:
    """[[ISO date, value], ...] from the Bank of Korea ECOS API.  The key sits in the URL path, so every failure is raised
    without the URL or the provider's text.  ``cycle``: D or M; ``start`` and ``end`` use that cycle's format."""
    key = key or os.getenv("ECOS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ECOS key not configured")
    url = "/".join(["https://ecos.bok.or.kr/api/StatisticSearch", key, "json", "kr", "1", "5000", stat, cycle, start, end, *items])
    try:
        r = http.get(url, timeout=30)
        body = r.json()
    except Exception:
        raise RuntimeError("ECOS request failed") from None
    rows = (body.get("StatisticSearch") or {}).get("row")
    if rows is None:
        raise RuntimeError("ECOS returned no rows")
    out = []
    for x in rows:
        t = str(x.get("TIME") or "")
        iso = f"{t[:4]}-{t[4:6]}-{t[6:8] or '01'}"
        out.append([iso, _num(x.get("DATA_VALUE"))])
    return out


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
