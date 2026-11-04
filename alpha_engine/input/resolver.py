import time
import re
from typing import Dict, List, Optional, Union, Any
import sqlite3
from .storage import TickerStorage
from .pipeline import AliasGenerationPipeline
from utils.logger import setup_logger

# RapidFuzz / difflib fallback
try:
    from rapidfuzz import fuzz, process
    USE_RAPIDFUZZ = True
except ImportError:
    import difflib
    USE_RAPIDFUZZ = False

logger = setup_logger("EntityResolutionEngine")

class EntityResolutionEngine:
    """
    SECTION 6: Production Resolver & Tiered Cache
    - adaptive TTL based on hit patterns.
    - Token-indexed candidate filtering.
    """
    def __init__(self):
        self.storage = TickerStorage()
        self.pipeline = AliasGenerationPipeline(self.storage)
        self.ttl_map = {
            'HOT': 3600,      # 1 hour
            'WARM': 21600,    # 6 hours
            'COLD': 86400     # 24 hours
        }

    def parse_input(self, user_input: Union[str, List[str]]) -> List[str]:
        """
        Parses user input string into candidate entity strings.
        For example: "구글이랑 애플 분석해줘" -> ["구글", "애플"]
        """
        if not user_input:
            return []
        if isinstance(user_input, list):
            return user_input
            
        cleaned = re.sub(r'[^\w\s]', ' ', user_input)
        tokens = [t for t in cleaned.split() if len(t) > 0]
        
        candidates = []
        for token in tokens:
            cleaned_token = re.sub(r'(이랑|랑|은|는|이|가|을|를|와|과|분석해줘|분석|해줘)$', '', token).strip()
            if cleaned_token and len(cleaned_token) >= 1:
                # check if there's any matching alias or ticker in DB
                with sqlite3.connect(self.storage.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT DISTINCT t.ticker 
                        FROM tickers t 
                        LEFT JOIN aliases a ON t.id = a.ticker_id
                        WHERE t.ticker = ? OR a.alias = ? OR t.company_name LIKE ? OR a.alias LIKE ?
                    """, (cleaned_token.upper(), cleaned_token.lower(), f"%{cleaned_token}%", f"%{cleaned_token}%"))
                    if cursor.fetchone():
                        candidates.append(cleaned_token)
                        continue
                
                if cleaned_token.isupper() and len(cleaned_token) <= 5:
                    candidates.append(cleaned_token)
                elif re.match(r'^[가-힣]+$', cleaned_token):
                    candidates.append(cleaned_token)
                    
        if not candidates:
            candidates = [t for t in tokens if len(t) > 1]
        if not candidates:
            candidates = [user_input]
            
        return candidates

    def resolve_input(self, query: str) -> Dict:
        """
        Wrapper around resolve() to match the system.py public API.
        """
        return self.resolve(query)

    def resolve(self, query: str) -> Dict:
        """
        Executes the production resolution flow (SECTION 6).
        """
        query = query.lower().strip()
        
        # 1. Lookup Cache (Tiered Expiry)
        cached = self.storage.get_cache(query)
        if cached:
            expiry = self.ttl_map.get(cached['usage_tier'], 86400)
            if time.time() - cached['last_used'] < expiry:
                logger.info(f"Cache Hit [{cached['usage_tier']}]: '{query}' -> {cached['ticker']}")
                return self._format_result(cached['ticker'], cached['confidence'], query)

        # 2. Token Search (O(1) Inverted Index Lookup)
        query_tokens = [t for t in re.split(r'\s+', query) if len(t) > 2]
        candidates = []
        if query_tokens:
            for t in query_tokens:
                candidates.extend(self.storage.search_by_token(t))
        else:
            # Fallback if query itself is very short (e.g., 'AAPL')
            candidates = self.storage.search_by_token(query)
            
        # 3. Fuzzy Ranking (Hybrid Engine)
        if candidates:
            # deduplicate by ticker
            seen = set()
            unique_candidates = []
            for c in candidates:
                if c['ticker'] not in seen:
                    unique_candidates.append(c)
                    seen.add(c['ticker'])
                    
            best = self._rank_candidates(query, unique_candidates)
            if best['confidence'] >= 0.6: # Relaxed slightly for multi-token fuzzy
                self.storage.set_cache(query, best['ticker'], best['confidence'])
                return best
        
        # 4. Wide Fuzzy Fallback (if no tokens match)
        logger.info(f"Token search failed for '{query}'. Running wide fuzzy fallback...")
        all_aliases = self.storage.get_all_aliases_for_fuzzy(min_confidence=0.8)
        if all_aliases:
            best_fuzzy = self._rank_candidates(query, all_aliases)
            if best_fuzzy['confidence'] >= 0.6:
                self.storage.set_cache(query, best_fuzzy['ticker'], best_fuzzy['confidence'])
                return best_fuzzy

        # 5. If still failed, trigger discovery
        logger.warning(f"Resolution failed for '{query}'. Triggering potential fallback...")
        
        return {
            "ticker": None,
            "company_name": "Unknown",
            "confidence": 0.0,
            "normalized_input": query
        }

    def _rank_candidates(self, query: str, candidates: List[Dict]) -> Dict:
        """Ranks candidates using RapidFuzz or difflib."""
        if not candidates:
            return {"ticker": None, "confidence": 0.0}

        # Convert candidates to list of names for matching
        choices = [c['alias'] for c in candidates]
        
        if USE_RAPIDFUZZ:
            result = process.extractOne(query, choices, scorer=fuzz.WRatio)
            if result:
                match_val, score, idx = result
                match_conf = (score / 100.0) * candidates[idx]['confidence']
                return self._format_result(candidates[idx]['ticker'], match_conf, query)
        else:
            matches = difflib.get_close_matches(query, choices, n=1, cutoff=0.6)
            if matches:
                # Find matching candidate
                match_val = matches[0]
                candidate = next(c for c in candidates if c['alias'] == match_val)
                return self._format_result(candidate['ticker'], candidate['confidence'] * 0.8, query)

        return {"ticker": None, "company_name": "Unknown", "confidence": 0.0}

    def _format_result(self, ticker: str, confidence: float, query: str) -> Dict:
        company_name = self.storage.get_company_name(ticker) if ticker else "Unknown"
        return {
            "ticker": ticker,
            "company_name": company_name,
            "confidence": round(confidence, 2),
            "normalized_input": query
        }
