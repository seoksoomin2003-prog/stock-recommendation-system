import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from utils.logger import setup_logger

logger = setup_logger("MonitoringEngine")

class MonitoringEngine:
    """
    성과 및 시스템 품질 모니터링 엔진
    - Rolling Sharpe Ratio 계산 (성과 추적)
    - 성과 저하 감지 (Alert)
    - Max Drawdown 실시간 모니터링
    - 시스템 상태 로깅
    """
    def __init__(self, 
                 sharpe_threshold: float = 0.5, 
                 mdd_limit: float = -0.15):
        self.sharpe_threshold = sharpe_threshold
        self.mdd_limit = mdd_limit

    def calculate_rolling_sharpe(self, 
                                 returns: pd.Series, 
                                 window: int = 63) -> pd.Series:
        """최근 성과 기반 Sharpe Ratio 계산 (63일 = 분기)"""
        rolling_mean = returns.rolling(window=window).mean()
        rolling_std = returns.rolling(window=window).std()
        
        # 연율화 (Daily -> Annual)
        sharpe = (rolling_mean / rolling_std) * np.sqrt(252)
        return sharpe

    def check_performance_degradation(self, 
                                    returns: pd.Series, 
                                    window: int = 21) -> bool:
        """성과 저하 감지 (최근 1개월 성과 기반)"""
        current_sharpe = self.calculate_rolling_sharpe(returns, window=window).iloc[-1]
        
        if current_sharpe < self.sharpe_threshold:
            logger.warning(f"Performance Alert: Current Sharpe ({current_sharpe:.2f}) < Threshold ({self.sharpe_threshold})")
            return True
        return False

    def monitor_mdd(self, returns: pd.Series) -> float:
        """Max Drawdown 모니터링"""
        cum_returns = (1 + returns).cumprod()
        peak = cum_returns.cummax()
        mdd = (cum_returns - peak) / peak
        current_mdd = mdd.iloc[-1]
        
        if current_mdd < self.mdd_limit:
            logger.error(f"Risk Warning: Current MDD ({current_mdd:.2f}) > Limit ({self.mdd_limit})")
            
        return current_mdd

    def log_system_status(self, metrics: Dict[str, float]):
        """시스템 상태 요약 로깅"""
        logger.info(f"System Monitor: Status OK. Metrics: {metrics}")
