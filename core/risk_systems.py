import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from utils.config import TAIL_RISK_SETTINGS, CAPACITY_SETTINGS
from utils.logger import setup_logger

logger = setup_logger("RiskSystems")

class TailRiskEngine:
    """
    테일 리스크(Tail Risk) 및 블랙스완 대응 엔진
    - Volatility Spike Detection (Z-score)
    - Drawdown Monitoring
    - Crash Probability Estimation
    - Emergency Stop & Risk-Off
    """
    def __init__(self, config: Dict = TAIL_RISK_SETTINGS):
        self.config = config
        self.current_mdd = 0.0
        self.peak_value = -np.inf

    def detect_vol_spike(self, returns: pd.Series, window: int = 20) -> bool:
        """변동성이 역사적 평균 대비 급증했는지 확인 (Z-score 기반)"""
        vol = returns.rolling(window=window).std() * np.sqrt(252)
        if len(vol) < window * 2: return False
        
        recent_vol = vol.iloc[-1]
        hist_vol_mean = vol.iloc[:-window].mean()
        hist_vol_std = vol.iloc[:-window].std()
        
        z_score = (recent_vol - hist_vol_mean) / hist_vol_std if hist_vol_std > 0 else 0
        is_spike = z_score > self.config['vol_spike_threshold']
        
        if is_spike:
            logger.warning(f"Volatility Spike Detected! Z-score: {z_score:.2f}")
        return is_spike

    def calculate_crash_probability(self, prices: pd.DataFrame) -> float:
        """
        간략화된 크래시 확률 모델
        - 하락 가속도 및 이동평균 이격도 기반
        - 멀티 자산의 경우 평균치를 사용하여 전체 시장 흐름 분석
        """
        # 자산별이 아닌 전체 시장(평균) 흐름 분석
        market_proxy = prices.mean(axis=1) if isinstance(prices, pd.DataFrame) else prices
        
        short_ma = market_proxy.rolling(window=20).mean()
        long_ma = market_proxy.rolling(window=200).mean()
        
        if len(market_proxy) < 20: return 0.0
        
        # 데드크로스 발생 및 가격이 급격히 MA 아래로 하향 시 확률 증가
        distance = (market_proxy.iloc[-1] / short_ma.iloc[-1]) - 1
        ma_slope = (short_ma.iloc[-1] / (short_ma.iloc[-5] if len(short_ma) >= 5 else short_ma.iloc[0])) - 1
        
        prob = 0.0
        if distance < -0.05: prob += 0.3
        if ma_slope < -0.02: prob += 0.4
        if long_ma.iloc[-1] > 0 and market_proxy.iloc[-1] < long_ma.iloc[-1]: prob += 0.3
        
        return min(prob, 1.0)

    def get_risk_multiplier(self, 
                             portfolio_value_history: pd.Series, 
                             market_returns: pd.Series,
                             market_prices: pd.Series) -> float:
        """
        현재 리스크 상태를 분석하여 노출도 조절 배수 반환 (0.0 ~ 1.0)
        """
        # 1. MDD 체크
        peak = portfolio_value_history.max()
        current = portfolio_value_history.iloc[-1]
        mdd = (current / peak) - 1 if peak > 0 else 0
        
        # Emergency Stop
        if mdd < self.config['emergency_stop_mdd']:
            logger.critical(f"EMERGENCY STOP: MDD {mdd:.2%} breached limit!")
            return 0.0
        
        # 2. Vol Spike & Crash Prob
        is_spike = self.detect_vol_spike(market_returns)
        crash_prob = self.calculate_crash_probability(market_prices)
        
        multiplier = 1.0
        if is_spike: multiplier *= 0.5
        if crash_prob > self.config['crash_prob_threshold']: multiplier *= 0.3
        if mdd < self.config['mdd_limit']: multiplier *= 0.7
        
        return max(multiplier, 0.0)

class CapacityEngine:
    """
    운용 한도(Capacity) 및 유동성 분석 엔진
    - ADV(Average Daily Volume) 대비 점유율 분석
    - 자금 규모 증가에 따른 성과 감쇄(Alpha Decay) 예측
    """
    def __init__(self, config: Dict = CAPACITY_SETTINGS):
        self.config = config

    def estimate_market_impact(self, 
                               order_value: float, 
                               avg_daily_volume_value: float) -> float:
        """거래 대금 대비 시장 충격(bps) 추정"""
        participation = order_value / avg_daily_volume_value
        # 단순 충격 모델: Impact = 0.1 * sqrt(Participation)
        impact_bps = 100 * np.sqrt(participation) if participation > 0 else 0
        return impact_bps

    def get_capacity_score(self, 
                           current_aum: float, 
                           portfolio_weights: pd.Series, 
                           adv_data: pd.Series) -> Dict:
        """
        현재 포트폴리오의 운용 가능 용량 평가
        """
        # 1. ADV 점유율 체크
        position_values = portfolio_weights * current_aum
        
        # ADV 데이터가 DataFrame일 경우 최근값 Series로 변환
        target_adv = adv_data.iloc[-1] if isinstance(adv_data, pd.DataFrame) else adv_data
        
        participation_rates = position_values / target_adv.loc[portfolio_weights.index]
        max_participation = participation_rates.max()
        
        avg_participation = participation_rates.mean()
        
        # 2. Alpha Decay (운용 자산 규모에 따른 페널티)
        # Decay = 2 ^ (-AUM / HalfLife)
        decay_factor = 2 ** (-current_aum / self.config['decay_half_life_aum'])
        
        is_over_capacity = max_participation > self.config['max_adv_participation']
        
        status = {
            "is_over_capacity": is_over_capacity,
            "max_participation": max_participation,
            "avg_participation": avg_participation,
            "alpha_decay_factor": decay_factor,
            "recommended_max_aum": adv_data.median() * self.config['max_adv_participation'] / portfolio_weights.max()
        }
        
        if is_over_capacity:
            logger.warning(f"Capacity Alert: Max ADV Participation {max_participation:.2%} exceeds limit!")
            
        return status
