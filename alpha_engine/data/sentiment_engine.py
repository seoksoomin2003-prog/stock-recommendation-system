import json
import numpy as np
from typing import Dict, List, Optional
try:
    from core.rag_engine import RAGEngine
except ImportError:
    RAGEngine = None
from utils.logger import setup_logger

logger = setup_logger("SentimentEngine")

class LLMSentimentEngine:
    """
    Contextual Sentiment Engine (Ollama-based)
    - Keyword matching strictly forbidden.
    - Utilizes context-aware NLP to interpret market events.
    - RAG-enabled for grounding.
    """
    def __init__(self, rag_engine: Optional[RAGEngine] = None):
        try:
            self.rag = rag_engine or RAGEngine()
            self.llm = getattr(self.rag, 'llm', None)
        except Exception as e:
            logger.warning(f"RAG/LLM Initialization failed: {e}. Falling back to passive sentiment.")
            self.rag = None
            self.llm = None

    def analyze_sentiment(self, ticker: str, text_data: List[str], context_query: str = "", company_name: str = "") -> Dict:
        """
        Analyze sentiment for a list of news headlines or social mentions (Delegated to Provider Factory).
        """
        from core.providers import ProviderFactory
        return ProviderFactory.get_sentiment_provider(self.llm).analyze_sentiment(
            ticker, text_data, context_query, company_name
        )

    def get_batch_sentiment(self, ticker: str, text_data: List[str]) -> Dict:
        """
        High-level wrapper for the alpha engine.
        """
        return self.analyze_sentiment(ticker, text_data)
