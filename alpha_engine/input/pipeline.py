import re
import math
import numpy as np
from typing import List, Dict, Set, Tuple
from .storage import TickerStorage
from alpha_engine.data.social.social_engines import InstitutionalSocialEngine
from alpha_engine.data.sec.sec_api_provider import SecApiProvider
try:
    from core.rag_engine import RAGEngine
except ImportError:
    RAGEngine = None
from utils.logger import setup_logger

# Professional NER and Embedding Libraries
try:
    import spacy
except ImportError:
    spacy = None

try:
    from sentence_transformers import SentenceTransformer, util
except ImportError:
    SentenceTransformer = None
    util = None

logger = setup_logger("AliasGenerationPipeline")

class AliasGenerationPipeline:
    """
    SECTION 2-5: Institutional Alias Generation Pipeline
    - Stage 1: High Recall extraction (SEC/News).
    - Stage 2: Precision filtering with 6-factor hybrid scoring.
    - LLM Noise Filter classifier.
    """
    def __init__(self, storage: TickerStorage):
        self.storage = storage
        self.social_engine = InstitutionalSocialEngine()
        self.sec_provider = SecApiProvider()
        
        # Delegated to providers to support local M2 Mac without auto-loading heavy models.
        self.nlp = None
        self.fast_embedder = None
            
        # Optional: Specialized Financial Embedder (Slow Path)
        self.financial_embedder = None # Load on-demand only for score threshold hits
        
        # RAG Engine for baseline semantic grounded embeddings
        self.rag = RAGEngine() if RAGEngine else None

    def generate_aliases(self, ticker: str, company_name: str, context_text: str = ""):
        """Orchestrates decomposition and extraction with context awareness."""
        logger.info(f"Triggering institutional alias pipeline for {company_name} ({ticker})")
        
        ticker_id = self.storage.add_ticker(ticker, company_name)
        
        # 1. Extraction (High Recall)
        raw_candidates = self._fetch_all_candidates(ticker, company_name, context_text)
        
        # 2. Precision Filtering Loop
        final_aliases = []
        for alias, source, context in raw_candidates:
            # Step A: System-calculated Confidence
            score = self._calculate_confidence(alias, context, ticker, company_name, source)
            
            # Step B: LLM Semantic Validation (Noise Filter)
            if score >= 0.5:
                validation = self._run_llm_noise_filter(alias, context, ticker, company_name)
                
                # Filter Logic (SECTION 6)
                if validation == "NO":
                    continue
                if validation == "UNCERTAIN" and score < 0.75:
                    continue
                
                # Step C: Tiered Persistence
                alias_id = self.storage.add_alias(ticker_id, alias, source, score)
                
                # SECTION 5: Primary Tier Only Token Indexing
                if score >= 0.8:
                    self._index_alias_tokens(alias_id, alias)
                    
                logger.debug(f"Verified Alias: {alias} (Score: {score:.2f}, Logic: {validation})")

    def _fetch_all_candidates(self, ticker: str, company_name: str, doc_text: str) -> List[Tuple]:
        """Stage 1: Multi-source recall extraction."""
        candidates = []
        
        # Manual/Decomposition
        candidates.append((ticker.lower(), "manual", f"Ticker: {ticker}"))
        candidates.append((company_name.lower(), "manual", f"Company: {company_name}"))
        
        # News Mentions (API)
        api_mentions = self.social_engine.fetch_mentions(company_name)
        # Combined mentions: API results + provided document text
        all_mentions = api_mentions + ([doc_text] if doc_text else [])
        
        from core.providers import ProviderFactory
        alias_provider = ProviderFactory.get_alias_provider()
        
        for m in all_mentions:
            # NER extraction
            ner_candidates = alias_provider.extract_ner_candidates(m)
            for c in ner_candidates:
                candidates.append((c, "news", m))
                        
        # SEC Filings
        filings = self.sec_provider.fetch_filings(ticker)
        for f in filings:
            content = self.sec_provider.get_filing_content(f['url'])
            # Pattern extraction for acronyms
            matches = re.findall(r'\(([A-Z]+)\)', content)
            for m in matches:
                candidates.append((m.lower(), "sec", content[:500])) # Context sample

        return candidates

    def _calculate_confidence(self, alias: str, context: str, ticker: str, company_name: str, source: str) -> float:
        """
        PRODUCTION-GRADE CONFIDENCE SCORING FORMULA
        weighted_sum(type, freq, prox, pattern, semantic, source)
        """
        # 1. Entity Type Score (0.30)
        type_score = self._get_entity_type_score(alias)
        
        # 2. Frequency Score (0.20)
        freq_score = self._get_frequency_score(alias, context)
        
        # 3. Proximity Score (0.20) - Min Distance
        prox_score = self._get_proximity_score(alias, context, ticker, company_name)
        
        # 4. Pattern Score (0.15)
        pattern_score = self._get_pattern_score(alias)
        
        # 5. Semantic Similarity (0.10) - Hybrid Strategy
        semantic_score = self._get_semantic_similarity(alias, company_name, score_hint=0.5)
        
        # 6. Source Reliability (0.05)
        source_map = {"sec": 1.0, "news": 0.8, "manual": 1.0, "social": 0.5}
        source_score = source_map.get(source, 0.4)
        
        total_score = (
            0.30 * type_score +
            0.20 * freq_score +
            0.20 * prox_score +
            0.15 * pattern_score +
            0.10 * semantic_score +
            0.05 * source_score
        )
        return min(1.0, total_score)

    def _get_entity_type_score(self, alias: str) -> float:
        """spaCy + Rule-based Hybrid detection."""
        if not self.nlp: return 0.4
        doc = self.nlp(alias)
        score = 0.4
        for ent in doc.ents:
            if ent.label_ == "ORG": score = 1.0
            elif ent.label_ == "PRODUCT": score = 0.7
        
        # Rule boost
        if any(term in alias.lower() for term in ["inc", "corp", "ltd", "plc"]):
            score = max(score, 0.9)
        return score

    def _get_frequency_score(self, alias: str, context: str) -> float:
        """Frequency within context."""
        if not context: return 0.0
        count = len(re.findall(re.escape(alias), context.lower()))
        return min(1.0, count / 5.0)

    def _get_proximity_score(self, alias: str, context: str, ticker: str, company_name: str) -> float:
        """MIN DISTANCE + EXP DECAY."""
        if not context: return 0.5
        
        alias_indices = [m.start() for m in re.finditer(re.escape(alias), context.lower())]
        target_indices = [m.start() for m in re.finditer(re.escape(ticker.lower()), context.lower())]
        if not target_indices:
            target_indices = [m.start() for m in re.finditer(re.escape(company_name.lower()), context.lower())]
            
        if not alias_indices or not target_indices:
            return 0.3
            
        min_dist = min(abs(a - t) for a in alias_indices for t in target_indices)
        return math.exp(-min_dist / 100) # Norm for 100 chars

    def _get_pattern_score(self, alias: str) -> float:
        """Legal entity pattern validation."""
        if any(term in alias.lower() for term in ["inc", "corp", "ltd", "plc"]): return 1.0
        if alias.isupper() and len(alias) <= 5: return 0.8 # Ticker-like
        return 0.3

    def _get_semantic_similarity(self, alias: str, company_name: str, score_hint: float) -> float:
        """Two-Tier Hybrid Semantic Strategy (Delegated to Provider Factory)."""
        from core.providers import ProviderFactory
        return ProviderFactory.get_alias_provider().get_semantic_similarity(alias, company_name, score_hint)

    def _run_llm_noise_filter(self, alias: str, context: str, ticker: str, company_name: str) -> str:
        """LLM Noise Filter Model (Classifier Only) (Delegated to Provider Factory)."""
        from core.providers import ProviderFactory
        return ProviderFactory.get_alias_provider().run_llm_noise_filter(alias, context, ticker, company_name)

    def _index_alias_tokens(self, alias_id: int, alias: str):
        """Token indexing for fast lookup."""
        tokens = set(re.split(r'\s+', alias))
        for t in tokens:
            if len(t) > 2:
                self.storage.add_token(alias_id, t)
