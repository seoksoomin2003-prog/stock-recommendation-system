import os
import re
import json
import numpy as np
import requests
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any, Union
from utils.config import APP_MODE, OLLAMA_URL, OLLAMA_MODEL, FUNDAMENTAL_ANALYSIS_CONFIG, MAX_CONCURRENT_LLM_REQUESTS
from utils.logger import setup_logger

logger = setup_logger("ProviderFactory")

# =====================================================================
# 1. INTERFACES (ABSTRACTIONS)
# =====================================================================

class SentimentProvider(ABC):
    @abstractmethod
    def analyze_sentiment(self, ticker: str, text_data: List[str], context_query: str = "", company_name: str = "") -> Dict[str, Any]:
        pass

class FundamentalProvider(ABC):
    @abstractmethod
    def query_fundamental(self, prompt: str, required_keys: List[str]) -> Dict[str, Any]:
        pass

class AliasGenerationProvider(ABC):
    @abstractmethod
    def extract_ner_candidates(self, text: str) -> List[str]:
        pass

    @abstractmethod
    def get_semantic_similarity(self, alias: str, company_name: str, score_hint: float) -> float:
        pass

    @abstractmethod
    def run_llm_noise_filter(self, alias: str, context: str, ticker: str, company_name: str) -> str:
        pass


# =====================================================================
# 2. LOCAL PROVIDERS (Deterministic, Offline, Zero-Ollama, Zero-HuggingFace)
# =====================================================================

class LocalSentimentProvider(SentimentProvider):
    """
    Apple M2 8GB safe keyword-based local sentiment analyzer.
    No Ollama model loading, zero network latency.
    """
    def __init__(self):
        self.pos_words = {"buy", "bullish", "growth", "record", "profit", "gain", "upgrade", "positive", "strong", "beat", "surge", "up"}
        self.neg_words = {"sell", "bearish", "loss", "drop", "lawsuit", "layoff", "negative", "weak", "miss", "concern", "crash", "down"}

    def analyze_sentiment(self, ticker: str, text_data: List[str], context_query: str = "", company_name: str = "") -> Dict[str, Any]:
        if not text_data:
            return {"sentiment": 0.0, "confidence": 0.5, "event_type": "Neutral (No Data)", "mode": "local"}

        combined = " ".join(text_data).lower()
        score = 0.0
        hits = 0
        for w in self.pos_words:
            if w in combined:
                score += 0.5
                hits += 1
        for w in self.neg_words:
            if w in combined:
                score -= 0.5
                hits += 1

        final_score = np.clip(score / max(1, hits), -1.0, 1.0)
        confidence = min(0.5 + 0.1 * hits, 0.9)
        
        # Simple heuristic to determine event type
        event = "General"
        if "earning" in combined or "quarter" in combined:
            event = "Earnings"
        elif "m&a" in combined or "merger" in combined or "acquire" in combined:
            event = "M&A"
        elif "lawsuit" in combined or "regulation" in combined or "sec" in combined:
            event = "Regulatory"

        return {
            "sentiment": float(final_score),
            "confidence": float(confidence),
            "event_type": event,
            "mode": "local"
        }

class LocalFundamentalProvider(FundamentalProvider):
    """
    Ollama-free deterministic Local Fundamental Analyser.
    Matches the schema requirements without query overhead.
    """
    def query_fundamental(self, prompt: str, required_keys: List[str]) -> Dict[str, Any]:
        # Generate stable, structured mockup outputs matching the metric requested in the prompt
        result = {
            "confidence": 0.8,
            "reason": "Local mode validation fallback metrics.",
            "mode": "local"
        }
        
        prompt_lower = prompt.lower()
        if "cashflow" in prompt_lower or "cash flow" in prompt_lower:
            result["quality"] = "STABLE"
        elif "resilience" in prompt_lower or "earnings" in prompt_lower:
            result["resilience"] = "STABLE"
        elif "sustainability" in prompt_lower or "moat" in prompt_lower:
            result["sustainability"] = "STABLE"
        elif "debt" in prompt_lower or "borrowing" in prompt_lower:
            result["debt_type"] = "GOOD"
        else:
            result["quality"] = "NEUTRAL"
            result["resilience"] = "NEUTRAL"
            result["sustainability"] = "NEUTRAL"
            result["debt_type"] = "NEUTRAL"

        return result

class LocalAliasGenerationProvider(AliasGenerationProvider):
    """
    spaCy & SentenceTransformer free Local Alias Generator.
    Uses regex NER and Jaccard-like fuzzy token extraction.
    """
    def extract_ner_candidates(self, text: str) -> List[str]:
        # Simple regex noun-like words extractor
        words = re.findall(r'\b[A-Z][a-zA-Z]{3,}\b', text)
        return list(set(words))

    def get_semantic_similarity(self, alias: str, company_name: str, score_hint: float) -> float:
        # Fallback to Jaccard similarity over characters/words
        a_set = set(alias.lower().split())
        c_set = set(company_name.lower().split())
        intersection = a_set.intersection(c_set)
        union = a_set.union(c_set)
        similarity = len(intersection) / len(union) if union else 0.5
        return float(similarity)

    def run_llm_noise_filter(self, alias: str, context: str, ticker: str, company_name: str) -> str:
        # Rule-based filter
        a_clean = alias.lower()
        c_clean = company_name.lower()
        if a_clean in c_clean or ticker.lower() in a_clean:
            return "YES"
        return "UNCERTAIN"


# =====================================================================
# 3. PRODUCTION PROVIDERS (Full Ollama, RAG, spaCy, and Embeddings)
# =====================================================================

class ProductionSentimentProvider(SentimentProvider):
    """
    Production-grade LLM-based Sentiment Provider.
    Queries the live Ollama service.
    """
    def __init__(self, llm_instance: Any):
        self.llm = llm_instance

    def analyze_sentiment(self, ticker: str, text_data: List[str], context_query: str = "", company_name: str = "") -> Dict[str, Any]:
        if not text_data or not self.llm:
            return {"sentiment": 0.0, "confidence": 0.0, "event_type": "Neutral (No Model)", "mode": "production"}

        combined_text = "\n".join(text_data[:10])
        
        prompt = f"""
[Role] Institutional Quant Analyst
[Task] Analyze market sentiment and event type for {company_name} ({ticker}) based on the input text.

[Rules]
1. Ignore keywords. Analyze the semantic meaning and context.
2. Output MUST be VALID JSON.
3. Scale: Sentiment [-1.0 (Very Bearish) to 1.0 (Very Bullish)].
4. Confidence: [0.0 to 1.0].

[Input Text]
{combined_text}

[Required JSON Format]
{{
    "sentiment": float,
    "confidence": float,
    "event_type": "string (e.g., Earnings, M&A, Regulatory, Product, Macro)"
}}
"""
        try:
            response = self.llm.invoke(prompt)
            # Extracted parser helper invocation
            result = self._parse_json(response)
            
            return {
                "sentiment": max(-1.0, min(1.0, float(result.get("sentiment", 0.0)))),
                "confidence": max(0.0, min(1.0, float(result.get("confidence", 0.5)))),
                "event_type": result.get("event_type", "General"),
                "mode": "production"
            }
        except Exception as e:
            logger.error(f"Production sentiment failed: {e}")
            return {"sentiment": 0.0, "confidence": 0.0, "event_type": "Error", "mode": "production"}

    def _parse_json(self, text: str) -> Dict[str, Any]:
        try:
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except:
            return {}

class ProductionFundamentalProvider(FundamentalProvider):
    """
    Production-grade LLM-based Fundamental Provider.
    """
    def __init__(self):
        self.api_url = OLLAMA_URL

    def query_fundamental(self, prompt: str, required_keys: List[str]) -> Dict[str, Any]:
        # Perform live Ollama POST request with resilience wrappers
        from core.llm_validation_layer import LLMValidationLayer
        from utils.memory_guard import MemoryGuard
        
        if not MemoryGuard.allow("llm"):
            logger.warning("[MEMORY_GUARD] LLM fundamental query blocked due to memory pressure.")
            return LLMValidationLayer.get_safe_default()

        from utils.resilience import resilient_request
        from utils.config import API_CONNECT_TIMEOUT, API_READ_TIMEOUT

        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 500
            }
        }
        
        def run_post():
            return requests.post(self.api_url, json=payload, timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT))
            
        response = resilient_request(
            run_post,
            provider="ProductionFundamentalProvider",
            fallback_value=None
        )
        
        if response is None:
            return LLMValidationLayer.get_safe_default()
            
        try:
            response.raise_for_status()
            result = response.json()
            raw_content = result.get("response", "{}")
            
            parsed = LLMValidationLayer.sanitize_and_parse(raw_content, required_keys=required_keys)
            parsed["mode"] = "production"
            return parsed
        except Exception as e:
            logger.error(f"Production fundamental query failed: {e}")
            return LLMValidationLayer.get_safe_default()

class ProductionAliasGenerationProvider(AliasGenerationProvider):
    """
    Production-grade spaCy + SentenceTransformer Alias Generator.
    Loads models lazily, caches instances, and enforces local_files_only in local mode.
    """
    def __init__(self):
        self._nlp = None
        self._fast_embedder = None

    def _get_nlp(self):
        if self._nlp is None:
            try:
                import spacy
                self._nlp = spacy.load("en_core_web_sm")
            except Exception as e:
                logger.error(f"Production NLP load failed: {e}")
                self._nlp = "FAILED"
        return self._nlp if self._nlp != "FAILED" else None

    def _get_fast_embedder(self):
        if self._fast_embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                import utils.config
                local_only = (utils.config.APP_MODE == "local")
                self._fast_embedder = SentenceTransformer('all-MiniLM-L6-v2', local_files_only=local_only)
            except Exception as e:
                logger.error(f"Production SentenceTransformer load failed (local_only={utils.config.APP_MODE == 'local'}): {e}")
                self._fast_embedder = "FAILED"
        return self._fast_embedder if self._fast_embedder != "FAILED" else None

    def extract_ner_candidates(self, text: str) -> List[str]:
        nlp = self._get_nlp()
        if not nlp:
            return []
        doc = nlp(text)
        candidates = []
        for ent in doc.ents:
            if ent.label_ in ["ORG", "PRODUCT", "WORK_OF_ART"]:
                candidates.append(ent.text.lower())
        # Rule-based fallback: Capitalized words (Proper Nouns)
        for token in doc:
            if token.is_alpha and token.is_title and not token.is_stop:
                candidates.append(token.text.lower())
        return list(set(candidates))

    def get_semantic_similarity(self, alias: str, company_name: str, score_hint: float) -> float:
        from utils.memory_guard import MemoryGuard
        if not MemoryGuard.allow("embedding"):
            logger.warning("[MEMORY_GUARD] Embedding similarity blocked due to memory pressure. Reverting to Jaccard.")
            w1 = set(alias.lower().split())
            w2 = set(company_name.lower().split())
            sim = len(w1 & w2) / len(w1 | w2) if (w1 | w2) else 0.5
            return float(sim)

        fast_embedder = self._get_fast_embedder()
        if not fast_embedder:
            logger.warning("Fast embedder not available. Returning fallback semantic similarity.")
            return 0.5
        from sentence_transformers import util
        emb1 = fast_embedder.encode(alias)
        emb2 = fast_embedder.encode(company_name)
        sim = util.cos_sim(emb1, emb2).item()
        
        # Production hybrid domain overlap simulator boost
        if 0.5 <= score_hint <= 0.75:
            sim = 0.8 * sim + 0.2 * sim
        return max(0.0, float(sim))

    def run_llm_noise_filter(self, alias: str, context: str, ticker: str, company_name: str) -> str:
        # Real production Ollama classifier validation
        from utils.memory_guard import MemoryGuard
        if not MemoryGuard.allow("llm"):
            logger.warning("[MEMORY_GUARD] LLM noise filter blocked due to memory pressure.")
            return "UNCERTAIN"

        from utils.resilience import resilient_request
        from utils.config import API_CONNECT_TIMEOUT, API_READ_TIMEOUT
        
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": f"Is the following 'alias' referring to the company '{company_name}' (ticker: {ticker}) based on context?\nAlias: {alias}\nContext: {context[:300]}\nAnswer strictly: YES / NO / UNCERTAIN",
            "stream": False,
            "options": {"temperature": 0.0}
        }
        
        def run_post():
            return requests.post(OLLAMA_URL, json=payload, timeout=(API_CONNECT_TIMEOUT, API_READ_TIMEOUT))
            
        response = resilient_request(
            run_post,
            provider="ProductionAliasNoiseFilter",
            fallback_value=None
        )
        
        if response is None:
            return "UNCERTAIN"
            
        try:
            response.raise_for_status()
            res_text = response.json().get("response", "").strip().upper()
            if "YES" in res_text: return "YES"
            if "NO" in res_text: return "NO"
            return "UNCERTAIN"
        except Exception as e:
            logger.error(f"Production LLM noise filter query processing failed: {e}")
            return "UNCERTAIN"


# =====================================================================
# 4. PROVIDER FACTORY (APP_MODE Controlled Manager)
# =====================================================================

class ProviderFactory:
    """
    Central Factory controlling provider resolution based on configuration APP_MODE.
    """
    _sentiment_provider: Optional[SentimentProvider] = None
    _fundamental_provider: Optional[FundamentalProvider] = None
    _alias_provider: Optional[AliasGenerationProvider] = None

    @classmethod
    def get_sentiment_provider(cls, llm_instance: Any = None) -> SentimentProvider:
        import utils.config
        if cls._sentiment_provider is None:
            if utils.config.APP_MODE == "production":
                logger.info("Initializing ProductionSentimentProvider")
                cls._sentiment_provider = ProductionSentimentProvider(llm_instance)
            else:
                logger.info("Initializing LocalSentimentProvider")
                cls._sentiment_provider = LocalSentimentProvider()
        return cls._sentiment_provider

    @classmethod
    def get_fundamental_provider(cls) -> FundamentalProvider:
        import utils.config
        if cls._fundamental_provider is None:
            if utils.config.APP_MODE == "production":
                logger.info("Initializing ProductionFundamentalProvider")
                cls._fundamental_provider = ProductionFundamentalProvider()
            else:
                logger.info("Initializing LocalFundamentalProvider")
                cls._fundamental_provider = LocalFundamentalProvider()
        return cls._fundamental_provider

    @classmethod
    def get_alias_provider(cls) -> AliasGenerationProvider:
        import utils.config
        if cls._alias_provider is None:
            if utils.config.APP_MODE == "production":
                logger.info("Initializing ProductionAliasGenerationProvider")
                cls._alias_provider = ProductionAliasGenerationProvider()
            else:
                logger.info("Initializing LocalAliasGenerationProvider")
                cls._alias_provider = LocalAliasGenerationProvider()
        return cls._alias_provider

    @classmethod
    def reset_providers(cls):
        """Helper to reset provider state during unit tests."""
        cls._sentiment_provider = None
        cls._fundamental_provider = None
        cls._alias_provider = None
