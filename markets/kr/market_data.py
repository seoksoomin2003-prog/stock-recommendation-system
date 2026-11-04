"""Korean daily OHLCV acquisition and validation (KR-DATA-0.1 §3).

Providers
* ``KRXOpenAPIProvider`` -- official KRX Open API (data-dbg.krx.co.kr/svc/apis/...), keyed by the
  ``AUTH_KEY`` header from ``KRX_API_KEY``.  Supplies official traded value (ACC_TRDVAL), market cap and
  listed shares.  Used whenever the key is configured.  (Verified 2026-11-04: an unkeyed request returns
  ``401 Unauthorized Key``; response field names follow the published service description and are
  re-checked by ``parse_krx_daily`` on the first keyed call -- an unknown layout raises, never guesses.)
* ``YahooKRProvider`` -- supplementary public source (``<code>.KS`` / ``<code>.KQ``).  OHLC and volume are
  split-adjusted by the provider; ``adj_close`` additionally reflects dividends.  Traded value is a
  PROXY = close x volume (``traded_value_basis = PROXY_CLOSE_X_VOLUME``); split adjustment leaves the
  product unchanged, but it is not KRX's official ACC_TRDVAL (intraday prices differ from the close).

Canonical long schema (one row per security-session), see ``CANONICAL_COLUMNS``.  Invalid rows are
*flagged* and their values removed (NaN), never repaired or replaced.
"""
import os
import time
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
import requests

CANONICAL_COLUMNS = ["date", "market", "ticker", "open", "high", "low", "close", "adj_close", "volume",
                     "traded_value", "traded_value_basis", "provider", "retrieved_at", "observation_ts",
                     "adjustment", "quality_status", "quality_flags"]
YAHOO_ADJUSTMENT = "OHLCV split-adjusted by provider; adj_close also dividend-adjusted"
KRX_ADJUSTMENT = "UNADJUSTED (as traded)"


# ----------------------------------------------------------------------------- validation
def validate_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Row-level OHLCV integrity.  Adds quality_flags; invalid rows get quality_status INVALID and
    their numeric values set to NaN (missing), so they can never become an observation."""
    df = df.copy()
    flags = [[] for _ in range(len(df))]
    o, h, l, c = (df[k].astype(float) for k in ("open", "high", "low", "close"))
    v, tv = df["volume"].astype(float), df["traded_value"].astype(float)
    checks = {
        "NON_POSITIVE_PRICE": (o <= 0) | (h <= 0) | (l <= 0) | (c <= 0),
        "HIGH_BELOW_LOW": h < l,
        "OPEN_OUTSIDE_RANGE": (o > h * (1 + 1e-9)) | (o < l * (1 - 1e-9)),
        "CLOSE_OUTSIDE_RANGE": (c > h * (1 + 1e-9)) | (c < l * (1 - 1e-9)),
        "NEGATIVE_VOLUME": v < 0,
        "NEGATIVE_TRADED_VALUE": tv < 0,
        "MISSING_PRICE": o.isna() | h.isna() | l.isna() | c.isna(),
        "MISSING_VOLUME": v.isna(),
    }
    dup = df.duplicated(["ticker", "date"], keep="last")
    checks["DUPLICATE_DATE"] = dup
    for name, mask in checks.items():
        for i in np.flatnonzero(mask.fillna(False).to_numpy()):
            flags[i].append(name)
    df["quality_flags"] = [";".join(f) for f in flags]
    bad = df["quality_flags"] != ""
    df["quality_status"] = np.where(bad, "INVALID", "REAL")
    num = ["open", "high", "low", "close", "adj_close", "volume", "traded_value"]
    df.loc[bad, num] = np.nan
    return df


def series_checks(bars: pd.DataFrame, sessions: pd.DatetimeIndex, latest_session: pd.Timestamp) -> Dict:
    """Security-level checks on validated bars of ONE ticker (sorted by date)."""
    valid = bars[bars["quality_status"] == "REAL"]
    out = {"bars": int(len(bars)), "valid_bars": int(len(valid)), "flags": []}
    if valid.empty:
        out["status"] = "UNAVAILABLE"
        out["flags"].append("NO_VALID_BARS")
        return out
    last = pd.Timestamp(valid["date"].max()).normalize()
    out["last_bar"] = str(last.date())
    window = sessions[sessions >= valid["date"].min()]
    missing = sorted(set(window) - set(pd.to_datetime(valid["date"]).dt.normalize()))
    out["missing_sessions"] = len(missing)
    if missing:
        out["flags"].append("MISSING_SESSIONS")
    if last < latest_session:
        out["flags"].append("STALE")
    tail = valid.sort_values("date")["volume"].tail(3)
    if len(tail) == 3 and (tail == 0).all():
        out["flags"].append("ZERO_VOLUME_RUN_HALT_SUSPECTED")
    if "adj_close" in valid and valid["adj_close"].notna().any():
        ratio = (valid["adj_close"] / valid["close"]).replace([np.inf, -np.inf], np.nan)
        jumps = ratio.pct_change().abs()
        if (jumps > 0.02).any():
            out["flags"].append("CORPORATE_ACTION_SUSPECTED")
            out["corporate_action_dates"] = [str(pd.Timestamp(d).date()) for d in
                                             valid.loc[jumps > 0.02, "date"].tolist()[:5]]
    out["status"] = ("STALE" if "STALE" in out["flags"] else
                     "HALTED" if "ZERO_VOLUME_RUN_HALT_SUSPECTED" in out["flags"] else "REAL")
    return out


# ----------------------------------------------------------------------------- Yahoo
def _yf_download(symbols, start, end):
    import yfinance as yf
    return yf.download(list(symbols), start=start, end=end, interval="1d", auto_adjust=False,
                       actions=False, progress=False, group_by="column", threads=False)


class YahooKRProvider:
    name = "yfinance"

    def __init__(self, download: Callable = _yf_download, chunk: int = 50, pause: float = 1.0,
                 attempts: int = 3, sleep=time.sleep):
        self.download, self.chunk, self.pause, self.attempts, self.sleep = download, chunk, pause, attempts, sleep
        self.events: List[Dict] = []

    def fetch(self, securities: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
        """``securities`` needs columns canonical_ticker, market, yahoo_symbol.  Returns canonical rows."""
        retrieved = datetime.now(timezone.utc).isoformat()
        sym2 = {r.yahoo_symbol: (r.canonical_ticker, r.market) for r in securities.itertuples()}
        symbols = list(sym2)
        frames = []
        for i in range(0, len(symbols), self.chunk):
            part = symbols[i:i + self.chunk]
            data, err = None, None
            for a in range(self.attempts):
                try:
                    data = self.download(part, start, end)
                    break
                except Exception as exc:
                    err = type(exc).__name__
                    self.sleep(self.pause * (a + 2))
            if data is None or data.empty:
                self.events.append({"kind": "chunk_failed", "symbols": len(part), "error": err})
                continue
            frames.append(self._to_long(data, part, sym2, retrieved))
            self.sleep(self.pause)
        if not frames:
            return pd.DataFrame(columns=CANONICAL_COLUMNS)
        return validate_rows(pd.concat(frames, ignore_index=True))

    @staticmethod
    def _to_long(data: pd.DataFrame, part, sym2, retrieved) -> pd.DataFrame:
        if not isinstance(data.columns, pd.MultiIndex):        # single symbol
            data.columns = pd.MultiIndex.from_product([data.columns, part[:1]])
        rows = []
        for sym in part:
            if ("Close", sym) not in data.columns:
                continue
            sub = pd.DataFrame({k.lower().replace(" ", "_"): data[(k, sym)]
                                for k in ("Open", "High", "Low", "Close", "Adj Close", "Volume")
                                if (k, sym) in data.columns})
            sub = sub.dropna(how="all")
            if sub.empty:
                continue
            code, market = sym2[sym]
            sub["date"] = pd.to_datetime(sub.index).tz_localize(None).normalize()
            sub["market"], sub["ticker"] = market, code
            sub["traded_value"] = sub["close"] * sub["volume"]
            sub["traded_value_basis"] = "PROXY_CLOSE_X_VOLUME"
            sub["provider"], sub["retrieved_at"] = "yfinance", retrieved
            sub["observation_ts"] = sub["date"].dt.strftime("%Y-%m-%dT15:30:00+09:00")
            sub["adjustment"] = YAHOO_ADJUSTMENT
            rows.append(sub.reset_index(drop=True))
        if not rows:
            return pd.DataFrame(columns=CANONICAL_COLUMNS)
        out = pd.concat(rows, ignore_index=True)
        for col in CANONICAL_COLUMNS:
            if col not in out:
                out[col] = np.nan
        return out[CANONICAL_COLUMNS[:-2] + ["quality_status", "quality_flags"]]

    def fetch_index(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        data = self.download([symbol], start, end)
        if data is None or data.empty:
            return pd.DataFrame()
        if isinstance(data.columns, pd.MultiIndex):
            data = data.xs(symbol, axis=1, level=1)
        data.index = pd.to_datetime(data.index).tz_localize(None).normalize()
        return data[["Open", "High", "Low", "Close"]].dropna(how="all")


# ----------------------------------------------------------------------------- KRX Open API
KRX_BASE = "https://data-dbg.krx.co.kr/svc/apis"
KRX_DAILY = {"KOSPI": "sto/stk_bydd_trd", "KOSDAQ": "sto/ksq_bydd_trd"}
KRX_FIELDS = {"BAS_DD": "date", "ISU_CD": "ticker", "ISU_NM": "name", "TDD_OPNPRC": "open", "TDD_HGPRC": "high",
              "TDD_LWPRC": "low", "TDD_CLSPRC": "close", "ACC_TRDVOL": "volume", "ACC_TRDVAL": "traded_value",
              "MKTCAP": "market_cap", "LIST_SHRS": "listed_shares"}


def _num(s):
    try:
        s = str(s).replace(",", "").strip()
        return float(s) if s not in ("", "-") else np.nan
    except Exception:
        return np.nan


def parse_krx_daily(payload: Dict, market: str, retrieved: str) -> pd.DataFrame:
    rows = payload.get("OutBlock_1")
    if rows is None:
        raise ValueError(f"KRX response layout not recognised (keys: {sorted(payload)[:5]})")
    if rows and not set(KRX_FIELDS) <= set(rows[0]):
        raise ValueError(f"KRX fields missing: {sorted(set(KRX_FIELDS) - set(rows[0]))}")
    out = pd.DataFrame([{KRX_FIELDS[k]: r.get(k) for k in KRX_FIELDS} for r in rows])
    if out.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)
    for k in ("open", "high", "low", "close", "volume", "traded_value", "market_cap", "listed_shares"):
        out[k] = out[k].map(_num)
    out["date"] = pd.to_datetime(out["date"], format="%Y%m%d")
    out["market"], out["adj_close"] = market, np.nan
    out["traded_value_basis"], out["provider"], out["retrieved_at"] = "KRX_ACC_TRDVAL", "krx_openapi", retrieved
    out["observation_ts"] = out["date"].dt.strftime("%Y-%m-%dT15:30:00+09:00")
    out["adjustment"] = KRX_ADJUSTMENT
    return out


class KRXOpenAPIProvider:
    name = "krx_openapi"

    def __init__(self, api_key: Optional[str] = None, http=None, pause: float = 0.5, sleep=time.sleep):
        self.api_key = api_key if api_key is not None else os.getenv("KRX_API_KEY", "")
        self.http, self.pause, self.sleep = http or requests, pause, sleep

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def daily(self, market: str, day: str) -> pd.DataFrame:
        if not self.configured:
            raise RuntimeError("KRX_API_KEY not configured")
        r = self.http.get(f"{KRX_BASE}/{KRX_DAILY[market]}", params={"basDd": day},
                          headers={"AUTH_KEY": self.api_key}, timeout=30)
        self.sleep(self.pause)
        if r.status_code != 200:
            raise RuntimeError(f"KRX HTTP_{r.status_code}")      # never echoes the key
        return validate_rows(parse_krx_daily(r.json(), market, datetime.now(timezone.utc).isoformat()))


def select_provider(env=os.environ):
    """KRX Open API when a key is configured, else the supplementary Yahoo provider."""
    if env.get("KRX_API_KEY"):
        return {"provider": "krx_openapi", "basis": "KRX_ACC_TRDVAL", "status": "OFFICIAL"}
    return {"provider": "yfinance", "basis": "PROXY_CLOSE_X_VOLUME", "status": "SUPPLEMENTARY",
            "reason": "KRX_API_KEY not configured"}
