import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from utils.config import ALT_DATA_WEIGHTS, GOOGLE_TRENDS_CONFIG
from utils.logger import setup_logger

logger = setup_logger("AlternativeDataEngine")

class AlternativeDataEngine:
    """
    비정형 대체 데이터(Alternative Data) 분석 엔진
    - Google Trends (Search Volume)
    - SNS Sentiment (Twitter/Reddit)
    - News Momentum (Volume Spikes)
    """
    def __init__(self, weights: Dict = ALT_DATA_WEIGHTS):
        self.weights = weights
        self.ema_span = 7
        try:
            from pytrends.request import TrendReq
            self.pytrends = TrendReq(
                hl=GOOGLE_TRENDS_CONFIG.get('hl', 'en-US'),
                tz=GOOGLE_TRENDS_CONFIG.get('tz', 360),
                timeout=(GOOGLE_TRENDS_CONFIG.get('timeout', 10), 30),
                retries=GOOGLE_TRENDS_CONFIG.get('retries', 3)
            )
        except (ImportError, Exception):
            self.pytrends = None

    def _analyze_sentiment(self, headlines: List[str]) -> float:
        """
        [NEW] 키워드 기반 뉴스 센티먼트 분석 (Deterministic)
        - 긍정/부정 키워드 매칭을 통한 감성 점수 산출
        """
        if not headlines: return 0.0
        
        pos_words = ["buy", "bullish", "growth", "record", "profit", "gain", "upgrade", "positive", "strong", "beat", "surge", "long"]
        neg_words = ["sell", "bearish", "loss", "drop", "lawsuit", "layoff", "negative", "weak", "miss", "concern", "crash", "short"]
        
        score = 0
        total_count = 0
        
        for h in headlines:
            h_lower = h.lower()
            h_score = 0
            for w in pos_words:
                if w in h_lower: h_score += 1
            for w in neg_words:
                if w in h_lower: h_score -= 1
            
            if h_score != 0:
                score += (h_score / max(1, abs(h_score))) # Normalize to -1 or 1 per headline
                total_count += 1
                
        return score / total_count if total_count > 0 else 0.0

    def _calculate_buzz(self, headlines: List[str]) -> float:
        """
        [NEW] 뉴스 언급량(Buzz) 모멘텀 산출
        - 헤드라인 개수를 기반으로 관심도 측정 (정규화)
        """
        count = len(headlines)
        # 상위 20개 헤드라인 중 유효 비율 (10개 이상이면 강한 Buzz로 인식)
        buzz = (count / 10.0) - 1.0 # -1 (0개) ~ 1 (20개)
        return np.clip(buzz, -1.0, 1.0)

    def fetch_google_trends(self, ticker: str) -> pd.Series:
        """
        Google Trends 검색량 지수 로드 (EMA 기반 추세 보강)
        """
        if self.pytrends:
            try:
                # 쿼리에 티커 직접 입력 (최근 3개월 데이터)
                self.pytrends.build_payload([ticker], cat=0, timeframe='today 3-m')
                df = self.pytrends.interest_over_time()
                if not df.empty and ticker in df.columns:
                    return df[ticker]
            except Exception as e:
                logger.error(f"Google Trends Error for {ticker}: {e}")

        # Fallback: Provider Unavailable
        return pd.Series(dtype=float)

    def calculate_alternative_score(self, ticker: str, headlines: List[str] = []) -> float:
        """
        [DE-RANDOMIZED] 대체 데이터 통합 스코어링
        1. Google Trends Velocity (검색 급증 여부)
        2. News Sentiment (헤드라인 긍부정)
        3. News Buzz (절대적 언급량)
        """
        try:
            # 1. Google Trends (Velocity 측정)
            trends = self.fetch_google_trends(ticker)
            if trends.empty:
                scaled_trend = np.nan
            else:
                smoothed_fast = trends.ewm(span=7).mean()
                smoothed_slow = trends.ewm(span=30).mean()
                trend_velocity = (smoothed_fast.iloc[-1] / (smoothed_slow.iloc[-1] + 1e-9)) - 1
                scaled_trend = np.clip(trend_velocity * 5, -1, 1)

            # 2. News Sentiment & Buzz
            sentiment = self._analyze_sentiment(headlines)
            buzz = self._calculate_buzz(headlines)
            
            # 3. 통합 (가중 합산)
            if np.isnan(scaled_trend):
                # PyTrends is UNAVAILABLE. P6-11B allows graceful degradation.
                # We return np.nan to explicitly propagate UNAVAILABLE status.
                logger.info(f"[{ticker}] Alt Data: UNAVAILABLE (PyTrends missing/failed)")
                return np.nan
                
            # Buzz가 높을수록 Sentiment 점수의 신뢰도를 높여 반영
            final_alt_score = (
                self.weights.get('google_trends', 0.3) * scaled_trend +
                self.weights.get('sns_sentiment', 0.4) * sentiment * (1 + abs(buzz)) +
                self.weights.get('news_momentum', 0.3) * buzz
            )
            
            # [-1, 1] 범위로 클리핑
            final_alt_score = np.clip(final_alt_score, -1.0, 1.0)

            logger.info(f"[{ticker}] Alt Data (REAL): {final_alt_score:+.4f} [Trends: {scaled_trend:+.2f}, Sent: {sentiment:+.2f}, Buzz: {buzz:+.2f}]")
            return final_alt_score

        except Exception as e:
            logger.error(f"Alternative Data Error for {ticker}: {str(e)}")
            return np.nan

    def get_alt_data_matrix(self, tickers: List[str], news_data_dict: Dict[str, List[str]]) -> pd.Series:
        """종목별 대체 데이터 점수 산출 매트릭스"""
        results = {ticker: self.calculate_alternative_score(ticker, news_data_dict.get(ticker, [])) for ticker in tickers}
        return pd.Series(results)
