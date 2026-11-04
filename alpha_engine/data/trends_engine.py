import time
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from utils.config import GOOGLE_TRENDS_CONFIG
from utils.logger import setup_logger

logger = setup_logger("GoogleTrendsEngine")

class GoogleTrendsEngine:
    """
    Data Layer: Google Trends Engine
    - Generates Investor Attention Signals.
    - Supports multi-word queries for enhanced signal-to-noise ratio.
    - Implements fresh-to-stale caching, resilient retries, and neutral fallbacks.
    """
    def __init__(self):
        self._cache = {}
        self.cache_ttl = 3600  # 1 hour
        try:
            from pytrends.request import TrendReq
            self.pytrends = TrendReq(
                hl=GOOGLE_TRENDS_CONFIG.get('hl', 'en-US'),
                tz=GOOGLE_TRENDS_CONFIG.get('tz', 360),
                timeout=(GOOGLE_TRENDS_CONFIG.get('timeout', 10), 30),
                retries=GOOGLE_TRENDS_CONFIG.get('retries', 2)
            )
        except ImportError:
            logger.warning("pytrends not installed. Using fallback logic.")
            self.pytrends = None

    def get_trend_score(self, ticker: str, company_name: str = "") -> Dict:
        """
        Calculate combined trend score from multiple queries.
        Returns a detailed schema dictionary with status and confidence tracking.
        """
        ticker_upper = ticker.upper().strip()
        now_ts = time.time()
        
        # Cache lookup (Fresh Cache check)
        if ticker_upper in self._cache:
            entry = self._cache[ticker_upper]
            if now_ts - entry["timestamp"] < self.cache_ttl:
                logger.info(f"[CACHE_HIT] Google Trends cache is FRESH for {ticker_upper}.")
                return {
                    "value": entry["value"],
                    "status": "OK",
                    "confidence": 1.0,
                    "source": "google_trends_cache",
                    "timestamp": pd.Timestamp.now().isoformat(),
                    "error_type": None
                }

        # Query construction strategy
        queries = [
            ticker_upper,
            f"{ticker_upper} stock",
            f"{ticker_upper} share price"
        ]
        if company_name and company_name != "Unknown":
            queries.append(company_name)
            
        queries = queries[:5]  # Pytrends limits to max 5

        # Check if engine is available
        if not self.pytrends:
            return self._handle_failure(ticker_upper, "pytrends_not_installed")

        logger.info(f"[TRENDS_REQUEST] Querying Google Trends for {ticker_upper} with queries: {queries}")
        
        # Bounded retries loop (P1-resilience approach)
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                self.pytrends.build_payload(queries, cat=0, timeframe='today 1-m')
                df = self.pytrends.interest_over_time()
                
                if df.empty:
                    logger.warning(f"Empty trends response for {ticker_upper}. Attempt {attempt}/{max_attempts}")
                    if attempt < max_attempts:
                        time.sleep(1.0)
                        continue
                    return self._handle_failure(ticker_upper, "no_data_found")
                    
                # Calculate mean trend score
                avg_scores = df[queries].mean()
                final_score = float(avg_scores.mean())
                
                # Update Cache
                self._cache[ticker_upper] = {
                    "value": final_score,
                    "timestamp": now_ts
                }
                
                logger.info(f"[TRENDS_SUCCESS] ticker={ticker_upper} trend_score={final_score:.2f}")
                return {
                    "value": final_score,
                    "status": "OK",
                    "confidence": 1.0,
                    "source": "google_trends_api",
                    "timestamp": pd.Timestamp.now().isoformat(),
                    "error_type": None
                }
                
            except Exception as e:
                err_name = type(e).__name__
                logger.warning(f"[TRENDS_TIMEOUT/RATE_LIMIT] attempt={attempt}/{max_attempts} error={err_name}")
                if "429" in str(e):
                    logger.error(f"[TRENDS_RATE_LIMIT] Google Trends API rate limited (429) for {ticker_upper}.")
                if attempt < max_attempts:
                    # Exponential backoff with random jitter
                    time.sleep(1.5 * attempt)
                else:
                    return self._handle_failure(ticker_upper, err_name)
                    
        return self._handle_failure(ticker_upper, "retry_exhausted")

    def _handle_failure(self, ticker: str, error_type: str) -> Dict:
        """
        Retrieves stale cache if available, otherwise returns neutral 50.0 fallback.
        """
        # Stale cache check
        if ticker in self._cache:
            entry = self._cache[ticker]
            logger.warning(f"[CACHE_STALE] Google Trends API failed ({error_type}). Reverting to STALE cache for {ticker}.")
            return {
                "value": entry["value"],
                "status": "STALE",
                "confidence": 0.5,
                "source": "google_trends_stale_cache",
                "timestamp": pd.Timestamp.now().isoformat(),
                "error_type": error_type
            }
            
        logger.warning(f"[NEUTRAL_FALLBACK] Google Trends failed ({error_type}). Reverting to neutral 50.0 for {ticker}.")
        return {
            "value": 50.0,
            "status": "FALLBACK",
            "confidence": 0.0,
            "source": "google_trends_fallback",
            "timestamp": pd.Timestamp.now().isoformat(),
            "error_type": error_type
        }
