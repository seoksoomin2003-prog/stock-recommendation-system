import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from utils.config import DEFAULT_FACTOR_WEIGHTS
from utils.logger import setup_logger

logger = setup_logger("ScoringEngine")

class ScoringEngine:
    """
    고급 스코어링 엔진 (V2)
    - 멀티팩터 가중 결합
    - 리스크 조정 점수 (Risk-adjusted score)
    - Volatility, MDD, Negative Skewness 페널티 적용
    """
    def __init__(self, weights: Dict[str, float] = None):
        # 초기화 시 가중치 정규화 보장
        self.weights = self._normalize_weights(weights or DEFAULT_FACTOR_WEIGHTS)

    def _normalize_weights(self, weights_dict: Dict[str, float]) -> Dict[str, float]:
        """
        가중치 합이 1이 되도록 정규화하고, 비정상 상태(total=0) 시 기본값으로 복구
        """
        total = sum(weights_dict.values())
        
        # 1. 가중치 합이 0인 경우 (비정상) -> 기본값으로 강제 복구
        if total == 0:
            logger.warning("Factor weights sum to zero! Falling back to DEFAULT_FACTOR_WEIGHTS to prevent NaN scores.")
            return DEFAULT_FACTOR_WEIGHTS.copy()
            
        # 2. 가중치 합이 1이 아닌 경우 (부정당) -> 정규화 수행
        if abs(total - 1.0) > 1e-9:
            logger.warning(f"Factor weights sum to {total:.2f} (not 1.0). Normalizing weights.")
            return {k: v / total for k, v in weights_dict.items()}
            
        return weights_dict.copy()

    def calculate(self, 
                  factor_matrix: pd.DataFrame, 
                  weights: Optional[Dict[str, float]] = None) -> pd.Series:
        """기존 팩터 가중 합산 점수 (Dynamic Weights 지원)"""
        # Dynamic weights 사용 시에도 정규화 보장 (제공된 가중치가 없으면 기본 가중치 사용)
        active_weights = self._normalize_weights(weights) if weights is not None else self.weights
        
        # [NEW] 선택된 가중치 로깅 (전략 반영 확인용)
        weight_str = ", ".join([f"{k}: {v:.2f}" for k, v in active_weights.items()])
        logger.info(f"Scoring with Effective Weights: {weight_str}")
        
        total_score = pd.Series(0.0, index=factor_matrix.index)
        for idx in factor_matrix.index:
            row = factor_matrix.loc[idx]
            available_factors = {f: active_weights[f] for f in active_weights 
                                 if f in row and not pd.isna(row[f])}
            
            if not available_factors:
                total_score.loc[idx] = np.nan
                continue
                
            total_w = sum(available_factors.values())
            if total_w > 0:
                norm_w = {k: v / total_w for k, v in available_factors.items()}
            else:
                norm_w = {k: 1.0 / len(available_factors) for k in available_factors}
                
            score_val = 0.0
            for f, w in norm_w.items():
                score_val += row[f] * w
            total_score.loc[idx] = score_val
            
        return total_score

    def apply_risk_penalties(self, 
                             raw_scores: pd.Series, 
                             volatility: pd.Series, 
                             mdd: pd.Series,
                             returns: pd.DataFrame) -> pd.Series:
        """
        리스크 요인을 반영한 점수 조정 (Adaptive Deduction Model)
        """
        from utils.config import TAIL_RISK_SETTINGS
        
        # 1. Adaptive Lambda (시장 변동성에 따른 페널티 강도 조절)
        lambda_base = TAIL_RISK_SETTINGS.get("risk_score_lambda", 20.0)
        market_vol = volatility.mean()
        # 시장 변동성이 평소보다 높으면 페널티를 더 강화 (1.0 + 시장 변동성 비율)
        lambda_adaptive = lambda_base * (1 + market_vol * 5) 
        
        # 2. 개별 리스크 컴포넌트 산출 (상대 범위 정규화)
        # Volatility Penalty
        vol_p = volatility / (volatility.median() + 1e-9)
        
        # MDD Penalty (하방 리스크 강조를 위해 가중치 2.0배)
        mdd_p = mdd.abs() / (mdd.abs().median() + 1e-9)
        
        # Negative Skewness Penalty
        skew = returns.skew()
        skew_p = skew.apply(lambda x: abs(x) if x < 0 else 0)
        
        # 3. Tail Risk (극단적 위험) 가중 처벌
        tail_threshold = TAIL_RISK_SETTINGS.get("tail_risk_percentile", 0.90)
        vol_limit = volatility.quantile(tail_threshold)
        mdd_limit = mdd.abs().quantile(tail_threshold)
        
        # 상위 10% 위험 종목은 페널티를 2배로 강화
        tail_multiplier = volatility.apply(lambda x: 2.0 if x > vol_limit else 1.0) * \
                          mdd.apply(lambda x: 2.0 if abs(x) > mdd_limit else 1.0)
        
        # 4. 통합 페널티 구조
        # Penalty = (Vol + 2*MDD + 1.5*Skew) * TailMultiplier
        total_penalty = (vol_p + 2.0 * mdd_p + 1.5 * skew_p) * tail_multiplier
        
        # 5. 최종 점수 산출 (Deduction 모델)
        # Adjusted = Raw - (Lambda * Penalty)
        adjusted_score = raw_scores - (lambda_adaptive * total_penalty)
        
        # 6. 후처리 (0 이하 클리핑 및 100점 만점 스케일링 유지)
        adjusted_score = adjusted_score.clip(lower=0)
        
        # 점수가 모두 0인 경우 방지
        if adjusted_score.max() > 0:
            adjusted_score = (adjusted_score / adjusted_score.max()) * 100
            
        logger.info(f"Risk Scored (Adaptive Lambda: {lambda_adaptive:.2f}) | Max Penalty: {total_penalty.max():.2f}")
        return adjusted_score

    def select_top_candidates(self, scores: pd.Series, top_pct: float = 0.2) -> List[str]:
        if scores.empty: return []
        num_to_select = max(1, int(len(scores) * top_pct))
        return scores.sort_values(ascending=False).head(num_to_select).index.tolist()

    def update_weights(self, new_weights: Dict[str, float]):
        """새로운 가중치 업데이트 및 검증"""
        self.weights.update(new_weights)
        self.weights = self._normalize_weights(self.weights)
