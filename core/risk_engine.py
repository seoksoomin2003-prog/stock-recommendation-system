import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from utils.logger import setup_logger

logger = setup_logger("RiskEngine")

class RiskEngine:
    """
    리스크 관리 엔진
    - 포트폴리오 VaR (Value at Risk) 계산
    - 포지션별 리스크 기여도 (Risk Contribution) 분석
    - 상관관계 매트릭스 분석
    - 노출도(Exposure) 및 MDD 제한
    """
    def __init__(self):
        from utils.config import RISK_MANAGEMENT_SETTINGS
        self.settings = RISK_MANAGEMENT_SETTINGS
        self.confidence_level = self.settings.get("var_confidence_level", 0.95)

    def calculate_portfolio_var(self, 
                                weights: pd.Series, 
                                returns: pd.DataFrame,
                                method: str = 'historical') -> float:
        """
        포트폴리오 VaR 계산 (Historical vs Parametric)
        """
        portfolio_returns = returns @ weights
        
        if method == 'historical':
            # Historical Simulation: 과거 수익률 분포의 백분위수 사용
            alpha = 1 - self.confidence_level
            var = -np.percentile(portfolio_returns.dropna(), alpha * 100)
            return max(0.0, var)
        else:
            # Parametric: 공분산 기반
            cov_matrix = returns.cov()
            portfolio_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
            z_score = 1.645 if self.confidence_level == 0.95 else 2.326
            return portfolio_vol * z_score

    def calculate_risk_contribution(self, 
                                   weights: pd.Series, 
                                   returns: pd.DataFrame) -> pd.Series:
        """
        각 종목별 리스크 기여도 (Percentage of Total Risk)
        """
        cov_matrix = returns.cov()
        p_vol = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
        if p_vol == 0: return pd.Series(0, index=weights.index)
        
        marginal_contribution = np.dot(cov_matrix, weights) / p_vol
        risk_contribution = weights * marginal_contribution
        
        # 전체 리스크(Volatility) 대비 기여 비중으로 변환
        return risk_contribution / p_vol

    def calculate_var(self, portfolio_returns: pd.Series) -> float:
        """
        [NEW] 포트폴리오 수익률 이력을 기반으로 한 실시간 VaR 산출
        - 최근 60일 데이터 기준 95% 신뢰 수준의 일일 VaR 계산
        """
        if len(portfolio_returns) < 5: return 0.0 # 데이터 부족 시 0 반환
        
        # 최근 60개 데이터만 사용 (최신 변동성 반영)
        recent_returns = portfolio_returns.tail(60)
        alpha = 1 - self.confidence_level
        
        # 95% 신뢰구간의 일일 예상 손실액(VaR)
        var = -np.percentile(recent_returns.dropna(), alpha * 100)
        return max(0.0, var)

    def check_kill_switch(self, current_mdd: float) -> bool:
        """
        [NEW] 최대 낙폭(MDD) 기반 시스템 자동 중단 여부 판단
        - MDD가 max_drawdown_limit(기본 10%)를 초과하면 True 반환
        """
        limit = self.settings.get("max_drawdown_limit", 0.10)
        if abs(current_mdd) >= limit:
            logger.critical(f"KILL SWITCH ACTIVATED: Current MDD {current_mdd:.2%} exceeds limit {limit:.2%}")
            return True
        return False

    def get_exposure_scaling_factor(self, current_var: float) -> float:
        """
        VaR 한도 초과 시 노출도 축소 비율 산출
        """
        limit = self.settings.get("max_allowed_daily_var", 0.02)
        if current_var > limit:
            # 선형 축소: 한도 / 현재위험
            scaling_factor = limit / current_var
            # 극단적 상황(2배 초과 등) 시 추가 안전 마진 적용
            if current_var > limit * 2:
                scaling_factor *= self.settings.get("emergency_reduction_ratio", 0.5)
            
            logger.warning(f"EXPOSURE SCALING: VaR {current_var:.2%} > Limit {limit:.2%}. Scaling={scaling_factor:.2f}")
            return max(0.0, scaling_factor)
        return 1.0

    def get_correlation_matrix(self, returns: pd.DataFrame) -> pd.DataFrame:
        """종목 간 상관관계 분석"""
        return returns.corr()
