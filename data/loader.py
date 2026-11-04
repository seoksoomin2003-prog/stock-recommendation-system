"""Canonical live data acquisition (yfinance market data + SEC EDGAR / yfinance fundamentals).

P6-18 repairs (data acquisition only; no factor/scoring/decision math lives here):

* Market data is downloaded ONCE per (tickers, window) in bounded chunks with a
  bounded retry, and memoised so ``get_price_data`` and ``get_volume_data`` no
  longer download the full universe twice.
* Fundamentals are fetched with bounded concurrency, explicit provider pacing
  (SEC < 10 req/s, Yahoo conservative), bounded retries, and a short-lived
  on-disk cache of *extracted genuine observations* (never synthetic values).
* SEC CompanyFacts selection is period-aligned: annual (FY, 10-K family,
  ~1-year duration) net income / revenue for the same fiscal period, equity at
  that period end.  The previous "latest ``filed``" selection could pick a
  prior-year comparative or a single quarter because a 10-K files several
  periods on the same date.
* ``None``/non-finite provider values become NaN (missing), while a genuine
  provider ``0`` is preserved as 0.
* Security metadata (sector, quote type, name) is returned with provenance in
  ``attrs["security_meta"]``.

Status semantics are unchanged: per-ticker ``provider_status`` is REAL /
PARTIAL / UNAVAILABLE for fundamentals and REAL / STALE / UNAVAILABLE for
market data.  Nothing in this module fabricates an observation.
"""
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from utils import config as cfg
from utils.config import NEWS_API_KEY
from utils import runtime_config
from utils.logger import setup_logger
from utils.market_calendar import get_trading_session_lag

logger = setup_logger("DataLoader")

FUNDAMENTAL_FIELDS = ("per", "pbr", "roe", "profitMargin")
SEC_NET_INCOME = ("NetIncomeLoss",)
SEC_REVENUE = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
               "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax",
               # P6-19: lessors/REITs and banks report total revenue under these concepts.  Without them
               # the ASC 606 line (often a small non-lease slice for a REIT) was used as "revenue".
               "OperatingLeaseLeaseIncome", "RealEstateRevenueNet", "RevenuesNetOfInterestExpense")
# P6-19 provider-consistency rule: a Yahoo priceToBook more than this factor away from the
# same company's marketCap / SEC equity is a unit/share-class artifact (e.g. BRK-B priced
# against Class-A book value).  It is rejected (left missing), never replaced.
PBR_CONSISTENCY_FACTOR = 10.0
FUNDAMENTALS_CACHE_SCHEMA = 4
# Version of docs/DATA_INPUT_SPECIFICATION.md implemented by this loader (recorded in run manifests, P6-20).
DATA_INPUT_SPEC_VERSION = "P6-19-final"
SEC_EQUITY = ("StockholdersEquity",)
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "20-F", "40-F"}
INFO_FIELDS = ("trailingPE", "priceToBook", "returnOnEquity", "profitMargins", "sector",
               "industry", "quoteType", "longName", "shortName", "currency", "averageVolume",
               "marketCap", "exchange")


class RateLimiter:
    """Thread-safe minimum-interval limiter (never bursts above ``rate``/s)."""

    def __init__(self, rate_per_second: float):
        self.interval = 1.0 / rate_per_second
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            delay = self._next - now
            self._next = max(now, self._next) + self.interval
        if delay > 0:
            time.sleep(delay)


def _finite_or_nan(value) -> float:
    """Missing / non-numeric / non-finite -> NaN; a genuine 0 stays 0."""
    if value is None or isinstance(value, bool):
        return np.nan
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan
    return number if math.isfinite(number) else np.nan


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DataLoader:
    def __init__(self, cache_dir: Optional[str] = None, use_cache: bool = True):
        self.news_api_key = NEWS_API_KEY
        self.newsapi = None
        if self.news_api_key:
            try:
                from newsapi import NewsApiClient
                self.newsapi = NewsApiClient(api_key=self.news_api_key)
            except Exception:
                self.newsapi = None
        self.cache_dir = cache_dir or cfg.PROVIDER_CACHE_DIR
        self.use_cache = use_cache
        self._market_memo: Dict[Tuple, pd.DataFrame] = {}
        self._sec_limiter = RateLimiter(cfg.SEC_MAX_REQUESTS_PER_SECOND)
        self._yf_limiter = RateLimiter(cfg.YF_INFO_MAX_REQUESTS_PER_SECOND)
        self._events_lock = threading.Lock()
        self.provider_events: List[Dict[str, Any]] = []
        self.request_counts = {"yfinance_download": 0, "yfinance_info": 0, "sec_companyfacts": 0,
                               "fundamental_cache_hits": 0}

    # ------------------------------------------------------------------ utils
    def _event(self, provider: str, kind: str, **details):
        with self._events_lock:
            self.provider_events.append({"provider": provider, "event": kind,
                                         "at": _utc_now().isoformat(), **details})

    def _count(self, key: str):
        with self._events_lock:
            self.request_counts[key] = self.request_counts.get(key, 0) + 1

    # ----------------------------------------------------------- market data
    def _enforce_lookback_and_freshness(self, data: pd.DataFrame, tickers: List[str], required_days: int = 425) -> pd.DataFrame:
        """
        Enforces lookback while preserving provider state in ``DataFrame.attrs``.
        Stale bars are deliberately left intact for diagnostics; the production
        decision boundary quarantines them rather than erasing their identity.
        """
        if data.empty:
            return pd.DataFrame()

        current_utc = _utc_now()
        valid_data = data.copy()
        statuses = dict(data.attrs.get("provider_status", {}))
        last_bars = {}

        for t in tickers:
            if t not in valid_data.columns:
                continue

            series = valid_data[t].dropna()
            if len(series) == 0:
                statuses[t] = "UNAVAILABLE"
                continue

            # 1. Freshness Check
            last_timestamp = pd.Timestamp(series.index[-1])
            last_bars[t] = str(last_timestamp.date())
            lag = get_trading_session_lag(last_timestamp, current_utc)
            if lag > 1:
                logger.warning(f"[{t}] Market data is STALE. Lag: {lag} trading sessions. Last bar: {last_timestamp.date()}")
                statuses[t] = "STALE"
                continue

            # 2. Lookback Check
            if len(series) < 14:  # Absolute minimum trading days check just to be safe
                logger.warning(f"[{t}] Insufficient history ({len(series)} bars). Marked UNAVAILABLE.")
                valid_data[t] = np.nan
                statuses[t] = "UNAVAILABLE"
                continue
            statuses[t] = "REAL"

        valid_data.attrs["provider_status"] = statuses
        valid_data.attrs["provider"] = "yfinance"
        valid_data.attrs["last_bar"] = last_bars
        valid_data.attrs["retrieved_at"] = data.attrs.get("retrieved_at")
        return valid_data

    def _download_chunk(self, chunk: List[str], start: str, end: str) -> pd.DataFrame:
        last_error = None
        for attempt in range(cfg.PROVIDER_MAX_RETRIES + 1):
            try:
                self._count("yfinance_download")
                data = yf.download(chunk, start=start, end=end, interval="1d", auto_adjust=True,
                                   progress=False, threads=True, group_by="column")
                if data is not None and not data.empty:
                    if not isinstance(data.columns, pd.MultiIndex):
                        data.columns = pd.MultiIndex.from_product([data.columns, chunk])
                    return data
                last_error = "EMPTY_RESPONSE"
            except Exception as exc:  # provider failure: bounded retry, never fabricate
                last_error = f"{type(exc).__name__}: {exc}"
            if attempt < cfg.PROVIDER_MAX_RETRIES:
                self._event("yfinance", "retry", chunk_size=len(chunk), attempt=attempt + 1, error=last_error)
                time.sleep(2 * (attempt + 1))
        logger.error(f"[API_FAILURE] provider=MarketDataProvider chunk_size={len(chunk)} error={last_error} fallback=UNAVAILABLE")
        self._event("yfinance", "chunk_failed", chunk_size=len(chunk), error=last_error, tickers=chunk[:10])
        return pd.DataFrame()

    def _download_yf(self, tickers: List[str], start: str, end: str) -> pd.DataFrame:
        # Enforce minimum 425 days (14 months) lookback for Momentum requirements
        start_date = pd.to_datetime(start)
        min_start = pd.Timestamp.now() - pd.Timedelta(days=425)
        if start_date > min_start:
            start = min_start.strftime('%Y-%m-%d')
        key = (tuple(tickers), start, end)
        if key in self._market_memo:
            return self._market_memo[key]

        frames = []
        size = max(1, cfg.MARKET_DOWNLOAD_CHUNK)
        for i in range(0, len(tickers), size):
            chunk = list(tickers[i:i + size])
            frame = self._download_chunk(chunk, start, end)
            if not frame.empty:
                frames.append(frame)
        data = pd.concat(frames, axis=1) if frames else pd.DataFrame()
        if not data.empty:
            data = data.loc[:, ~data.columns.duplicated()]
        data.attrs["retrieved_at"] = _utc_now().isoformat()
        self._market_memo[key] = data
        return data

    @staticmethod
    def _field(data: pd.DataFrame, names: Tuple[str, ...]) -> Optional[pd.DataFrame]:
        level0 = data.columns.get_level_values(0) if isinstance(data.columns, pd.MultiIndex) else data.columns
        for name in names:
            if name in level0:
                frame = data[name]
                if isinstance(frame, pd.Series):
                    frame = frame.to_frame()
                return frame
        return None

    def _empty_market(self, tickers, start, end) -> pd.DataFrame:
        result = pd.DataFrame(np.nan, index=pd.date_range(start, end), columns=tickers)
        result.attrs["provider_status"] = {ticker: "UNAVAILABLE" for ticker in tickers}
        result.attrs["provider"] = "yfinance"
        result.attrs["retrieved_at"] = _utc_now().isoformat()
        return result

    def get_price_data(self, tickers: List[str], start: str, end: str) -> pd.DataFrame:
        data = self._download_yf(tickers, start=start, end=end)
        # auto_adjust=True => "Close" IS the split/dividend-adjusted close.  yfinance
        # (>=1.x) adds an "Adj Close" column only as an all-NaN filler for symbols
        # that failed in a chunk; preferring it blanked every price whenever one
        # invalid/delisted symbol was present (P6-18 defect fix).
        prices = self._field(data, ("Close",)) if not data.empty else None
        if prices is None:
            return self._empty_market(tickers, start, end)
        prices = prices.reindex(columns=tickers)
        prices.attrs["retrieved_at"] = data.attrs.get("retrieved_at")
        return self._enforce_lookback_and_freshness(prices, tickers)

    def get_volume_data(self, tickers: List[str], start: str, end: str) -> pd.DataFrame:
        data = self._download_yf(tickers, start=start, end=end)
        volumes = self._field(data, ("Volume",)) if not data.empty else None
        if volumes is None:
            return self._empty_market(tickers, start, end)
        volumes = volumes.reindex(columns=tickers)
        volumes.attrs["retrieved_at"] = data.attrs.get("retrieved_at")
        return self._enforce_lookback_and_freshness(volumes, tickers)

    # ----------------------------------------------------------- SEC EDGAR
    def _fetch_sec_facts(self, cik: str) -> Dict[str, Any]:
        """Fetch SEC Company Facts with fair-access pacing (< 10 req/s) and bounded retry."""
        cik_padded = str(cik).zfill(10)
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
        headers = {"User-Agent": cfg.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
        for attempt in range(cfg.PROVIDER_MAX_RETRIES + 1):
            self._sec_limiter.wait()
            self._count("sec_companyfacts")
            try:
                resp = requests.get(url, headers=headers, timeout=(cfg.API_CONNECT_TIMEOUT, 30))
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 404:
                    self._event("sec_edgar", "not_found", cik=cik_padded)
                    return {}
                error = f"HTTP_{resp.status_code}"
            except Exception as exc:
                error = type(exc).__name__
            if attempt < cfg.PROVIDER_MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
        self._event("sec_edgar", "failed", cik=cik_padded, error=error)
        return {}

    def _extract_latest_sec_value(self, facts: Dict[str, Any], taxonomy: str, concept: str) -> float:
        """Legacy helper retained for compatibility: latest filed value, ties -> latest period end."""
        try:
            units = facts.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {})
            if not units:
                return np.nan
            entries = units[list(units.keys())[0]]
            current_date = _utc_now().strftime("%Y-%m-%d")
            valid = [e for e in entries if e.get("filed") and e["filed"] <= current_date]
            if not valid:
                return np.nan
            valid.sort(key=lambda x: (x["filed"], x.get("end", "")), reverse=True)
            return float(valid[0]["val"])
        except Exception:
            return np.nan

    @staticmethod
    def _sec_entries(facts: Dict[str, Any], concept: str) -> List[Dict[str, Any]]:
        units = facts.get("facts", {}).get("us-gaap", {}).get(concept, {}).get("units", {})
        return list(units.get("USD", []))

    @classmethod
    def _sec_annual_flow(cls, facts: Dict[str, Any], concepts, today: str) -> Optional[Dict[str, Any]]:
        """Latest annual (~1y duration, FY, 10-K family) value across candidate concepts."""
        best = None
        for concept in concepts:
            for e in cls._sec_entries(facts, concept):
                if e.get("form") not in ANNUAL_FORMS or not e.get("start") or not e.get("end"):
                    continue
                if not e.get("filed") or e["filed"] > today:
                    continue
                try:
                    days = (pd.Timestamp(e["end"]) - pd.Timestamp(e["start"])).days
                except Exception:
                    continue
                if not 330 <= days <= 380:
                    continue
                key = (e["end"], e["filed"])
                if best is None or key > (best["end"], best["filed"]):
                    best = {"val": e["val"], "end": e["end"], "start": e["start"], "filed": e["filed"],
                            "form": e.get("form"), "concept": concept, "accn": e.get("accn"),
                            "fy": e.get("fy"), "fp": e.get("fp"), "frame": e.get("frame")}
        return best

    @classmethod
    def _sec_instant(cls, facts: Dict[str, Any], concepts, today: str, at_end: Optional[str]) -> Optional[Dict[str, Any]]:
        best = None
        for concept in concepts:
            for e in cls._sec_entries(facts, concept):
                if e.get("start") or not e.get("end") or not e.get("filed") or e["filed"] > today:
                    continue
                if at_end and e["end"] != at_end:
                    continue
                key = (e["end"], e["filed"])
                if best is None or key > (best["end"], best["filed"]):
                    best = {"val": e["val"], "end": e["end"], "filed": e["filed"],
                            "form": e.get("form"), "concept": concept, "accn": e.get("accn"),
                            "fy": e.get("fy"), "fp": e.get("fp")}
        return best

    def _sec_metrics(self, facts: Dict[str, Any]) -> Dict[str, Any]:
        """Period-aligned SEC ROE and profit margin with their provenance."""
        out = {"roe": np.nan, "profitMargin": np.nan, "detail": {}}
        if not facts:
            out["detail"]["status"] = "UNAVAILABLE"
            return out
        today = _utc_now().strftime("%Y-%m-%d")
        ni = self._sec_annual_flow(facts, SEC_NET_INCOME, today)
        if ni is None:
            out["detail"]["status"] = "NET_INCOME_UNAVAILABLE"
            return out
        age = (pd.Timestamp(today) - pd.Timestamp(ni["end"])).days
        out["detail"]["net_income"] = ni
        if age > cfg.SEC_ANNUAL_MAX_AGE_DAYS:
            out["detail"]["status"] = "STALE"
            out["detail"]["period_age_days"] = age
            return out
        equity = self._sec_instant(facts, SEC_EQUITY, today, ni["end"])
        revenue = None
        # P6-19: total revenue = the LARGEST same-period value among total-revenue concepts.
        # Every concept in SEC_REVENUE is a revenue measure <= total revenue, so the maximum is the
        # most complete single reported line and can never be a partial slice when a fuller one exists.
        candidates = {}
        for concept in SEC_REVENUE:
            cand = self._sec_annual_flow(facts, (concept,), today)
            if cand is not None and cand["end"] == ni["end"] and np.isfinite(_finite_or_nan(cand["val"])):
                candidates[concept] = cand
        if candidates:
            revenue = max(candidates.values(), key=lambda c: float(c["val"]))
            out["detail"]["revenue_rule"] = "max_same_period_total_revenue_concept"
            out["detail"]["revenue_candidates"] = {k: v["val"] for k, v in candidates.items()}
        net_income = _finite_or_nan(ni["val"])
        if equity is not None:
            eq = _finite_or_nan(equity["val"])
            out["detail"]["equity"] = equity
            if not np.isnan(net_income) and not np.isnan(eq) and eq > 0:
                out["roe"] = net_income / eq
        if revenue is not None:
            rev = _finite_or_nan(revenue["val"])
            out["detail"]["revenue"] = revenue
            if not np.isnan(net_income) and not np.isnan(rev) and rev > 0:
                if net_income > rev:
                    # P6-19: net income above the selected revenue line proves that line is not total
                    # revenue (e.g. a bank tagging only fee income or lease income).  The SEC margin is
                    # rejected - never reconstructed - and the field falls back to the provider value.
                    out["detail"]["revenue_rejected"] = {
                        "reason": "NET_INCOME_EXCEEDS_REVENUE_CONCEPT", "concept": revenue.get("concept"),
                        "revenue": rev, "net_income": net_income}
                else:
                    out["profitMargin"] = net_income / rev
        out["detail"]["status"] = "REAL"
        out["detail"]["fiscal_period_end"] = ni["end"]
        return out

    # --------------------------------------------------------- yfinance info
    def _fetch_yf_info(self, ticker: str) -> Dict[str, Any]:
        error = None
        for attempt in range(cfg.PROVIDER_MAX_RETRIES + 1):
            self._yf_limiter.wait()
            self._count("yfinance_info")
            try:
                info = yf.Ticker(ticker).info or {}
                return {k: info.get(k) for k in INFO_FIELDS}
            except Exception as exc:
                error = f"{type(exc).__name__}: {str(exc)[:120]}"
                rate_limited = "RateLimit" in type(exc).__name__ or "Too Many" in str(exc)
                if attempt < cfg.PROVIDER_MAX_RETRIES:
                    time.sleep((10 if rate_limited else 2) * (attempt + 1))
        self._event("yfinance", "info_failed", ticker=ticker, error=error)
        return {}

    # ------------------------------------------------------ fundamental cache
    def _cache_path(self, ticker: str) -> str:
        return os.path.join(self.cache_dir, "fundamentals", f"{ticker}.json")

    def _load_cached(self, ticker: str, cik: Optional[str]) -> Optional[Dict[str, Any]]:
        if not self.use_cache:
            return None
        path = self._cache_path(ticker)
        try:
            with open(path) as fh:
                payload = json.load(fh)
            retrieved = datetime.fromisoformat(payload["retrieved_at"])
            if _utc_now() - retrieved > timedelta(hours=cfg.FINANCIAL_CACHE_TTL_HOURS):
                return None
            if payload.get("cik") != (str(cik) if cik else None):
                return None
            if payload.get("schema") != FUNDAMENTALS_CACHE_SCHEMA:
                return None
            if cik and bool(payload.get("sec_enabled", True)) != runtime_config.sec_configured():
                return None  # SEC configuration changed since this entry was written
            return payload
        except Exception:
            return None

    def _save_cached(self, ticker: str, payload: Dict[str, Any]):
        if not self.use_cache:
            return
        path = self._cache_path(ticker)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f"{path}.tmp"
            with open(tmp, "w") as fh:
                json.dump(payload, fh, default=str)
            os.replace(tmp, path)
        except Exception as exc:
            logger.warning(f"Fundamental cache write failed for {ticker}: {exc}")

    def _acquire_fundamentals(self, ticker: str, cik: Optional[str]) -> Dict[str, Any]:
        cached = self._load_cached(ticker, cik)
        if cached is not None:
            self._count("fundamental_cache_hits")
            cached["cache_hit"] = True
            return cached
        sec_enabled = runtime_config.sec_configured()
        if not cik:
            sec = {"roe": np.nan, "profitMargin": np.nan, "detail": {"status": "NO_CIK"}}
        elif not sec_enabled:
            # P6-19: SEC fair-access requires a real contact; without one we do not query SEC at all.
            sec = {"roe": np.nan, "profitMargin": np.nan, "detail": {"status": "SEC_NOT_CONFIGURED"}}
        else:
            sec = self._sec_metrics(self._fetch_sec_facts(cik))
        info = self._fetch_yf_info(ticker)
        payload = {
            "schema": FUNDAMENTALS_CACHE_SCHEMA, "ticker": ticker, "cik": str(cik) if cik else None, "sec_enabled": sec_enabled,
            "retrieved_at": _utc_now().isoformat(),
            "sec": {"roe": None if np.isnan(sec["roe"]) else sec["roe"],
                    "profitMargin": None if np.isnan(sec["profitMargin"]) else sec["profitMargin"],
                    "detail": sec["detail"]},
            "yf_info": info, "yf_info_ok": bool(info),
        }
        # Only cache when at least one provider answered; failures are retried next run.
        if info or sec["detail"].get("status") == "REAL":
            self._save_cached(ticker, payload)
        payload["cache_hit"] = False
        return payload

    @staticmethod
    def _pbr_consistency(pbr: float, market_cap, sec_detail: Dict[str, Any]) -> Dict[str, Any]:
        """Cross-check Yahoo priceToBook against marketCap / SEC stockholders' equity (same company)."""
        equity = _finite_or_nan((sec_detail.get("equity") or {}).get("val"))
        mcap = _finite_or_nan(market_cap)
        if np.isnan(pbr) or np.isnan(equity) or np.isnan(mcap) or pbr <= 0 or equity <= 0 or mcap <= 0:
            return {}
        implied = mcap / equity
        ratio = pbr / implied
        out = {"provider_value": pbr, "implied_market_cap_over_sec_equity": implied, "ratio": ratio,
               "sec_equity_period_end": (sec_detail.get("equity") or {}).get("end"),
               "tolerance_factor": PBR_CONSISTENCY_FACTOR}
        out["status"] = ("REJECTED_INCONSISTENT" if ratio > PBR_CONSISTENCY_FACTOR or ratio < 1 / PBR_CONSISTENCY_FACTOR
                         else "CONSISTENT")
        return out

    def get_financial_data(self, tickers: List[str], ciks: Dict[str, str] = None) -> pd.DataFrame:
        ciks = ciks or {}
        tickers = list(tickers)
        workers = max(1, min(cfg.FINANCIAL_FETCH_WORKERS, len(tickers) or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            payloads = list(pool.map(lambda t: self._acquire_fundamentals(t, ciks.get(t)), tickers))

        rows, provenance, meta = [], {}, {}
        for ticker, p in zip(tickers, payloads):
            sec, info = p["sec"], p.get("yf_info") or {}
            sec_roe = _finite_or_nan(sec.get("roe"))
            sec_margin = _finite_or_nan(sec.get("profitMargin"))
            per = _finite_or_nan(info.get("trailingPE"))
            pbr = _finite_or_nan(info.get("priceToBook"))
            roe = sec_roe if not np.isnan(sec_roe) else _finite_or_nan(info.get("returnOnEquity"))
            margin = sec_margin if not np.isnan(sec_margin) else _finite_or_nan(info.get("profitMargins"))
            pbr_check = self._pbr_consistency(pbr, info.get("marketCap"), sec.get("detail", {}))
            if pbr_check.get("status") == "REJECTED_INCONSISTENT":
                pbr = np.nan
            values = {"per": per, "pbr": pbr, "roe": roe, "profitMargin": margin}
            src = {
                "per": "yfinance", "pbr": "yfinance",
                "roe": "sec_edgar" if not np.isnan(sec_roe) else "yfinance",
                "profitMargin": "sec_edgar" if not np.isnan(sec_margin) else "yfinance",
            }
            provenance[ticker] = {
                field: {"source": src[field] if not np.isnan(values[field]) else None,
                        "status": "REAL" if not np.isnan(values[field]) else "UNAVAILABLE"}
                for field in FUNDAMENTAL_FIELDS
            }
            if pbr_check.get("status") == "REJECTED_INCONSISTENT":
                provenance[ticker]["pbr"] = {"source": None, "status": "REJECTED_INCONSISTENT",
                                             "rejected_provider_value": pbr_check}
            elif pbr_check:
                provenance[ticker]["pbr"]["consistency_check"] = pbr_check
            if sec.get("detail", {}).get("revenue_rejected"):
                provenance[ticker]["profitMargin"]["sec_rejected"] = sec["detail"]["revenue_rejected"]
            provenance[ticker]["_retrieved_at"] = p["retrieved_at"]
            provenance[ticker]["_cache_hit"] = p.get("cache_hit", False)
            provenance[ticker]["_sec_status"] = sec.get("detail", {}).get("status")
            provenance[ticker]["_sec_fiscal_period_end"] = sec.get("detail", {}).get("fiscal_period_end")
            provenance[ticker]["_sec_filings"] = {
                part: {k: d.get(k) for k in ("concept", "start", "end", "filed", "form", "accn", "fy", "fp")}
                for part in ("net_income", "equity", "revenue")
                if isinstance((d := sec.get("detail", {}).get(part)), dict)}
            meta[ticker] = {
                "sector": info.get("sector") or None,
                "industry": info.get("industry") or None,
                "quote_type": info.get("quoteType") or None,
                "name": info.get("longName") or info.get("shortName") or None,
                "currency": info.get("currency") or None,
                "exchange": info.get("exchange") or None,
                "yf_info_ok": bool(p.get("yf_info_ok", bool(info))),
                "source": "yfinance",
            }
            rows.append({"ticker": ticker, **values})

        frame = pd.DataFrame(rows, columns=["ticker", *FUNDAMENTAL_FIELDS]).set_index("ticker")
        frame.attrs["field_provenance"] = provenance
        frame.attrs["security_meta"] = meta
        def _status(ticker):
            row = frame.loc[ticker]
            if row.notna().all():
                # P6-19: a complete observation served from the local cache is CACHED, not REAL.
                return "CACHED" if provenance[ticker].get("_cache_hit") else "REAL"
            return "PARTIAL" if row.notna().any() else "UNAVAILABLE"
        frame.attrs["provider_status"] = {ticker: _status(ticker) for ticker in frame.index}
        return frame

    def get_news_headlines(self, ticker: str) -> List[str]:
        if not self.newsapi:
            return []  # STRICT POLICY: NO MOCK FALLBACKS.

        sub_queries = [f'"{ticker}"', f'"{ticker} stock"']
        q_str = " OR ".join(sub_queries)

        try:
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            all_articles = self.newsapi.get_everything(
                q=q_str,
                from_param=from_date,
                to=datetime.now().strftime('%Y-%m-%d'),
                language='en',
                sort_by='relevancy'
            )
            headlines = [article.get('title') for article in all_articles.get('articles', []) if article.get('title')]
            return headlines[:20] if headlines else []
        except Exception as e:
            logger.error(f"[API_FAILURE] provider=NewsDataProvider ticker={ticker} error={type(e).__name__} fallback=UNAVAILABLE")
            return []
