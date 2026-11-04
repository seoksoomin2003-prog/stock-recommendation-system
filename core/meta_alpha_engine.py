import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from utils.config import META_ALPHA_SETTINGS, HYBRID_WEIGHTS
from utils.logger import setup_logger

logger = setup_logger("MetaAlphaEngine")

class MetaAlphaEngine:
    """
    메타 알파(Meta-Alpha) 앙상블 엔진
    - 알파 소스별(Factor, Sentiment, AltData) 성과 추적
    - 성과 기반 동적 가중치(Dynamic Weighting) 재계산
    - 부진한 알파 노출 축소 (Alpha Drift Control)
    """
    def __init__(self, config: Dict = META_ALPHA_SETTINGS):
        self.config = config
        self.current_weights = HYBRID_WEIGHTS.copy()
        # [수정] Mock 데이터 제거: 실제 운영 시 빈 리스트로 시작하여 학습
        self.performance_history = {
            "factor": [],
            "fundamental": [], # [NEW]
            "sentiment": [],
            "alt_data": []
        }

    def track_performance(self, alpha_name: str, new_perf: float):
        """본격적인 알파 성과 기록 (Rolling Window 유지)"""
        if alpha_name in self.performance_history:
            self.performance_history[alpha_name].append(new_perf)
            # 윈도우 크기 유지 (config 반영 권장)
            max_len = self.config.get("history_lookback", 20)
            if len(self.performance_history[alpha_name]) > max_len:
                self.performance_history[alpha_name].pop(0)

    def calculate_adaptive_weights(self) -> Dict[str, float]:
        """
        최근 성과(평균 IC) 기반으로 가중치를 동적으로 재계산
        - [수정] Progressive Learning 적용: 데이터 부족 시에도 점진적으로 학습 반영
        """
        # 0. 초기 상태 대응: 샘플 수에 따른 신뢰도(alpha) 기반 Shrinkage 적용
        min_samples = self.config.get("min_learning_samples", 4)
        history_lengths = [len(v) for v in self.performance_history.values()]
        
        # 데이터가 아예 없는 경우 (초기 Cycle)
        if not history_lengths or max(history_lengths) == 0:
            return HYBRID_WEIGHTS

        # Progressive Alpha: 샘플이 쌓일수록 학습 비중 상향 (1개=25%, 4개=100%)
        current_samples = max(history_lengths)
        learning_alpha = min(1.0, current_samples / min_samples)
        
        # 1. 성과 계산 (평균 IC)
        avg_perfs = {k: np.mean(v[-4:]) if v else 0.0 for k, v in self.performance_history.items()}
        total_perf = sum(abs(v) for v in avg_perfs.values())
        
        # 성과 데이터가 비정상(모두 0)인 경우
        if total_perf == 0:
            return HYBRID_WEIGHTS
            
        # 2. 성과 비례 가중치 산출 (Target Weight)
        target_weights = {k: v / total_perf for k, v in avg_perfs.items()}
        
        # 3. Drift Control (성과 급락 시 패널티)
        for k, perf in avg_perfs.items():
            if perf < self.config['drift_threshold']:
                logger.warning(f"Drift Detected in {k}: performance {perf:.4f} < {self.config['drift_threshold']}. Reducing weight.")
                target_weights[k] *= 0.5
        
        # 4. [신규] Progressive Shrinkage 적용
        # Weight = (1 - alpha) * HYBRID_WEIGHTS + alpha * Target_Weights
        shrunk_weights = {}
        for k in HYBRID_WEIGHTS.keys():
            shrunk_weights[k] = (1 - learning_alpha) * HYBRID_WEIGHTS[k] + \
                                learning_alpha * target_weights.get(k, HYBRID_WEIGHTS[k])
        
        # 5. 제약 조건 반영 (Min/Max Weight) 및 Smoothing 적용
        new_weights = {}
        for k, w in shrunk_weights.items():
            # Smoothing: (1-decay) * current + decay * shrunk_target
            clamped_w = np.clip(w, self.config['min_weight'], self.config['max_weight'])
            new_weights[k] = (1 - self.config['decay_factor']) * self.current_weights.get(k, HYBRID_WEIGHTS[k]) + \
                             self.config['decay_factor'] * clamped_w
                             
        # 4. 합계 1.0 정규화
        total_w = sum(new_weights.values())
        final_weights = {k: v / total_w for k, v in new_weights.items()}
        
        self.current_weights = final_weights
        logger.info(f"Meta Alpha Weights Updated: {final_weights}")
        return final_weights

    def _apply_strategy_bias(self, weights: Dict[str, float], strategy: str) -> Dict[str, float]:
        """
        [NEW] 전략적 편향(Strategic Bias) 적용
        - MetaController의 결정에 따라 특정 알파 소스의 가중치를 상향 조정
        """
        biased_weights = weights.copy()
        
        # 1. 공격적 모멘텀 전략 (Bull Regime)
        if strategy == "aggressive_momentum":
            # 센티먼트 및 대체 데이터(트렌드) 가중치 강화 (+15~20%)
            biased_weights['sentiment'] += 0.15
            biased_weights['alt_data'] += 0.05
            biased_weights['factor'] -= 0.20
            
        # 2. 방어적 가치 전략 (Bear Regime)
        elif strategy == "defensive_value":
            # 팩터 및 펀더멘탈(안정적 기초지표) 가중치 강화
            biased_weights['factor'] += 0.15
            biased_weights['fundamental'] += 0.10
            biased_weights['sentiment'] -= 0.10
            biased_weights['alt_data'] -= 0.15
            
        # 3. 중립/밸런스 전략 (Neutral/Sideways)
        else:
            # 중립 상태에서는 학습된(Adaptive) 가중치를 그대로 사용
            pass
            
        # 가중치 제약 조건 (Min/Max) 재적용 및 정규화
        final_biased = {}
        for k, w in biased_weights.items():
            final_biased[k] = np.clip(w, self.config.get('min_weight', 0.05), self.config.get('max_weight', 0.80))
            
        total_w = sum(final_biased.values())
        return {k: v / total_w for k, v in final_biased.items()}

    def combine_scores(self, 
                       factor_scores: pd.Series, 
                       fundamental_scores: Optional[pd.Series] = None,
                       sentiment_scores: Optional[pd.Series] = None, 
                       alt_data_scores: Optional[pd.Series] = None,
                       strategy: str = "neutral_balanced") -> pd.Series:
        """
        [수정] 동적 학습 가중치에 전략적 편향(Strategy Bias)을 결합하여 최종 점수 산출
        - [P6-16] Candidate-level dynamic weight redistribution for missing optional factors.
        """
        # 1. 성과 기반 적응형 가중치 산출
        adaptive_weights = self.calculate_adaptive_weights()
        
        # 2. 메타 컨트롤러 전략 기반 편향 적용
        final_weights = self._apply_strategy_bias(adaptive_weights, strategy)
        
        logger.info(f"Final Ensemble Declared Weights (Strategy: {strategy}): {final_weights}")
        
        # Default empty/neutral series for optional inputs
        if fundamental_scores is None:
            fundamental_scores = pd.Series(np.nan, index=factor_scores.index)
        if sentiment_scores is None:
            sentiment_scores = pd.Series(np.nan, index=factor_scores.index)
        if alt_data_scores is None:
            alt_data_scores = pd.Series(np.nan, index=factor_scores.index)

        final_score = pd.Series(np.nan, index=factor_scores.index)
        provenance = {}

        for ticker in factor_scores.index:
            # 1. Check data availability for this candidate
            f_score = factor_scores.get(ticker, np.nan)
            fund_score = fundamental_scores.get(ticker, np.nan)
            sent_score = sentiment_scores.get(ticker, np.nan)
            alt_score = alt_data_scores.get(ticker, np.nan)

            available_factors = []
            unavailable_factors = []
            runtime_weights = {}

            # Core factor
            if not pd.isna(f_score):
                available_factors.append("factor")
                runtime_weights["factor"] = final_weights.get("factor", 0.5)
            else:
                unavailable_factors.append("factor")
                runtime_weights["factor"] = 0.0

            # Optional factors
            for name, score, w_key in [("fundamental", fund_score, "fundamental"), 
                                       ("sentiment", sent_score, "sentiment"), 
                                       ("alt_data", alt_score, "alt_data")]:
                if not pd.isna(score):
                    available_factors.append(name)
                    runtime_weights[name] = final_weights.get(w_key, 0.0)
                else:
                    unavailable_factors.append(name)
                    runtime_weights[name] = 0.0

            total_valid_weight = sum(runtime_weights.values())

            # 2. Minimum Effective Coverage Check (50%)
            # Also must include 'factor' because it's the core model base.
            if total_valid_weight < 0.5 or "factor" not in available_factors:
                final_score[ticker] = np.nan
                effective_weights = {k: 0.0 for k in runtime_weights}
            else:
                # 3. Proportionally normalize weights
                effective_weights = {k: v / total_valid_weight for k, v in runtime_weights.items()}
                
                s = 0.0
                if "factor" in available_factors: s += f_score * effective_weights["factor"]
                if "fundamental" in available_factors: s += fund_score * effective_weights["fundamental"]
                if "sentiment" in available_factors: s += sent_score * effective_weights["sentiment"]
                if "alt_data" in available_factors: s += alt_score * effective_weights["alt_data"]
                
                final_score[ticker] = s

            # 4. Store Candidate Provenance
            provenance[ticker] = {
                "ticker": ticker,
                "declared_weights": final_weights.copy(),
                "effective_runtime_weights": effective_weights,
                "available_factors": available_factors,
                "unavailable_factors": unavailable_factors,
                "effective_weight_coverage": float(total_valid_weight)
            }

        final_score.attrs["provenance"] = provenance
        return final_score
