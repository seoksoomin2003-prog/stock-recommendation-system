import requests
import json
import asyncio
import time
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Union, Optional
from utils.config import OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, MAX_CONCURRENT_LLM_REQUESTS
from utils.logger import setup_logger

logger = setup_logger("NewsEngine")

class NewsEngine:
    """
    고급 뉴스 센티먼트 분석 엔진 (V2)
    - 이벤트 분류 (Earnings, Macro, Regulatory 등)
    - 이벤트별 중요도 가중치 부여
    - 시간 붕괴 (Time Decay) 적용
    - 신뢰도 (Confidence Score) 산출
    - 중복 제거 및 클러스터링 기반 필터링
    """
    def __init__(self, model: str = OLLAMA_MODEL):
        self.model = model
        # 이벤트별 가중치 체계
        self.event_weights = {
            "earnings": 5.0,
            "guidance": 3.0,
            "revenue": 3.0,
            "profit": 4.0,
            "M&A": 5.0,
            "product": 2.0,
            "lawsuit": 4.5,
            "regulatory": 4.0,
            "management": 3.0,
            "insider": 3.5,
            "analyst_rating": 2.5,
            "macro": 1.5,
            "Fed": 4.0,
            "interest_rate": 3.5,
            "inflation": 3.0,
            "employment": 2.5,
            "geopolitical": 3.5,
            "other": 1.0
        }
        # 키워드 매핑
        self.rules = {
            "실적": "earnings", "가이던스": "guidance", "금리": "interest_rate", 
            "인수합병": "M&A", "규제": "regulatory", "소송": "lawsuit",
            "파산": "other", "earnings": "earnings", "merger": "M&A",
            "revenue": "revenue", "profit": "profit", "guidance": "guidance",
            "fed": "Fed", "inflation": "inflation", "cpi": "inflation"
        }
        self._semaphore = None
        self.session = requests.Session()
        # Simple local in-memory cache to prevent redundant requests
        self._cache = {}
        from utils.memory_guard import MemoryGuard
        MemoryGuard.register_cache(self._cache)

    def _get_event_priority_tier(self, event_type: str) -> int:
        """
        이벤트 유형에 따른 우선순위 티어 (1: 최상위, 2: 중위, 3: 하위)
        """
        if event_type in ["earnings", "M&A", "profit", "lawsuit", "Fed", "regulatory"]:
            return 1
        if event_type in ["guidance", "revenue", "interest_rate", "geopolitical"]:
            return 2
        return 3

    def _get_source_quality(self, source: str) -> float:
        """
        Assigns source quality score based on institutional credentials.
        """
        if not source:
            return 0.2
        src = source.lower().strip()
        tier1 = ["reuters", "bloomberg", "wsj", "wall street journal", "cnbc", "ap", "associated press", "sec", "regulatory", "press release"]
        tier2 = ["yahoo finance", "motley fool", "seeking alpha", "marketwatch", "investor", "financial times", "ft", "nasdaq"]
        tier3 = ["reddit", "twitter", "blog", "hackernews", "medium", "tumblr", "substack"]
        
        if any(t in src for t in tier1):
            return 1.0
        if any(t in src for t in tier2):
            return 0.8
        if any(t in src for t in tier3):
            return 0.4
        return 0.2

    def calculate_confidence(self, article: Dict, days_ago: float, is_duplicate: bool = False) -> float:
        """
        Calculates sentiment signal confidence.
        """
        source_quality = self._get_source_quality(article.get("source", ""))
        recency_factor = np.exp(-0.1 * days_ago)
        
        score = article.get("raw_sentiment", 0.0)
        sentiment_certainty = 0.5 + 0.5 * abs(score)
        
        dup_penalty = 0.5 if is_duplicate else 1.0
        
        confidence = source_quality * recency_factor * sentiment_certainty * dup_penalty
        return max(0.1, min(1.0, float(confidence)))

    def calculate_buzz(self, articles: List[Dict], evaluation_time: float) -> float:
        """
        Calculates News Momentum/Buzz.
        """
        if not articles:
            return 0.0
            
        ages = []
        for art in articles:
            pub_time = art.get("published_at_ts", evaluation_time)
            age = (evaluation_time - pub_time) / 86400.0
            if age >= 0:
                ages.append(age)
                
        if not ages:
            return 0.0
            
        day1_count = sum(1 for age in ages if age <= 1.0)
        day2_3_count = sum(1 for age in ages if 1.0 < age <= 3.0)
        
        if day2_3_count > 0:
            change_rate = (day1_count) / (day2_3_count / 2.0)
        else:
            change_rate = day1_count * 2.0 if day1_count > 0 else 1.0
            
        decayed_vol = sum(np.exp(-0.2 * age) for age in ages)
        buzz = (decayed_vol * 0.5) + (day1_count * 1.5) + (min(3.0, change_rate) * 2.0)
        return max(0.0, float(buzz))

    async def _analyze_single_news_v2(self, article: Dict, evaluation_time: float) -> Dict:
        """개별 뉴스 분석 및 결정론적 가중치 적용"""
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            headline = article.get("headline", "")
            
            score, confidence = await loop.run_in_executor(None, self.get_sentiment_score_with_confidence, headline)
            article["raw_sentiment"] = score
            
            event_type = self._get_event_type(headline)
            event_weight = self.event_weights.get(event_type, 1.0)
            priority = self._get_event_priority_tier(event_type)
            
            pub_ts = article.get("published_at_ts", evaluation_time)
            days_ago = max(0.0, (evaluation_time - pub_ts) / 86400.0)
            
            decayed_score = self.apply_time_decay(score, days_ago, event_type)
            conf = self.calculate_confidence(article, days_ago, article.get("is_duplicate", False))
            
            final_weighted_score = decayed_score * event_weight * (conf ** 2)
            
            return {
                "score": score,
                "confidence": conf,
                "weighted_score": final_weighted_score,
                "event": event_type,
                "priority": priority
            }

    async def analyze_sentiment_batch_v2(self, headlines: List[Union[str, Dict]], ticker: str = "Unknown", evaluation_time: float = None) -> float:
        """
        [DE-AVERAGED] 티어별 맥스 풀링 (Tiered Max-Pooling)
        """
        now_ts = evaluation_time or time.time()
        
        # Normalize to Dict representations
        articles = []
        for item in headlines:
            if isinstance(item, str):
                articles.append({
                    "headline": item,
                    "source": "Reuters",
                    "published_at_ts": now_ts,
                    "is_duplicate": False
                })
            elif isinstance(item, dict):
                pub_ts = item.get("published_at_ts")
                if pub_ts is None:
                    pub_str = item.get("published_at")
                    if pub_str:
                        try:
                            pub_ts = pd.Timestamp(pub_str).timestamp()
                        except Exception:
                            pub_ts = now_ts
                    else:
                        pub_ts = now_ts
                
                # Prevent look-ahead bias: articles in the future are discarded
                if pub_ts > now_ts:
                    continue
                    
                articles.append({
                    "headline": item.get("headline") or item.get("title") or "",
                    "source": item.get("source") or "unknown",
                    "published_at_ts": pub_ts,
                    "is_duplicate": False
                })
                
        if not articles:
            logger.info(f"[TELEMETRY] ticker={ticker} status=UNAVAILABLE (No valid articles)")
            return np.nan

        # Mark duplicates instead of deleting, to allow penalties
        unique_articles = []
        for art in articles:
            headline = art.get("headline", "").strip().lower()
            pub_ts = art.get("published_at_ts", 0.0)
            
            is_dup = False
            for u_art in unique_articles:
                u_headline = u_art.get("headline", "").strip().lower()
                u_pub_ts = u_art.get("published_at_ts", 0.0)
                
                # Jaccard matching
                w1 = set(headline.split())
                w2 = set(u_headline.split())
                jaccard = len(w1 & w2) / len(w1 | w2) if (w1 | w2) else 0.0
                
                if jaccard > 0.65 and abs(pub_ts - u_pub_ts) < 86400.0:
                    is_dup = True
                    break
            
            if is_dup:
                art["is_duplicate"] = True
            else:
                unique_articles.append(art)
                
        tasks = [self._analyze_single_news_v2(art, now_ts) for art in articles]
        results = await asyncio.gather(*tasks)
        
        # Filter noise
        valid_results = [r for r in results if r['confidence'] >= 0.2]
        if not valid_results:
            return np.nan
            
        tier1 = [r for r in valid_results if r['priority'] == 1]
        tier2 = [r for r in valid_results if r['priority'] == 2]
        tier3 = [r for r in valid_results if r['priority'] == 3]
        
        if tier1: dominant_group = tier1
        elif tier2: dominant_group = tier2
        else: dominant_group = tier3
        
        dominant_event = max(dominant_group, key=lambda x: abs(x['weighted_score']))
        final_sentiment = dominant_event['weighted_score']
        
        # Offset handling
        opposite_score = [r['weighted_score'] for r in dominant_group if np.sign(r['weighted_score']) != np.sign(final_sentiment)]
        if opposite_score:
            max_opposite = max(opposite_score, key=abs)
            final_sentiment = (final_sentiment + max_opposite) / 2
            
        # Telemetry
        logger.info(
            f"[TELEMETRY] ticker={ticker} article_count={len(headlines)} "
            f"unique_article_count={len(unique_articles)} sentiment={final_sentiment:+.4f} "
            f"buzz={self.calculate_buzz(articles, now_ts):.2f} event_type={dominant_event['event']} "
            f"status=OK"
        )
        
        # Extreme value validation check and clipping
        if np.isnan(final_sentiment) or np.isinf(final_sentiment):
            return np.nan
            
        return max(-1.0, min(1.0, float(final_sentiment)))

    @property
    def semaphore(self):
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_REQUESTS)
        return self._semaphore

    def get_sentiment_score_with_confidence(self, headline: str) -> Tuple[float, float]:
        """
        Determines sentiment score [-1.0, 1.0] and confidence [0.0, 1.0] using rule-based contextual rules.
        """
        if not headline:
            return 0.0, 0.0
            
        headline_lower = headline.lower()
        
        is_negated = False
        if any(neg in headline_lower for neg in ["not", "never", "no", "fail", "despite", "without"]):
            is_negated = True
            
        # Contrary structures
        if "despite" in headline_lower and any(n in headline_lower for n in ["fall", "drop", "down", "plummet", "slide"]):
            return -0.4, 0.5
            
        if "beat" in headline_lower and "expectations" in headline_lower:
            return 0.8, 0.9
            
        if "lawsuit" in headline_lower or "sued" in headline_lower:
            return -0.8, 0.85
            
        pos_map = {
            "upgrade": 0.8, "buy": 0.6, "bullish": 0.8, "growth": 0.5,
            "surge": 0.9, "beat": 0.7, "strong": 0.6, "improve": 0.5,
            "gain": 0.5, "record": 0.8, "acquire": 0.7, "merger": 0.6,
            "호조": 0.7, "상승": 0.6, "흑자": 0.8, "성장": 0.6
        }
        
        neg_map = {
            "downgrade": -0.8, "sell": -0.6, "bearish": -0.8, "drop": -0.5,
            "fall": -0.5, "loss": -0.7, "weak": -0.5, "miss": -0.6,
            "concern": -0.5, "bankruptcy": -1.0, "lawsuit": -0.8, "sued": -0.8,
            "하락": -0.6, "부진": -0.7, "적자": -0.8, "우려": -0.5
        }
        
        pos_hits = [pos_map[k] for k in pos_map if k in headline_lower]
        neg_hits = [neg_map[k] for k in neg_map if k in headline_lower]
        
        if pos_hits and neg_hits:
            raw_score = sum(pos_hits) + sum(neg_hits)
            confidence = 0.4
        elif pos_hits:
            raw_score = sum(pos_hits) / len(pos_hits)
            confidence = 0.8
        elif neg_hits:
            raw_score = sum(neg_hits) / len(neg_hits)
            confidence = 0.8
        else:
            raw_score = 0.0
            confidence = 0.5
            
        if is_negated:
            raw_score = -0.5 * raw_score
            confidence = max(0.3, confidence - 0.2)
            
        return max(-1.0, min(1.0, raw_score)), confidence

    def _get_event_type(self, headline: str) -> str:
        h = headline.lower()
        if "earning" in h or "quarter" in h or "실적" in h:
            return "earnings"
        if "guidance" in h or "가이던스" in h or "outlook" in h:
            return "guidance"
        if "revenue" in h or "sales" in h or "매출" in h:
            return "revenue"
        if "profit" in h or "income" in h or "net profit" in h or "흑자" in h:
            return "profit"
        if "m&a" in h or "acquire" in h or "acquisition" in h or "merger" in h or "인수" in h or "합병" in h:
            return "M&A"
        if "product" in h or "launch" in h or "iphone" in h or "release" in h or "제품" in h:
            return "product"
        if "lawsuit" in h or "sued" in h or "litigation" in h or "소송" in h:
            return "lawsuit"
        if "regulatory" in h or "antitrust" in h or "sec" in h or "ftc" in h or "regulation" in h or "규제" in h:
            return "regulatory"
        if "ceo" in h or "cfo" in h or "management" in h or "board" in h or "경영진" in h:
            return "management"
        if "insider" in h or "insider buy" in h or "insider sell" in h:
            return "insider"
        if "upgrade" in h or "downgrade" in h or "analyst" in h or "price target" in h:
            return "analyst_rating"
        if "fed" in h or "powell" in h or "fomc" in h or "연준" in h:
            return "Fed"
        if "interest rate" in h or "rate hike" in h or "rate cut" in h or "금리" in h:
            return "interest_rate"
        if "inflation" in h or "cpi" in h or "pce" in h or "물가" in h:
            return "inflation"
        if "employment" in h or "nfp" in h or "jobs report" in h or "unemployment" in h or "고용" in h:
            return "employment"
        if "geopolitical" in h or "war" in h or "tariff" in h or "china" in h or "sanction" in h:
            return "geopolitical"
        if "macro" in h or "gdp" in h or "economy" in h:
            return "macro"
        return "other"

    def apply_time_decay(self, score: float, days_ago: int, event_type: str = "other") -> float:
        lambdas = {
            "earnings": 0.1,
            "guidance": 0.1,
            "revenue": 0.15,
            "profit": 0.1,
            "M&A": 0.03,
            "product": 0.3,
            "lawsuit": 0.02,
            "regulatory": 0.05,
            "management": 0.03,
            "insider": 0.15,
            "analyst_rating": 0.4,
            "Fed": 0.2,
            "interest_rate": 0.2,
            "inflation": 0.2,
            "employment": 0.25,
            "geopolitical": 0.05,
            "macro": 0.1,
            "other": 0.5
        }
        decay_lambda = lambdas.get(event_type, 0.2)
        return score * np.exp(-decay_lambda * days_ago)

    def filter_and_deduplicate(self, headlines: List[str]) -> List[str]:
        """Backward compatibility helper"""
        if not headlines:
            return []
        seen = set()
        unique_headlines = []
        for h in headlines:
            h_clean = h.strip().lower()
            if h_clean not in seen:
                seen.add(h_clean)
                unique_headlines.append(h)
        return unique_headlines

    def get_company_sentiment(self, headlines: List[Union[str, Dict]], ticker: str = "Unknown", evaluation_time: float = None) -> float:
        """최종 센티먼트 점수 산출 (V2)"""
        self._semaphore = None
        try:
            return asyncio.run(self.analyze_sentiment_batch_v2(headlines, ticker=ticker, evaluation_time=evaluation_time))
        except Exception as e:
            logger.error(f"Error in get_company_sentiment: {e}")
            return np.nan

    def fetch_news(self, ticker: str) -> List[Dict]:
        """
        Fetches news articles using Company Name resolution and OR-queries.
        """
        try:
            from alpha_engine.input.resolver import EntityResolutionEngine
            resolver = EntityResolutionEngine()
            resolved = resolver.resolve_input(ticker)
            company_name = resolved.get("company_name", ticker)
            if not company_name or company_name == "Unknown":
                company_name = ticker

            # Check cache with 1 hour TTL
            now_ts = time.time()
            cache_key = f"{ticker}:{company_name}"
            if cache_key in self._cache:
                entry, cache_ts = self._cache[cache_key]
                if now_ts - cache_ts < 3600:
                    return entry

            sub_queries = [
                f'"{ticker}"',
                f'"{company_name}"',
                f'"{ticker} stock"',
                f'"{company_name} earnings"',
                f'"{company_name} guidance"'
            ]
            merged_query = " OR ".join(sub_queries[:5])

            from data.loader import DataLoader
            loader = DataLoader()
            
            if loader.newsapi:
                from datetime import datetime, timedelta
                from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
                
                try:
                    res_dict = loader.newsapi.get_everything(
                        q=merged_query,
                        from_param=from_date,
                        to=datetime.now().strftime('%Y-%m-%d'),
                        language='en',
                        sort_by='relevancy'
                    )
                    articles = []
                    for art in res_dict.get("articles", []):
                        articles.append({
                            "headline": art.get("title") or "",
                            "source": art.get("source", {}).get("name") or "unknown",
                            "published_at": art.get("publishedAt"),
                            "url": art.get("url")
                        })
                    self._cache[cache_key] = (articles, now_ts)
                    return articles
                except Exception as e:
                    logger.error(f"[API_FAILURE] provider=NewsDataProvider ticker={ticker} attempts=1 error={type(e).__name__} status=UNAVAILABLE")
                    return []
            
            # Provider missing
            return []
        except Exception as e:
            logger.error(f"Failed to fetch news for {ticker}: {e}")
            return []
