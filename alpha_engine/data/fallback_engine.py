import os
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from alpha_engine.input.storage import TickerStorage
from utils.logger import setup_logger

load_dotenv()
logger = setup_logger("FallbackDataEngine")

class MultiApiFallbackEngine:
    """
    Tiered Data API & Dynamic Expansion (SECTION 1, 2, 5, 7)
    - Polygon.io (Primary)
    - Finnhub (Secondary)
    - Alpha Vantage (Tertiary)
    - Yahoo Finance (Last Fallback)
    - Fail-Safe (Neutral Data)
    """
    def __init__(self, storage: Optional[TickerStorage] = None):
        self.storage = storage or TickerStorage()
        self._cache = {} 
        self.cache_ttl = 300 
        from utils.memory_guard import MemoryGuard
        MemoryGuard.register_cache(self._cache)
        
        # API Keys from Environment
        self.polygon_key = os.getenv("POLYGON_API_KEY")
        self.finnhub_key = os.getenv("FINNHUB_API_KEY")
        self.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY")

    def fetch_data_with_fallback(self, ticker: str) -> Dict[str, Any]:
        """Orchestrates tiered data retrieval."""
        if not ticker:
            return self._get_neutral_data("None")

        cached = self._get_from_cache(ticker)
        if cached: return cached

        # Chain: Poly -> Finn -> Alpha -> Yahoo
        data = self._try_polygon(ticker) or \
               self._try_finnhub(ticker) or \
               self._try_alpha_vantage(ticker) or \
               self._try_yahoo(ticker)

        if data:
            return self._save_to_cache(ticker, data)

        logger.warning(f"All APIs failed for {ticker}. Returning neutral.")
        return self._get_neutral_data(ticker)

    def discover_ticker_details(self, ticker: str) -> Optional[Dict]:
        """
        SECTION 1: Dynamic Expansion Logic
        Fetches metadata for a new ticker and saves it to SQLite.
        """
        logger.info(f"Globally discovering metadata for {ticker}...")
        
        # 1. Try Polygon Reference API
        if self.polygon_key:
            # Placeholder for actual: requests.get(f"https://api.polygon.io/v3/reference/tickers/{ticker}...")
            # If successful:
            # metadata = {"ticker": ticker, "company_name": "...", "sector": "...", "aliases": []}
            # self.storage.upsert_ticker(metadata)
            pass

        return None

    def _try_polygon(self, ticker: str) -> Optional[Dict]:
        if not self.polygon_key: return None
        logger.info(f"Polling Polygon.io for {ticker}...")
        return None 

    def _try_finnhub(self, ticker: str) -> Optional[Dict]:
        if not self.finnhub_key: return None
        logger.info(f"Polling Finnhub for {ticker}...")
        return None

    def _try_alpha_vantage(self, ticker: str) -> Optional[Dict]:
        if not self.alpha_vantage_key: return None
        logger.info(f"Polling Alpha Vantage for {ticker}...")
        return None

    def _try_yahoo(self, ticker: str) -> Optional[Dict]:
        logger.info(f"Polling Yahoo Finance (Fallback) for {ticker}...")
        # This module is retained for legacy demonstrations only.  It must
        # never masquerade as an observed Yahoo quote.
        return {"source": "Yahoo_SIMULATED", "price": 100.0, "status": "MOCK", "is_synthetic": True}

    def _get_neutral_data(self, ticker: str) -> Dict:
        return {
            "ticker": ticker,
            "source": "FAIL-SAFE",
            "sentiment": 0.0,
            "buzz": 0.0,
            "trends": 50.0,
            "insider": 0.0,
            "macro": 0.0,
            "status": "MOCK",
            "is_synthetic": True,
        }

    def _get_from_cache(self, ticker: str) -> Optional[Dict]:
        if ticker in self._cache:
            entry = self._cache[ticker]
            if time.time() - entry["timestamp"] < self.cache_ttl:
                return entry["data"]
        return None

    def _save_to_cache(self, ticker: str, data: Dict) -> Dict:
        self._cache[ticker] = {"data": data, "timestamp": time.time()}
        return data
