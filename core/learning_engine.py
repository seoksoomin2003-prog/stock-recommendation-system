import json
import pandas as pd
import numpy as np
from typing import Dict, List
from utils.config import LEARNING_RATE, CLIPPING_VALUE
from utils.logger import setup_logger

logger = setup_logger("LearningEngine")

class LearningEngine:
    """
    성과 기반 팩터 가중치 최적화 엔진
    가중치 업데이트 로직: w = w + lr * error * factor_value
    """
    def __init__(self, lr: float = LEARNING_RATE, clip: float = CLIPPING_VALUE):
        self.lr = lr
        self.clip = clip

    def update_weights(self, 
                       current_weights: Dict[str, float], 
                       predicted_scores: pd.Series, 
                       actual_returns: pd.Series, 
                       factor_matrix: pd.DataFrame) -> Dict[str, float]:
        """
        예측과 실제 결과를 비교하여 가중치를 업데이트함.
        """
        new_weights = current_weights.copy()
        
        # 실제 수익률과 예측 점수 간의 상관관계 기반 오차 계산
        # 랭킹 기반 학습 (상위 종목과 하위 종목의 성과 비교)
        top_indices = predicted_scores.nlargest(len(predicted_scores)//5).index
        bottom_indices = predicted_scores.nsmallest(len(predicted_scores)//5).index
        
        top_performance = actual_returns.loc[top_indices].mean()
        bottom_performance = actual_returns.loc[bottom_indices].mean()
        
        error = top_performance - bottom_performance
        
        for factor in new_weights.keys():
            if factor in factor_matrix.columns:
                # 팩터 값의 강도와 오차를 결합하여 업데이트량 결정
                factor_avg = factor_matrix[factor].mean()
                delta = self.lr * error * factor_avg
                
                # 과적합 방지를 위한 Clipping
                delta = np.clip(delta, -self.clip, self.clip)
                
                new_weights[factor] += delta
        
        # 가중치 정규화 (합이 1이 되도록)
        total_weight = sum(new_weights.values())
        if total_weight > 0:
            new_weights = {k: v / total_weight for k, v in new_weights.items()}
            
        logger.info(f"Weights updated: {new_weights}")
        return new_weights

    def save_weights(self, weights: Dict[str, float], filepath: str):
        with open(filepath, 'w') as f:
            json.dump(weights, f)
        logger.info(f"Weights saved to {filepath}")

    def load_weights(self, filepath: str) -> Dict[str, float]:
        try:
            with open(filepath, 'r') as f:
                weights = json.load(f)
            logger.info(f"Weights loaded from {filepath}")
            return weights
        except FileNotFoundError:
            logger.error(f"Weights file not found: {filepath}")
            return None
