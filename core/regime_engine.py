import pandas as pd
import numpy as np
from typing import Dict, Union, Tuple, Optional
from utils.logger import setup_logger

logger = setup_logger("RegimeEngine")

class RegimeEngine:
    """
    시장 국면(Regime) 판별 엔진
    - 다중 지표(Trend, Volatility, Breadth) 기반 확률적 판별
    - 레짐 전환 Smoothing (노이즈 제거)
    """
    def __init__(self, 
                 trend_window: int = 200, 
                 vol_window: int = 20, 
                 smooth_window: int = 5):
        self.trend_window = trend_window
        self.vol_window = vol_window
        self.smooth_window = smooth_window
        # 판별 임계값 및 가중치 (하드코딩 제거)
        self.trend_threshold = 0.02
        self.vol_threshold = 0.2
        self.bull_base = 0.6
        self.bear_base = 0.6

    def detect_regime(self, market_index: pd.Series, market_breadth: Optional[pd.Series] = None) -> Dict:
        """
        시장 상태 판별: Bull, Bear, Sideways 확률 및 점수 반환
        """
        epsilon = 1e-9
        
        # 1. Trend Score (이동평균 대비 괴리율)
        ma = market_index.rolling(window=self.trend_window).mean()
        trend_score = (market_index.iloc[-1] - ma.iloc[-1]) / (ma.iloc[-1] + epsilon)
        
        # 2. Volatility Score (장기 평균 대비 변동성 비율)
        vol = market_index.pct_change().rolling(window=self.vol_window).std() * np.sqrt(252)
        vol_avg = vol.rolling(window=252).mean()
        vol_score = (vol.iloc[-1] - vol_avg.iloc[-1]) / (vol_avg.iloc[-1] + epsilon)
        
        # 3. Breadth (상승 종목 비율)
        breadth_val = market_breadth.iloc[-1] if market_breadth is not None else 0.5
        
        # 4. 확률 산출 (Bull & Bear 우선 산출)
        # Bull: 상승 추세 + 저변동성 + 높은 마켓 브레드
        bull_p = max(0, (self.bull_base if trend_score > 0 else 0.1) * 
                        (1.2 if vol_score < self.vol_threshold else 0.5) * 
                        breadth_val)
        
        # Bear: 하락 추세 + 고변동성 + 낮은 마켓 브레드
        bear_p = max(0, (self.bear_base if trend_score < 0 else 0.1) * 
                        (1.5 if vol_score > self.vol_threshold else 0.4) * 
                        (1 - breadth_val))
        
        # 5. Sideways 확률 (계산값 유지, 하드코딩 제거)
        # Bull/Bear로 설명되지 않는 나머지 공간을 횡보장으로 간주
        sideways_p = max(0, 1.0 - (bull_p + bear_p))
        
        # 6. 정규화 (probs 의 합 = 1)
        raw_probs = np.array([bull_p, bear_p, sideways_p])
        probs = raw_probs / (raw_probs.sum() + epsilon)
        
        # 7. 가독성 점수 및 결과 구성
        scores = probs * 100
        regime_labels = ["bull", "bear", "sideways"]
        regime_idx = np.argmax(probs)
        
        regime_results = {
            "probabilities": probs.tolist(),
            "scores": scores.tolist(),
            "regime": regime_labels[regime_idx],
            "metadata": {
                "trend": "up" if trend_score > 0 else "down",
                "volatility": "high" if vol_score > self.vol_threshold else "low",
                "labels": regime_labels
            }
        }
        
        logger.info(f"Regime Detected: {regime_results['regime']} (Bull: {scores[0]:.1f}, Bear: {scores[1]:.1f}, Side: {scores[2]:.1f})")
        return regime_results

    def get_adjusted_weights(self, base_weights: Dict[str, float], regime: str) -> Dict[str, float]:
        """
        시장 상태에 따른 팩터 가중치 동적 조정
        """
        adjusted = base_weights.copy()
        if regime == 'bull':
            # 강세장: 모멘텀 강화
            adjusted['momentum'] *= 1.2
            adjusted['value'] *= 0.8
        elif regime == 'bear':
            # 약세장: 가치 및 저변동성 강화
            adjusted['value'] *= 1.2
            adjusted['low_volatility'] *= 1.3
            adjusted['momentum'] *= 0.5
            
        # 가중치 합 1로 재정규화
        total = sum(adjusted.values())
        return {k: v / total for k, v in adjusted.items()}
