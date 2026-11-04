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
# P6-20-A2 semantic total-revenue selection (replaces the P6-19 "largest of any revenue concept" rule).
# Tier 1: US-GAAP concepts whose definition IS consolidated total revenue.
SEC_REVENUE_TOTAL = ("Revenues", "RevenuesNetOfInterestExpense", "RegulatedAndUnregulatedOperatingRevenue")
# Tier 2: single-stream concepts (ASC 606 contract revenue / legacy net sales).  They equal total revenue
# only for a company with no other revenue stream, so they are accepted ONLY when no component concept
# below is reported for the same period.
SEC_REVENUE_SINGLE_STREAM = ("RevenueFromContractWithCustomerExcludingAssessedTax",
                             "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet")
# Components / other revenue streams: never total revenue on their own and never summed.
SEC_REVENUE_COMPONENTS = ("OperatingLeaseLeaseIncome", "LeaseIncome", "OperatingLeasesIncomeStatementLeaseRevenue",
                          "RealEstateRevenueNet", "InterestAndDividendIncomeOperating", "NoninterestIncome",
                          "InterestIncomeExpenseNet", "InterestIncomeExpenseAfterProvisionForLoanLoss",
                          "PremiumsEarnedNet")
SEC_REVENUE = SEC_REVENUE_TOTAL + SEC_REVENUE_SINGLE_STREAM   # concepts that can be selected as total revenue
SEC_CONTINUING_OPS = ("IncomeLossFromContinuingOperations",)
# A1 provider-consistency rule: a Yahoo priceToBook more than this factor away from the diagnostic
# marketCap / SEC common equity is UNAVAILABLE (original value and reason kept), never replaced.
PBR_CONSISTENCY_FACTOR = 10.0
PBR_EQUITY_MAX_AGE_DAYS = 200        # latest balance sheet older than this -> cross-check NOT_VERIFIABLE
PBR_SCOPE_TOLERANCE = 0.02           # marketCap must equal price x all-class shares within 2%
YAHOO_MARGIN_MAX_AGE_DAYS = 200      # Yahoo TTM margin: mostRecentQuarter must be at most this old
FUNDAMENTALS_CACHE_SCHEMA = 5
# Version of docs/DATA_INPUT_SPECIFICATION.md implemented by this loader (recorded in run manifests, P6-20).
DATA_INPUT_SPEC_VERSION = "P6-20-A"
SEC_EQUITY = ("StockholdersEquity",)
SEC_PREFERRED = ("PreferredStockValue",)
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "20-F", "40-F"}
BALANCE_SHEET_FORMS = ANNUAL_FORMS | {"10-Q", "10-Q/A", "10-QT"}
INFO_FIELDS = ("trailingPE", "priceToBook", "returnOnEquity", "profitMargins", "sector",
               "industry", "quoteType", "longName", "shortName", "currency", "averageVolume",
               "marketCap", "exchange",
               # P6-20-A: fields needed to validate P/B scope and Yahoo margin freshness
               "currentPrice", "regularMarketPrice", "sharesOutstanding", "impliedSharesOutstanding",
               "financialCurrency", "mostRecentQuarter", "bookValue")


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

    # ------------------------------------------- SEC timestamp eligibility (P6-20-A1..A3)
    @staticmethod
    def _as_of(as_of=None) -> pd.Timestamp:
        ts = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(_utc_now())
        return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")

    @staticmethod
    def _accepted_utc(accepted: Optional[str]) -> Optional[pd.Timestamp]:
        """EDGAR ``acceptanceDateTime``.  EDGAR suffixes it with ``Z`` although the clock is US Eastern.
        Reading it as Eastern is never earlier than the true acceptance instant, so a filing that was not
        yet public can never be admitted."""
        if not accepted:
            return None
        try:
            ts = pd.Timestamp(str(accepted).replace("Z", "").split(".")[0])
            if ts.tzinfo is not None:
                ts = ts.tz_localize(None)
            return ts.tz_localize("America/New_York").tz_convert("UTC")
        except Exception:
            return None

    @classmethod
    def _available_at(cls, e: Dict[str, Any], as_of: pd.Timestamp,
                      accepted: Optional[Dict[str, str]]) -> Tuple[bool, Optional[str]]:
        """A fact may be used only if its filing was public at ``as_of``.

        Accepted datetime known (EDGAR submissions)  -> accepted <= as_of.
        Accepted datetime unknown                    -> filed date strictly before as_of's US/Eastern date
        (a same-day filing is excluded because its acceptance time cannot be verified)."""
        filed = e.get("filed")
        if not filed:
            return False, None
        raw = (accepted or {}).get(e.get("accn"))
        acc = cls._accepted_utc(raw)
        if acc is not None:
            return bool(acc <= as_of), raw
        return filed < as_of.tz_convert("America/New_York").strftime("%Y-%m-%d"), None

    @staticmethod
    def _sec_entries(facts: Dict[str, Any], concept: str, taxonomy: str = "us-gaap",
                     unit: str = "USD") -> List[Dict[str, Any]]:
        # CompanyFacts carries only non-dimensional facts (consolidated, entity-wide) for one CIK;
        # only the USD unit is read, so currencies/units are never mixed.
        units = facts.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {})
        return list(units.get(unit, []))

    @staticmethod
    def _fact(e: Dict[str, Any], concept: str, accepted: Optional[str], **extra) -> Dict[str, Any]:
        out = {"val": e["val"], "start": e.get("start"), "end": e["end"], "filed": e["filed"],
               "accepted": accepted, "form": e.get("form"), "concept": concept, "taxonomy": "us-gaap",
               "unit": "USD", "accn": e.get("accn"), "fy": e.get("fy"), "fp": e.get("fp"),
               "frame": e.get("frame")}
        out.update(extra)
        return out

    @classmethod
    def _sec_annual_flow(cls, facts: Dict[str, Any], concepts, as_of=None, accepted=None,
                         period: Optional[Tuple[str, str]] = None,
                         prefer_accn: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Annual (330-380 day duration, 10-K family) value available at ``as_of``.

        Without ``period``: latest period end, then latest filing (a restatement of the same period wins).
        With ``period``: exactly that (start, end); the filing ``prefer_accn`` is preferred, else the latest."""
        as_of = cls._as_of(as_of)
        best, best_key = None, None
        for concept in concepts:
            for e in cls._sec_entries(facts, concept):
                if e.get("form") not in ANNUAL_FORMS or not e.get("start") or not e.get("end"):
                    continue
                if np.isnan(_finite_or_nan(e.get("val"))):
                    continue
                ok, acc = cls._available_at(e, as_of, accepted)
                if not ok:
                    continue
                try:
                    days = (pd.Timestamp(e["end"]) - pd.Timestamp(e["start"])).days
                except Exception:
                    continue
                if not 330 <= days <= 380:
                    continue
                if period is not None and (e["start"], e["end"]) != tuple(period):
                    continue
                key = (e["end"], bool(prefer_accn) and e.get("accn") == prefer_accn, e["filed"])
                if best is None or key > best_key:
                    best, best_key = cls._fact(e, concept, acc, duration_days=days), key
        return best

    @classmethod
    def _sec_instant(cls, facts: Dict[str, Any], concepts, as_of=None, accepted=None,
                     at_end: Optional[str] = None, forms=None,
                     prefer_accn: Optional[str] = None) -> Optional[Dict[str, Any]]:
        as_of = cls._as_of(as_of)
        best, best_key = None, None
        for concept in concepts:
            for e in cls._sec_entries(facts, concept):
                if e.get("start") or not e.get("end"):
                    continue
                if forms is not None and e.get("form") not in forms:
                    continue
                if np.isnan(_finite_or_nan(e.get("val"))):
                    continue
                ok, acc = cls._available_at(e, as_of, accepted)
                if not ok:
                    continue
                if at_end and e["end"] != at_end:
                    continue
                key = (e["end"], bool(prefer_accn) and e.get("accn") == prefer_accn, e["filed"])
                if best is None or key > best_key:
                    best, best_key = cls._fact(e, concept, acc), key
        return best

    @classmethod
    def _pb_common_equity(cls, facts: Dict[str, Any], as_of, accepted) -> Dict[str, Any]:
        """A1: common shareholders' equity from the latest balance sheet public at ``as_of``.

        Common equity = StockholdersEquity (parent, excludes non-controlling interests) minus
        PreferredStockValue at the same instant.  Preferred stock that is not tagged at that instant is
        recorded as such and treated as zero (its effect is far inside the 10x cross-check tolerance)."""
        eq = cls._sec_instant(facts, SEC_EQUITY, as_of, accepted, forms=BALANCE_SHEET_FORMS)
        if eq is None:
            return {"status": "UNAVAILABLE", "reason": "SEC_STOCKHOLDERS_EQUITY_UNAVAILABLE"}
        pref = cls._sec_instant(facts, SEC_PREFERRED, as_of, accepted, at_end=eq["end"],
                                forms=BALANCE_SHEET_FORMS, prefer_accn=eq.get("accn"))
        common = float(eq["val"]) - (float(pref["val"]) if pref else 0.0)
        age = (as_of.tz_localize(None).normalize() - pd.Timestamp(eq["end"])).days
        out = {"stockholders_equity": eq, "preferred_stock": pref,
               "preferred_treatment": "SUBTRACTED_SAME_INSTANT" if pref else "NOT_TAGGED_AT_INSTANT_TREATED_AS_ZERO",
               "common_equity": common, "balance_sheet_date": eq["end"], "age_days": age,
               "max_age_days": PBR_EQUITY_MAX_AGE_DAYS}
        if age > PBR_EQUITY_MAX_AGE_DAYS:
            out.update(status="STALE", reason="SEC_BALANCE_SHEET_OLDER_THAN_MAX_AGE")
        elif common <= 0:
            out.update(status="NON_POSITIVE", reason="NON_POSITIVE_COMMON_EQUITY")
        else:
            out["status"] = "VALID"
        return out

    @classmethod
    def _select_total_revenue(cls, facts: Dict[str, Any], ni: Dict[str, Any], as_of, accepted) -> Dict[str, Any]:
        """A2: consolidated total revenue for exactly the net-income period (never combined, never summed)."""
        period = (ni["start"], ni["end"])

        def found(concepts):
            out = {}
            for c in concepts:
                f = cls._sec_annual_flow(facts, (c,), as_of, accepted, period=period, prefer_accn=ni.get("accn"))
                if f is not None:
                    out[c] = f
            return out

        total, single, comps = (found(SEC_REVENUE_TOTAL), found(SEC_REVENUE_SINGLE_STREAM),
                                found(SEC_REVENUE_COMPONENTS))
        brief = lambda f, tier: {"val": f["val"], "accn": f.get("accn"), "filed": f.get("filed"), "tier": tier}
        res = {"rule": "P6-20-A2 tiered semantic total revenue", "period": list(period),
               "candidates": {**{c: brief(f, 1) for c, f in total.items()},
                              **{c: brief(f, 2) for c, f in single.items()},
                              **{c: brief(f, "component") for c, f in comps.items()}},
               "rejected": []}
        selected, tier = None, None
        for c, f in list(total.items()) + list(single.items()):
            if float(f["val"]) <= 0:
                res["rejected"].append({"concept": c, "val": f["val"], "reason": "NON_POSITIVE_REVENUE"})
        pos_total = {c: f for c, f in total.items() if float(f["val"]) > 0}
        pos_single = {c: f for c, f in single.items() if float(f["val"]) > 0}
        if pos_total:
            selected, tier = max(pos_total.values(), key=lambda f: float(f["val"])), 1
        elif pos_single:
            if comps:
                for c, f in pos_single.items():
                    res["rejected"].append({"concept": c, "val": f["val"],
                                            "reason": "SINGLE_STREAM_CONCEPT_WITH_OTHER_REVENUE_STREAMS",
                                            "other_streams": {k: v["val"] for k, v in comps.items()}})
            else:
                selected, tier = max(pos_single.values(), key=lambda f: float(f["val"])), 2
        for c, f in comps.items():
            res["rejected"].append({"concept": c, "val": f["val"], "reason": "COMPONENT_NOT_TOTAL_REVENUE"})
        if selected is None:
            res.update(status="UNAVAILABLE",
                       reason=("NO_RELIABLE_TOTAL_REVENUE" if res["candidates"] else "NO_REVENUE_CONCEPT_FOR_PERIOD"))
        else:
            res.update(status="SELECTED", tier=tier, selected=selected,
                       same_filing_as_net_income=selected.get("accn") == ni.get("accn"))
        return res

    @classmethod
    def _margin_anomaly_review(cls, facts, ni, revenue: float, as_of, accepted) -> Dict[str, Any]:
        """A3: net margin above 100% with validated total revenue is reviewed, not declared impossible."""
        cont = cls._sec_annual_flow(facts, SEC_CONTINUING_OPS, as_of, accepted,
                                    period=(ni["start"], ni["end"]), prefer_accn=ni.get("accn"))
        review = {"trigger": "NET_MARGIN_ABOVE_100PCT", "net_margin": float(ni["val"]) / revenue,
                  "continuing_operations_income": cont}
        if cont is None:
            review.update(decision="REJECTED", explanation="CONTINUING_OPERATIONS_INCOME_UNAVAILABLE")
        elif float(cont["val"]) <= revenue:
            review.update(decision="ACCEPTED",
                          explanation="CONTINUING_OPERATIONS_INCOME_WITHIN_REVENUE: excess from discontinued "
                                      "operations or exceptional items")
        else:
            review.update(decision="REJECTED", explanation="CONTINUING_OPERATIONS_INCOME_EXCEEDS_REVENUE")
        return review

    def _sec_metrics(self, facts: Dict[str, Any], as_of=None, accepted: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Period-aligned SEC ROE and profit margin (A2/A3) and P/B common equity (A1), with provenance."""
        out = {"roe": np.nan, "profitMargin": np.nan, "detail": {}}
        if not facts:
            out["detail"]["status"] = "UNAVAILABLE"
            return out
        as_of = self._as_of(as_of)
        accepted = accepted or {}
        d = out["detail"]
        d["as_of"] = as_of.isoformat()
        d["accepted_datetime_source"] = ("edgar_submissions" if accepted else
                                         "UNAVAILABLE (filed date must be strictly before as_of date)")
        d["pb_equity"] = self._pb_common_equity(facts, as_of, accepted)
        ni = self._sec_annual_flow(facts, SEC_NET_INCOME, as_of, accepted)
        if ni is None:
            d["status"] = "NET_INCOME_UNAVAILABLE"
            return out
        age = (as_of.tz_localize(None).normalize() - pd.Timestamp(ni["end"])).days
        d["net_income"] = ni
        if age > cfg.SEC_ANNUAL_MAX_AGE_DAYS:
            d["status"] = "STALE"
            d["period_age_days"] = age
            return out
        net_income = _finite_or_nan(ni["val"])
        equity = self._sec_instant(facts, SEC_EQUITY, as_of, accepted, at_end=ni["end"], prefer_accn=ni.get("accn"))
        if equity is not None:
            eq = _finite_or_nan(equity["val"])
            d["equity"] = equity
            if not np.isnan(net_income) and not np.isnan(eq) and eq > 0:
                out["roe"] = net_income / eq
        selection = self._select_total_revenue(facts, ni, as_of, accepted)
        d["revenue_selection"] = selection
        if selection["status"] == "SELECTED":
            revenue = selection["selected"]
            rev = float(revenue["val"])
            d["revenue"] = revenue
            if not np.isnan(net_income):
                margin = net_income / rev
                if margin > 1.0:
                    review = self._margin_anomaly_review(facts, ni, rev, as_of, accepted)
                    d["margin_anomaly_review"] = review
                    if review["decision"] == "ACCEPTED":
                        out["profitMargin"] = margin
                    else:
                        d["revenue_rejected"] = {"reason": "NET_MARGIN_ABOVE_100PCT_UNEXPLAINED",
                                                 "concept": revenue.get("concept"), "revenue": rev,
                                                 "net_income": net_income, "review": review["explanation"]}
                else:
                    out["profitMargin"] = margin
        else:
            d["revenue_rejected"] = {"reason": selection["reason"], "concept": None, "net_income": net_income,
                                     "rejected_facts": selection["rejected"]}
        d["status"] = "REAL"
        d["fiscal_period_end"] = ni["end"]
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

    def _fetch_sec_submissions(self, cik: str) -> Dict[str, str]:
        """accession number -> EDGAR acceptanceDateTime (recent filings).  {} when unavailable."""
        cik_padded = str(cik).zfill(10)
        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        headers = {"User-Agent": cfg.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
        for attempt in range(cfg.PROVIDER_MAX_RETRIES + 1):
            self._sec_limiter.wait()
            self._count("sec_submissions")
            try:
                resp = requests.get(url, headers=headers, timeout=(cfg.API_CONNECT_TIMEOUT, 30))
                if resp.status_code == 200:
                    recent = (resp.json().get("filings") or {}).get("recent") or {}
                    return {a: t for a, t in zip(recent.get("accessionNumber", []),
                                                 recent.get("acceptanceDateTime", [])) if a and t}
                if resp.status_code == 404:
                    return {}
                error = f"HTTP_{resp.status_code}"
            except Exception as exc:
                error = type(exc).__name__
            if attempt < cfg.PROVIDER_MAX_RETRIES:
                time.sleep(1.5 * (attempt + 1))
        self._event("sec_edgar", "submissions_failed", cik=cik_padded, error=error)
        return {}

    def _acquire_fundamentals(self, ticker: str, cik: Optional[str]) -> Dict[str, Any]:
        cached = self._load_cached(ticker, cik)
        if cached is not None:
            self._count("fundamental_cache_hits")
            cached["cache_hit"] = True
            return cached
        sec_enabled = runtime_config.sec_configured()
        as_of = _utc_now()
        if not cik:
            sec = {"roe": np.nan, "profitMargin": np.nan, "detail": {"status": "NO_CIK"}}
        elif not sec_enabled:
            # P6-19: SEC fair-access requires a real contact; without one we do not query SEC at all.
            sec = {"roe": np.nan, "profitMargin": np.nan, "detail": {"status": "SEC_NOT_CONFIGURED"}}
        else:
            facts = self._fetch_sec_facts(cik)
            accepted = self._fetch_sec_submissions(cik) if facts else {}
            sec = self._sec_metrics(facts, as_of=as_of, accepted=accepted)
        info = self._fetch_yf_info(ticker)
        payload = {
            "schema": FUNDAMENTALS_CACHE_SCHEMA, "ticker": ticker, "cik": str(cik) if cik else None, "sec_enabled": sec_enabled,
            "retrieved_at": _utc_now().isoformat(), "sec_as_of": as_of.isoformat(),
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
    def _share_scope(mcap: float, info: Dict[str, Any]) -> Dict[str, Any]:
        """A1 scope check: Yahoo marketCap must value ALL share classes (price x all-class shares), because
        SEC StockholdersEquity is entity-wide.  A single-class market cap would mis-scale P/B."""
        price = _finite_or_nan(info.get("currentPrice"))
        if np.isnan(price) or price <= 0:
            price = _finite_or_nan(info.get("regularMarketPrice"))
        shares = _finite_or_nan(info.get("sharesOutstanding"))
        implied = _finite_or_nan(info.get("impliedSharesOutstanding"))
        all_class = implied if not np.isnan(implied) and implied > 0 else shares
        out = {"price": None if np.isnan(price) else price, "shares_outstanding": None if np.isnan(shares) else shares,
               "implied_shares_outstanding": None if np.isnan(implied) else implied, "tolerance": PBR_SCOPE_TOLERANCE}
        if np.isnan(price) or price <= 0:
            return {**out, "status": "NOT_VERIFIABLE", "reason": "PRICE_UNAVAILABLE_FOR_SCOPE_CHECK"}
        if np.isnan(all_class) or all_class <= 0:
            return {**out, "status": "NOT_VERIFIABLE", "reason": "SHARE_COUNT_UNAVAILABLE_FOR_SCOPE_CHECK"}
        mcap_shares = mcap / price
        out["market_cap_over_price"] = mcap_shares
        if abs(mcap_shares / all_class - 1) <= PBR_SCOPE_TOLERANCE:
            return {**out, "status": "COMPATIBLE", "scope": "ALL_SHARE_CLASSES_AT_QUOTED_PRICE"}
        if (not np.isnan(shares) and shares > 0 and abs(mcap_shares / shares - 1) <= PBR_SCOPE_TOLERANCE
                and all_class > shares * (1 + PBR_SCOPE_TOLERANCE)):
            return {**out, "status": "NOT_VERIFIABLE", "reason": "SINGLE_CLASS_MARKET_CAP_VS_ENTITY_EQUITY"}
        return {**out, "status": "NOT_VERIFIABLE", "reason": "MARKET_CAP_SHARE_COUNT_UNRECONCILED"}

    @classmethod
    def _pbr_cross_check(cls, pbr: float, info: Dict[str, Any], sec_detail: Dict[str, Any]) -> Dict[str, Any]:
        """A1: Yahoo priceToBook vs diagnostic marketCap / SEC common equity.

        status: CONSISTENT | INCONSISTENT (>10x either way -> Yahoo value UNAVAILABLE, never replaced) |
        NOT_VERIFIABLE (diagnostic cannot be computed validly -> Yahoo value kept, labelled) |
        PROVIDER_VALUE_UNAVAILABLE (no Yahoo value to check)."""
        out = {"rule": "P6-20-A1", "provider_value": None if np.isnan(pbr) else pbr,
               "tolerance_factor": PBR_CONSISTENCY_FACTOR, "reasons": []}
        eqd = sec_detail.get("pb_equity") or {}
        out["sec_common_equity"] = {k: eqd.get(k) for k in ("status", "common_equity", "balance_sheet_date",
                                                           "age_days", "preferred_treatment")}
        out["sec_equity_filing"] = {k: (eqd.get("stockholders_equity") or {}).get(k)
                                    for k in ("concept", "end", "filed", "accepted", "form", "accn", "fy", "fp")}
        if eqd.get("status") != "VALID":
            out["reasons"].append(eqd.get("reason") or "SEC_EQUITY_UNAVAILABLE")
        mcap = _finite_or_nan(info.get("marketCap"))
        out["market_cap"] = None if np.isnan(mcap) else mcap
        if np.isnan(mcap) or mcap <= 0:
            out["reasons"].append("MARKET_CAP_UNAVAILABLE")
        else:
            scope = cls._share_scope(mcap, info)
            out["share_scope"] = scope
            if scope["status"] != "COMPATIBLE":
                out["reasons"].append(scope["reason"])
        for k in ("currency", "financialCurrency"):
            if info.get(k) and info.get(k) != "USD":
                out["reasons"].append(f"CURRENCY_NOT_USD_{k}")
        if out["reasons"]:
            out["diagnostic_pbr"] = None
            out["status"] = "PROVIDER_VALUE_UNAVAILABLE" if np.isnan(pbr) else "NOT_VERIFIABLE"
            return out
        diag = mcap / float(eqd["common_equity"])
        out["diagnostic_pbr"] = diag
        if np.isnan(pbr):
            out["status"] = "PROVIDER_VALUE_UNAVAILABLE"
            return out
        ratio = pbr / diag
        out["ratio"] = ratio
        out["status"] = ("INCONSISTENT" if pbr <= 0 or ratio > PBR_CONSISTENCY_FACTOR
                         or ratio < 1 / PBR_CONSISTENCY_FACTOR else "CONSISTENT")
        return out

    @staticmethod
    def _yahoo_margin(info: Dict[str, Any], as_of) -> Tuple[float, Dict[str, Any]]:
        """A3: Yahoo profitMargins (provider TTM net income / TTM revenue, one provider, one period) is
        usable only if finite, <= 100% and its latest quarter is fresh."""
        m = _finite_or_nan(info.get("profitMargins"))
        prov = {"definition": "yfinance profitMargins: provider-computed TTM net income / TTM total revenue",
                "max_age_days": YAHOO_MARGIN_MAX_AGE_DAYS}
        if np.isnan(m):
            return np.nan, {**prov, "status": "UNAVAILABLE", "reason": "PROVIDER_VALUE_MISSING"}
        prov["provider_value"] = m
        mrq = _finite_or_nan(info.get("mostRecentQuarter"))
        if np.isnan(mrq):
            return np.nan, {**prov, "status": "UNAVAILABLE", "reason": "FRESHNESS_UNVERIFIABLE_NO_MOST_RECENT_QUARTER"}
        q_end = pd.Timestamp(int(mrq), unit="s")
        ref = pd.Timestamp(as_of)
        ref = ref.tz_convert("UTC").tz_localize(None) if ref.tzinfo is not None else ref
        age = (ref.normalize() - q_end.normalize()).days
        prov.update(most_recent_quarter=str(q_end.date()), age_days=age)
        if age > YAHOO_MARGIN_MAX_AGE_DAYS:
            return np.nan, {**prov, "status": "UNAVAILABLE", "reason": "PROVIDER_PERIOD_STALE"}
        if m > 1.0:
            return np.nan, {**prov, "status": "UNAVAILABLE", "reason": "ABOVE_100PCT_NOT_REVIEWABLE_FROM_PROVIDER"}
        return m, {**prov, "status": "VALID"}

    def get_financial_data(self, tickers: List[str], ciks: Dict[str, str] = None) -> pd.DataFrame:
        ciks = ciks or {}
        tickers = list(tickers)
        workers = max(1, min(cfg.FINANCIAL_FETCH_WORKERS, len(tickers) or 1))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            payloads = list(pool.map(lambda t: self._acquire_fundamentals(t, ciks.get(t)), tickers))

        rows, provenance, meta = [], {}, {}
        for ticker, p in zip(tickers, payloads):
            sec, info = p["sec"], p.get("yf_info") or {}
            detail = sec.get("detail", {}) or {}
            sec_roe = _finite_or_nan(sec.get("roe"))
            sec_margin = _finite_or_nan(sec.get("profitMargin"))
            per = _finite_or_nan(info.get("trailingPE"))
            pbr = _finite_or_nan(info.get("priceToBook"))
            roe = sec_roe if not np.isnan(sec_roe) else _finite_or_nan(info.get("returnOnEquity"))
            yahoo_margin_check = None
            if not np.isnan(sec_margin):
                margin = sec_margin
            else:
                # A3: never SEC net income / Yahoo revenue; Yahoo's own margin only if validated.
                margin, yahoo_margin_check = self._yahoo_margin(info, p.get("retrieved_at") or _utc_now())
            pbr_check = self._pbr_cross_check(pbr, info, detail)
            if pbr_check.get("status") == "INCONSISTENT":
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
            if pbr_check.get("status") == "INCONSISTENT":
                provenance[ticker]["pbr"] = {"source": None, "status": "UNAVAILABLE",
                                             "reason": "PBR_INCONSISTENT_WITH_SEC_COMMON_EQUITY",
                                             "rejected_provider_value": pbr_check}
            else:
                provenance[ticker]["pbr"]["consistency_check"] = pbr_check
            if detail.get("revenue_rejected"):
                provenance[ticker]["profitMargin"]["sec_rejected"] = detail["revenue_rejected"]
            if detail.get("margin_anomaly_review"):
                provenance[ticker]["profitMargin"]["anomaly_review"] = {
                    k: v for k, v in detail["margin_anomaly_review"].items() if k != "continuing_operations_income"}
            if yahoo_margin_check is not None:
                key = "yahoo_validation" if yahoo_margin_check["status"] == "VALID" else "yahoo_rejected"
                provenance[ticker]["profitMargin"][key] = yahoo_margin_check
            if isinstance(detail.get("revenue_selection"), dict):
                rs = detail["revenue_selection"]
                provenance[ticker]["profitMargin"]["revenue_selection"] = {
                    k: rs.get(k) for k in ("rule", "status", "tier", "reason", "same_filing_as_net_income",
                                           "candidates", "rejected")}
            provenance[ticker]["_retrieved_at"] = p["retrieved_at"]
            provenance[ticker]["_sec_as_of"] = p.get("sec_as_of")
            provenance[ticker]["_cache_hit"] = p.get("cache_hit", False)
            provenance[ticker]["_sec_status"] = detail.get("status")
            provenance[ticker]["_sec_fiscal_period_end"] = detail.get("fiscal_period_end")
            provenance[ticker]["_sec_accepted_datetime_source"] = detail.get("accepted_datetime_source")
            provenance[ticker]["_sec_filings"] = {
                part: {k: d.get(k) for k in ("concept", "taxonomy", "unit", "start", "end", "duration_days",
                                             "filed", "accepted", "form", "accn", "fy", "fp")}
                for part in ("net_income", "equity", "revenue")
                if isinstance((d := detail.get(part)), dict)}
            sector_raw = info.get("sector")
            sector = sector_raw.strip() if isinstance(sector_raw, str) and sector_raw.strip() else None
            meta[ticker] = {
                "sector": sector,
                "sector_raw": sector_raw if sector_raw not in ("",) else None,
                "sector_observed_at": p["retrieved_at"],
                "sector_status": ("MISSING" if sector is None else ("CACHED" if p.get("cache_hit") else "REAL")),
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
