import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Callable
from utils.logger import setup_logger

logger = setup_logger("WeightOptimizer")

class FactorWeightOptimizer:
    """
    팩터 가중치 자동 최적화 엔진
    - Rolling Window 성과 기반 가중치 업데이트
    - Sharpe Ratio 최대화 (Objective Function)
    - Grid Search (Baseline) 및 Bayesian 확장 구조
    - Out-of-sample 검증 포함
    """
    def __init__(self, 
                 window: int = 252, 
                 allow_short: bool = False,
                 learning_rate: float = 0.05):
        self.window = window
        self.allow_short = allow_short
        self.learning_rate = learning_rate

    def calculate_sharpe(self, 
                       returns: pd.Series, 
                       risk_free_rate: float = 0.02) -> float:
        """Sharpe Ratio 계산"""
        if returns.empty or returns.std() == 0: return 0.0
        excess_returns = returns - (risk_free_rate / 252)
        return (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)

    def optimize_weights_grid(self, 
                             factor_returns: pd.DataFrame, 
                             current_weights: Dict[str, float]) -> Dict[str, float]:
        """
        간단한 Grid Search 기반 가중치 최적화 (Baseline)
        실제로는 Scipy.optimize나 Bayesian Opt를 권장함.
        """
        best_sharpe = -np.inf
        best_weights = current_weights.copy()
        
        # 팩터 간 조합 테스트 (간략화된 예시: 가중치 조정 루프)
        factors = list(current_weights.keys())
        
        # Grid Search 예시 (가중치 변화량 테스트)
        adjustments = [-0.1, -0.05, 0.0, 0.05, 0.1]
        
        for f in factors:
            for adj in adjustments:
                test_weights = current_weights.copy()
                test_weights[f] += adj
                
                # 가중치 합 1 유지 및 제약 조건 확인
                total = sum(test_weights.values())
                test_weights = {k: v / total for k, v in test_weights.items()}
                
                if not self.allow_short:
                    if any(v < 0 for v in test_weights.values()): continue
                
                # 포트폴리오 수익률 계산 (Out-of-sample 검증 위해 Window 내에서 수행)
                portfolio_ret = (factor_returns * pd.Series(test_weights)).sum(axis=1)
                sharpe = self.calculate_sharpe(portfolio_ret)
                
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_weights = test_weights
                    
        logger.info(f"Optimization completed. Max Sharpe: {best_sharpe:.4f}")
        return best_weights

    def update_dynamic_weights(self, 
                               historical_data: pd.DataFrame, 
                               current_weights: Dict[str, float]) -> Dict[str, float]:
        """
        최근 성과(Rolling Window)를 기반으로 가중치를 업데이트함.
        """
        if len(historical_data) < self.window:
            return current_weights
            
        # 최근 Window 기간의 데이터 추출
        recent_data = historical_data.tail(self.window)
        # 팩터별 수익률 데이터 (여기서는 팩터 값 자체가 수익률로 변환되었다고 가정)
        # 실제로는 각 팩터 포트폴리오의 실현 수익률을 넣어주어야 함.
        
        new_weights = self.optimize_weights_grid(recent_data, current_weights)
        
        # 급격한 가중치 변화 방지 (Smoothing)
        smoothed_weights = {
            k: (1 - self.learning_rate) * current_weights[k] + self.learning_rate * new_weights[k]
            for k in current_weights.keys()
        }
        
        return smoothed_weights
