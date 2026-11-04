import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils import config as cfg
from utils.logger import setup_logger

logger = setup_logger("UniverseProvider")

SEC_TICKER_MAP_CACHE = "data/sec_cache/company_tickers.json"


class SecTickerMap:
    """SEC ``company_tickers.json`` (ticker -> CIK) with an explicit cached fallback.

    Provenance is reported in ``self.provenance``: ``REAL`` when fetched now,
    ``CACHED`` (with age) when the local copy had to be used, ``UNAVAILABLE``
    when neither exists.  CIK assignments are stable identifiers, so a cached
    map is safe for CIK resolution; its age is always disclosed.
    """

    URL = "https://www.sec.gov/files/company_tickers.json"

    def __init__(self, cache_file: str = SEC_TICKER_MAP_CACHE):
        self.cache_file = cache_file
        self.mapping: Dict[str, Dict[str, Any]] = {}
        self.provenance: Dict[str, Any] = {"status": "NOT_LOADED"}

    def load(self) -> "SecTickerMap":
        if self.mapping:
            return self
        raw = None
        from utils import runtime_config
        try:
            if not runtime_config.sec_configured():
                # P6-19: no SEC request without a real fair-access contact; use the disclosed cache.
                raise PermissionError("SEC_USER_AGENT_NOT_CONFIGURED")
            import requests
            resp = requests.get(self.URL, headers={"User-Agent": cfg.SEC_USER_AGENT}, timeout=15)
            if resp.status_code == 200:
                raw = resp.json()
                self.provenance = {"status": "REAL", "source": "SEC_COMPANY_TICKERS",
                                   "retrieved_at": datetime.now(timezone.utc).isoformat()}
                try:
                    os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
                    with open(self.cache_file, "w") as fh:
                        json.dump(raw, fh)
                except Exception as exc:
                    logger.warning(f"Could not refresh SEC ticker cache: {exc}")
            else:
                logger.warning(f"SEC company_tickers.json returned HTTP {resp.status_code}; "
                               "set SEC_USER_AGENT to '<app> <contact email>' per SEC fair-access policy.")
                self.provenance = {"status": "FAILED", "http_status": resp.status_code}
        except PermissionError as exc:
            self.provenance = {"status": "NOT_QUERIED", "reason": str(exc)}
        except Exception as exc:
            logger.error(f"Failed to fetch SEC CIK mapping: {exc}")
            self.provenance = {"status": "FAILED", "error": type(exc).__name__}
        if raw is None and os.path.exists(self.cache_file):
            try:
                with open(self.cache_file) as fh:
                    raw = json.load(fh)
                mtime = datetime.fromtimestamp(os.path.getmtime(self.cache_file), timezone.utc)
                self.provenance = {"status": "CACHED", "source": "SEC_COMPANY_TICKERS_LOCAL_CACHE",
                                   "cache_file": self.cache_file, "cache_written_at": mtime.isoformat(),
                                   "age_days": (datetime.now(timezone.utc) - mtime).days,
                                   "live_fetch": self.provenance}
            except Exception:
                raw = None
        if raw is None:
            self.provenance = {"status": "UNAVAILABLE", "live_fetch": self.provenance}
            return self
        for item in raw.values():
            ticker = str(item.get("ticker", "")).upper().replace(".", "-")
            if ticker and ticker not in self.mapping:
                self.mapping[ticker] = {"cik": str(item["cik_str"]), "title": item.get("title")}
        return self

    def cik(self, ticker: str) -> Optional[str]:
        entry = self.load().mapping.get(ticker.upper())
        return entry["cik"] if entry else None

    def title(self, ticker: str) -> Optional[str]:
        entry = self.load().mapping.get(ticker.upper())
        return entry["title"] if entry else None


class WikipediaSP500BootstrapProvider:
    """
    ZERO-COST BOOTSTRAP UNIVERSE PROVIDER.
    Fetches the S&P 500 constituent list from Wikipedia and maps SEC CIKs.
    This is NOT a historical security master. It only serves as a current tradability baseline.
    """
    def __init__(self, cache_file: str = "data/sp500_universe_cache.json", max_age_days: int = 7,
                 ticker_map: Optional[SecTickerMap] = None):
        self.cache_file = cache_file
        self.max_age_days = max_age_days
        self.ticker_map = ticker_map or SecTickerMap()
        os.makedirs(os.path.dirname(self.cache_file) or ".", exist_ok=True)

    def _fetch_ciks(self, tickers: List[str]) -> Dict[str, str]:
        """Map CIKs through SEC company_tickers.json (live, else disclosed local cache)."""
        self.ticker_map.load()
        return {t: self.ticker_map.mapping[t]["cik"] for t in tickers if t in self.ticker_map.mapping}

    def _fetch_from_wikipedia(self) -> Dict[str, Any]:
        try:
            import requests
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            from utils import runtime_config
            headers = {"User-Agent": runtime_config.http_user_agent()}
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table', {'id': 'constituents'})
            if not table:
                raise ValueError("No constituents table found on Wikipedia page.")

            tickers, constituents = [], {}
            for row in table.find_all('tr')[1:]:  # Skip header
                cols = row.find_all('td')
                if cols:
                    ticker = cols[0].text.strip().replace('.', '-')
                    tickers.append(ticker)
                    constituents[ticker] = {
                        "name": cols[1].text.strip() if len(cols) > 1 else None,
                        "gics_sector": cols[2].text.strip() if len(cols) > 2 else None,
                    }

            if len(tickers) < 450:
                raise ValueError(f"Extracted unusually low number of constituents: {len(tickers)}")

            return {
                "status": "SUCCESS",
                "freshness_status": "REAL",
                "provider_role": "BOOTSTRAP_UNIVERSE",
                "source": "WIKIPEDIA_SP500",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "constituent_count": len(tickers),
                "tickers": tickers,
                "constituents": constituents,
            }
        except Exception as e:
            logger.error(f"[API_FAILURE] provider=WikipediaSP500BootstrapProvider error={type(e).__name__} details={str(e)}")
            return {"status": "FAILED", "reason": f"{type(e).__name__}: {e}"}

    def get_live_universe(self) -> Dict[str, Any]:
        """
        Attempts to fetch the universe. Returns dict with status, provenance, and tickers.
        """
        result = self._fetch_from_wikipedia()
        if result["status"] == "SUCCESS":
            result["ciks"] = self._fetch_ciks(result["tickers"])
            result["cik_map_provenance"] = dict(self.ticker_map.provenance)
            self._save_cache(result)
            return result

        # Fallback to cache if Wikipedia fails
        logger.warning("Wikipedia fetch failed. Attempting to load universe from cache...")
        cache = self._load_cache()
        if cache:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cache["retrieved_at"])).days
            cache["cache_age_days"] = age
            if age > self.max_age_days:
                cache["status"] = "STALE"
                cache["freshness_status"] = "STALE"
                cache["reason"] = f"Wikipedia unavailable and cached universe is {age} days old (max {self.max_age_days})."
                logger.warning(f"Cached universe is {age} days old (Max {self.max_age_days}). Marked as STALE.")
            else:
                cache["status"] = "SUCCESS_FROM_CACHE"
                cache["freshness_status"] = "REAL"
            return cache

        return {
            "status": "UNAVAILABLE",
            "freshness_status": "UNAVAILABLE",
            "provider_role": "BOOTSTRAP_UNIVERSE",
            "tickers": [],
            "ciks": {},
            "reason": "Wikipedia failed and no valid cache exists."
        }

    def _save_cache(self, data: Dict[str, Any]):
        try:
            tmp = f"{self.cache_file}.tmp"
            with open(tmp, "w") as f:
                json.dump(data, f)
            os.replace(tmp, self.cache_file)
        except Exception as e:
            logger.error(f"Failed to save universe cache: {e}")

    def _load_cache(self) -> Dict[str, Any]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    return json.load(f)
            except Exception:
                return None
        return None
