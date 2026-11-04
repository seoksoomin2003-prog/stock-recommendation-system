import pandas as pd
from typing import Dict, List, Optional, Union
from utils.logger import setup_logger

logger = setup_logger("MetaController")

class MetaController:
    """
    전체 시스템 총괄 컨트롤러
    - 알파 성능 추적 및 리스크 대응
    - 성과 저하 시 자동 Exposure 축소
    - 시장 국면(Regime)에 따른 전략 스위칭 제어
    - 모델 상태 및 결정 내역 로깅
    """
    def __init__(self, 
                 exposure_limit: float = 1.0, 
                 emergency_stop_mdd: float = -0.20):
        self.exposure_limit = exposure_limit
        self.emergency_stop_mdd = emergency_stop_mdd
        self.current_exposure = 1.0

    def adjust_exposure(self, 
                        is_performance_degraded: bool, 
                        current_mdd: float) -> float:
        """
        성과 및 리스크 상태에 따라 노출도(Exposure) 동적 조절
        """
        # 1. MDD 한도 초과 시 비상 정지 (0으로 축소)
        if current_mdd < self.emergency_stop_mdd:
            logger.error(f"EMERGENCY STOP: MDD ({current_mdd:.2f}) exceeded limit. Cutting exposure to 0.")
            self.current_exposure = 0.0
            return self.current_exposure
            
        # 2. 성과 저하 시 점진적 축소 (De-leveraging)
        if is_performance_degraded:
            target_exposure = self.current_exposure * 0.8
            logger.warning(f"Strategy Optimization Alert: Reducing exposure to {target_exposure:.2f}")
            self.current_exposure = max(0.2, target_exposure) # 최소 20% 유지 (회복 기회 확보)
        else:
            # 정상 성과 시 복구 (Re-leveraging)
            self.current_exposure = min(self.exposure_limit, self.current_exposure * 1.1)
            
        return self.current_exposure

    def select_strategy_by_regime(self, regime_info: Dict) -> str:
        """
        시장 국면에 따른 주력 전략 선택
        regime_info structure: { 'probabilities': [bull, bear, sideways], ... }
        """
        probs = regime_info.get('probabilities', [0, 0, 1])
        bull_p, bear_p, side_p = probs
        
        if bull_p > 0.6:
            strategy = "aggressive_momentum"
        elif bear_p > 0.6:
            strategy = "defensive_value"
        else:
            strategy = "neutral_balanced"
            
        logger.info(f"Meta Controller Strategy Switch: {strategy} based on regime {regime_info}")
        return strategy

    def log_control_decision(self, logic: str, decision: str):
        """결정 내역 추적을 위한 로깅"""
        logger.info(f"Control Decision: Logic[{logic}] -> Decision[{decision}]")
