"""Adapters around existing acquisition code; no Quant Engine imports are introduced."""

from datetime import datetime, timedelta, timezone
import threading
import time
import requests
from typing import Optional
from urllib.parse import urlparse

import pandas as pd

from contracts.normalized_data import DataStatus, NormalizedData
from contracts.security import SecurityIdentity
from .base import ProviderContext, ProviderKind


class _BaseAdapter:
    ttl_seconds = 3600

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    @staticmethod
    def _historical_supported(context: ProviderContext) -> bool:
        return context.as_of.date() == datetime.now(timezone.utc).date()


class YFinanceMarketProvider(_BaseAdapter):
    name, kind, ttl_seconds = "yfinance", ProviderKind.MARKET, 900

    def fetch(self, security: SecurityIdentity, context: ProviderContext) -> NormalizedData:
        import yfinance as yf
        end = context.as_of.date().isoformat()
        start = (context.as_of - timedelta(days=context.lookback_days)).date().isoformat()
        # Current yfinance requires its own curl-cffi session; DataLoader's requests.Session is incompatible.
        raw = yf.download([security.ticker], start=start, end=end, interval="1d", auto_adjust=False,
                          progress=False, threads=False, timeout=context.timeout_seconds)
        if raw is None or raw.empty:
            raise RuntimeError("market_data_unavailable")
        prices = raw["Close"] if "Close" in raw.columns else raw
        series = prices[security.ticker] if security.ticker in prices else prices.iloc[:, 0]
        series = series.dropna()
        
        adj_prices = raw.get("Adj Close", raw)
        adj_series = adj_prices[security.ticker] if security.ticker in adj_prices else adj_prices.iloc[:, 0]
        adj_series = adj_series.dropna()
        
        observed = pd.Timestamp(series.index[-1]).to_pydatetime().replace(tzinfo=timezone.utc)
        return NormalizedData(security.security_id, security.ticker, "market",
            {
                "close": {str(k): float(v) for k, v in series.items()},
                "adjusted_close": {str(k): float(v) for k, v in adj_series.items()}
            }, self.name, DataStatus.REAL, 0.9,
            observed, self._now(), self._now() + timedelta(seconds=self.ttl_seconds), request_id=context.request_id)


class YFinanceFinancialProvider(_BaseAdapter):
    name, kind, ttl_seconds = "yfinance", ProviderKind.FINANCIAL, 86400

    def fetch(self, security: SecurityIdentity, context: ProviderContext) -> NormalizedData:
        if not self._historical_supported(context):
            return NormalizedData(security.security_id, security.ticker, "financial", {}, self.name,
                DataStatus.UNAVAILABLE, 0.0, None, self._now(), None, request_id=context.request_id,
                error_code="historical_as_of_not_supported")
        import yfinance as yf
        try:
            ticker = yf.Ticker(security.ticker)
            info = ticker.info
            if not info:
                raise ValueError("empty_info")
        except Exception as e:
            from utils.logger import setup_logger
            setup_logger("YFinanceFinancialProvider").error(
                f"Failed to fetch financials for {security.ticker}: {type(e).__name__}"
            )
            return NormalizedData(security.security_id, security.ticker, "financial", {}, self.name,
                DataStatus.UNAVAILABLE, 0.0, None, self._now(), None, request_id=context.request_id,
                error_code="financial_data_unavailable")

        payload = {
            "per": info.get("trailingPE"),
            "pbr": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"),
            "profitMargin": info.get("profitMargins"),
            "forward_pe": info.get("forwardPE"),
            "psr": info.get("priceToSalesTrailing12Months") or info.get("priceToSales"),
            "ev_ebitda": info.get("enterpriseToEbitda"),
            "roa": info.get("returnOnAssets"),
            "operating_margin": info.get("operatingMargins"),
            "gross_margin": info.get("grossMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "revenue": info.get("totalRevenue"),
            "operating_income": info.get("operatingIncome"),
            "net_income": info.get("netIncome"),
            "total_assets": info.get("totalAssets"),
            "total_liabilities": info.get("totalLiabilities"),
            "cash": info.get("totalCash") or info.get("totalCashOrShortTermInvestments"),
            "debt": info.get("totalDebt"),
            "free_cash_flow": info.get("freeCashflow")
        }
        
        clean_payload = {}
        for k, v in payload.items():
            if v is None:
                clean_payload[k] = None
            else:
                try:
                    clean_payload[k] = float(v)
                except (ValueError, TypeError):
                    clean_payload[k] = None

        # Check if at least some core fields are present
        acquired_count = sum(1 for v in clean_payload.values() if v is not None)
        if acquired_count == 0:
            return NormalizedData(security.security_id, security.ticker, "financial", {}, self.name,
                DataStatus.UNAVAILABLE, 0.0, None, self._now(), None, request_id=context.request_id,
                error_code="all_financial_fields_nan")

        return NormalizedData(security.security_id, security.ticker, "financial", clean_payload, self.name,
            DataStatus.REAL_CURRENT, 0.75, context.as_of, self._now(), self._now() + timedelta(seconds=self.ttl_seconds),
            request_id=context.request_id)


class NewsProviderAdapter(_BaseAdapter):
    name, kind, ttl_seconds = "newsapi", ProviderKind.NEWS, 3600

    def fetch(self, security: SecurityIdentity, context: ProviderContext) -> NormalizedData:
        if not self._historical_supported(context):
            return NormalizedData(security.security_id, security.ticker, "news", [], self.name,
                DataStatus.UNAVAILABLE, 0.0, None, self._now(), None, request_id=context.request_id,
                error_code="historical_as_of_not_supported")
        
        import utils.config
        api_key = utils.config.NEWS_API_KEY
        if not api_key or api_key == "YOUR_NEWS_API_KEY_HERE":
            articles = self._get_mock_articles(security, context)
            observed = max((pd.to_datetime(x.get("published_at"), utc=True).to_pydatetime() for x in articles if x.get("published_at")),
                           default=context.as_of)
            return NormalizedData(security.security_id, security.ticker, "news", articles, self.name,
                DataStatus.FALLBACK, 0.2, observed, self._now(), self._now() + timedelta(seconds=self.ttl_seconds),
                is_fallback=True, request_id=context.request_id, error_code="news_api_key_missing")

        from datetime import datetime, timedelta
        from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        q_str = f'"{security.ticker}" OR "{security.company_name or security.ticker}"'
        
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": q_str,
            "from": from_date,
            "language": "en",
            "sortBy": "relevancy",
            "apiKey": api_key
        }
        
        try:
            resp = requests.get(url, params=params, timeout=context.timeout_seconds or 10)
            if resp.status_code == 401:
                raise ValueError("Unauthorized (invalid API key)")
            elif resp.status_code == 429:
                raise ValueError("Rate limited (too many requests)")
            elif resp.status_code != 200:
                raise ValueError(f"HTTP error: {resp.status_code}")
                
            res_dict = resp.json()
            articles = []
            for art in res_dict.get("articles", []):
                title = art.get("title")
                published_at = art.get("publishedAt")
                source_name = art.get("source", {}).get("name") or "unknown"
                url_str = art.get("url")
                
                if title and published_at:
                    articles.append({
                        "headline": title,
                        "source": source_name,
                        "published_at": published_at,
                        "url": url_str
                    })
                    
            if not articles:
                raise ValueError("No articles found")
                
            observed = max((pd.to_datetime(x.get("published_at"), utc=True).to_pydatetime() for x in articles if x.get("published_at")),
                           default=context.as_of)
            return NormalizedData(security.security_id, security.ticker, "news", articles, self.name,
                DataStatus.REAL, 0.8, observed, self._now(), self._now() + timedelta(seconds=self.ttl_seconds),
                request_id=context.request_id)
                
        except Exception as e:
            articles = self._get_mock_articles(security, context)
            observed = max((pd.to_datetime(x.get("published_at"), utc=True).to_pydatetime() for x in articles if x.get("published_at")),
                           default=context.as_of)
            return NormalizedData(security.security_id, security.ticker, "news", articles, self.name,
                DataStatus.FALLBACK, 0.2, observed, self._now(), self._now() + timedelta(seconds=self.ttl_seconds),
                is_fallback=True, request_id=context.request_id, error_code=type(e).__name__)

    def _get_mock_articles(self, security: SecurityIdentity, context: ProviderContext) -> list:
        from datetime import datetime, timedelta
        now = datetime.now()
        company_name = security.company_name or security.ticker
        return [
            {
                "headline": f"{company_name} reports earnings beat expectations",
                "source": "Reuters",
                "published_at": (now - timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "url": "http://example.com/art1"
            },
            {
                "headline": f"Lawsuit filed against {company_name} over battery issues",
                "source": "Bloomberg",
                "published_at": (now - timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "url": "http://example.com/art2"
            },
            {
                "headline": f"Analysts expect {company_name} to maintain strong guidance",
                "source": "Wall Street Journal",
                "published_at": (now - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "url": "http://example.com/art3"
            },
            {
                "headline": f"{security.ticker} shares drop despite strong earnings",
                "source": "unknown",
                "published_at": (now - timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ'),
                "url": "http://example.com/art4"
            }
        ]


class SECProviderAdapter(_BaseAdapter):
    name, kind, ttl_seconds = "sec_edgar", ProviderKind.SEC, 86400
    _lock = threading.Lock()
    _last_request_at = 0.0

    @classmethod
    def _rate_limit(cls) -> None:
        """Local SEC policy: sequential and <= 2 requests per second."""
        with cls._lock:
            delay = 0.5 - (time.monotonic() - cls._last_request_at)
            if delay > 0:
                time.sleep(delay)
            cls._last_request_at = time.monotonic()

    def fetch(self, security: SecurityIdentity, context: ProviderContext) -> NormalizedData:
        if not security.cik:
            return NormalizedData(security.security_id, security.ticker, "sec", {}, self.name, DataStatus.UNAVAILABLE,
                0.0, None, self._now(), None, request_id=context.request_id, error_code="cik_unavailable")
        from alpha_engine.data.sec.sec_api_provider import SecApiProvider
        provider = SecApiProvider()
        self._rate_limit()
        filings = provider.fetch_filings(security.ticker, filing_type="4", limit=3)
        filings = [f for f in filings if f.get("date", "9999-12-31") <= context.as_of.date().isoformat()]
        if not filings:
            return NormalizedData(security.security_id, security.ticker, "sec", {"filings": [], "transactions": []},
                self.name, DataStatus.UNAVAILABLE, 0.0, None, self._now(), None, request_id=context.request_id,
                error_code="form4_unavailable")
        from .sec_parser import parse_ownership_xml
        transactions = []
        for filing in filings:
            source_url = self._raw_ownership_url(filing["url"])
            transactions.extend(parse_ownership_xml(self._fetch_ownership_xml(source_url), security.security_id,
                                                     security.cik, source_url, filing.get("accession_number")))
        if not transactions:
            return NormalizedData(security.security_id, security.ticker, "sec", {"filings": filings, "transactions": []},
                self.name, DataStatus.UNAVAILABLE, 0.0, None, self._now(), None, request_id=context.request_id,
                error_code="form4_transaction_unavailable")
        observed = max(pd.to_datetime(f["date"], utc=True).to_pydatetime() for f in filings)
        return NormalizedData(security.security_id, security.ticker, "sec", {"filings": filings, "transactions": transactions},
            "sec_edgar_archive", DataStatus.REAL, 0.8, observed,
            self._now(), self._now() + timedelta(seconds=self.ttl_seconds), request_id=context.request_id,
            metadata={"submissions_source": getattr(provider, "last_source", {}).get(security.ticker, self.name)})

    @staticmethod
    def _raw_ownership_url(url: str) -> str:
        """SEC primaryDocument may be an XSL-rendered path; parser needs the archive XML."""
        marker = "/xslF345X06/"
        if marker in url:
            return url.split(marker, 1)[0] + "/" + url.rsplit("/", 1)[-1]
        return url

    @classmethod
    def _fetch_ownership_xml(cls, url: str) -> str:
        """Bounded, retrying fetch for a raw ownership document; never use legacy 2KB preview."""
        headers = {"User-Agent": __import__("os").getenv("SEC_USER_AGENT", "").strip()}  # P6-19: no fabricated contact
        last_error = None
        for attempt in range(2):
            cls._rate_limit()
            try:
                response = requests.get(url, headers=headers, timeout=(5, 10), stream=True)
                if response.status_code == 429:
                    time.sleep(min(int(response.headers.get("Retry-After", "1")), 5))
                    continue
                response.raise_for_status()
                chunks, total = [], 0
                for chunk in response.iter_content(chunk_size=16384, decode_unicode=False):
                    total += len(chunk)
                    if total > 512_000:
                        raise ValueError("ownership_document_too_large")
                    chunks.append(chunk)
                return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.5)
        raise RuntimeError(type(last_error).__name__ if last_error else "ownership_document_error")


class TrendsProviderAdapter(_BaseAdapter):
    name, kind, ttl_seconds = "google_trends", ProviderKind.TRENDS, 3600

    def fetch(self, security: SecurityIdentity, context: ProviderContext) -> NormalizedData:
        if not self._historical_supported(context):
            return NormalizedData(security.security_id, security.ticker, "trends", {}, self.name, DataStatus.UNAVAILABLE,
                0.0, None, self._now(), None, request_id=context.request_id, error_code="historical_as_of_not_supported")
        from alpha_engine.data.trends_engine import GoogleTrendsEngine
        
        queries_with_weights = [
            {"query": security.ticker, "weight": 0.4},
            {"query": f"{security.ticker} stock", "weight": 0.3},
            {"query": f"{security.ticker} share price", "weight": 0.3}
        ]
        
        result = GoogleTrendsEngine().get_trend_score(security.ticker, security.company_name)
        raw = result.get("status", "FALLBACK")
        status = DataStatus.REAL if raw == "OK" else DataStatus.STALE if raw == "STALE" else DataStatus.FALLBACK
        return NormalizedData(security.security_id, security.ticker, "trends", {"value": result["value"], "query_spec": queries_with_weights},
            result.get("source", self.name), status, result.get("confidence", 0.0), context.as_of, self._now(),
            self._now() + timedelta(seconds=self.ttl_seconds), is_fallback=status == DataStatus.FALLBACK,
            is_stale=status == DataStatus.STALE, request_id=context.request_id,
            error_code=result.get("error_type"), metadata={"query_spec": queries_with_weights})


class UnavailableProvider(_BaseAdapter):
    ttl_seconds = 300
    def __init__(self, kind: ProviderKind):
        self.kind, self.name = kind, f"{kind.value}_unavailable"
    def fetch(self, security, context):
        return NormalizedData(security.security_id if security else None, security.ticker if security else None,
            self.kind.value, {}, self.name, DataStatus.UNAVAILABLE, 0.0, None, self._now(), None,
            request_id=context.request_id, error_code="provider_not_configured")
