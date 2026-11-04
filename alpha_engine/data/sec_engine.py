import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
from .sec.base import SECDataProvider
from .sec.sec_api_provider import SecApiProvider
from .sentiment_engine import LLMSentimentEngine
from utils.logger import setup_logger

logger = setup_logger("SECInsiderEngine")

class SECInsiderEngine:
    """
    Data Layer: SEC / Insider Engine
    - Generates Fundamental Alpha Signals.
    - Uses SECDataProvider to fetch raw data.
    - Uses LLMSentimentEngine for contextual filing interpretation.
    - Implements look-ahead filters, User-Agent identification, and neutral fallbacks.
    """
    def __init__(self, provider: Optional[SECDataProvider] = None, sentiment_engine: Optional[LLMSentimentEngine] = None):
        self.provider = provider or SecApiProvider()
        self.sentiment_engine = sentiment_engine or LLMSentimentEngine()

    def get_alpha_signals(self, ticker: str, evaluation_time: Optional[float] = None) -> Dict[str, Any]:
        """
        Calculates insider_score and filing_sentiment ∈ [-1, 1].
        """
        ticker_upper = ticker.upper().strip()
        
        # Look-ahead prevention
        eval_date_str = None
        if evaluation_time is not None:
            eval_date_str = pd.Timestamp(evaluation_time, unit='s').strftime('%Y-%m-%d')

        try:
            # 1. Filing Sentiment (Contextual analysis of 10-K/Q)
            filings = self.provider.fetch_filings(ticker_upper, filing_type="10-K", limit=10)
            
            # Apply look-ahead date filter
            if eval_date_str:
                filings = [f for f in filings if f.get('date', '1900-01-01') <= eval_date_str]
                
            filing_sentiment = 0.0
            if filings:
                content = self.provider.get_filing_content(filings[0]['url'])
                res = self.sentiment_engine.analyze_sentiment(ticker_upper, [content], context_query="Key risks and financial outlook")
                filing_sentiment = res.get("sentiment", 0.0)

            # 2. Insider Score (Form 4 analysis)
            trades = self.provider.fetch_insider_trades(ticker_upper)
            if eval_date_str:
                trades = [t for t in trades if t.get('date', '1900-01-01') <= eval_date_str]
                
            insider_score = self._calculate_insider_score(trades)

            # Fetch metadata from provider
            status = getattr(self.provider, "last_status", {}).get(ticker_upper, "OK")
            source = getattr(self.provider, "last_source", {}).get(ticker_upper, "sec_api")
            confidence = getattr(self.provider, "last_confidence", {}).get(ticker_upper, 1.0)

            if status == "FALLBACK":
                insider_score = 0.0
                
            logger.info(f"[{ticker_upper}] SEC Alpha: Insider={insider_score:+.2f}, FilingSent={filing_sentiment:+.2f} | Status={status}")

            return {
                "insider_score": insider_score,
                "filing_sentiment": filing_sentiment,
                "status": status,
                "confidence": confidence,
                "source": source
            }
        except Exception as e:
            logger.error(f"SEC Engine failure for {ticker_upper}: {e}")
            return {
                "insider_score": 0.0,
                "filing_sentiment": 0.0,
                "status": "FALLBACK",
                "confidence": 0.0,
                "source": "sec_engine_error"
            }

    def _calculate_insider_score(self, trades: List[Dict]) -> float:
        """
        Quantifies Form 4 transaction data into a normalized score.
        """
        if not trades:
            return 0.0
        
        net_value = 0
        for t in trades:
            factor = 1.0 if t['transaction'].lower() == 'buy' else -1.0
            net_value += factor * t['amount']
        
        # Normalize net value relative to a baseline institutional trade size
        # Clip to [-1, 1]
        score = net_value / 100000.0 
        return max(-1.0, min(1.0, score))
