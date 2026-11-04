import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from utils.logger import setup_logger

logger = setup_logger("AnalyticsSystems")

class AlphaAttribution:
    """
    수익 기여도 분석(Alpha Attribution) 엔진
    - Factor Contribution
    - Sentiment Contribution
    - Alt Data Contribution
    - Macro Overlay Contribution
    """
    def __init__(self):
        self.contributions_log = pd.DataFrame()

    def attribute_return(self, 
                         ticker_returns: pd.Series, 
                         weights: pd.Series, 
                         alpha_scores: Dict[str, pd.Series]) -> Dict[str, float]:
        """
        포트폴리오 수익을 알파 소스별로 분해
        - 델타(Delta) 가중치 분석 기반
        """
        # 1. Total Daily Return
        total_ret = (ticker_returns * weights).sum()
        
        # 2. 개별 알파별 수익 기여도 추정 (Normalization)
        # 각 알파가 전체 점수에 미치는 비중을 통해 수익을 할당
        contributions = {}
        for alpha_name, scores in alpha_scores.items():
            # 점수의 상대적 강도를 활용하여 수익 기여도 계산 (단순화된 모델)
            # Port_ret_i = total_ret * corr(alpha_i, ticker_returns)
            # 여기선 간략히 가중 평균 점수 기반 분석
            score_contribution = (scores * weights).sum()
            avg_abs_score = scores.abs().mean()
            if avg_abs_score > 0:
                contributions[alpha_name] = (score_contribution / avg_abs_score) * 0.01 # 스케일링
            else:
                contributions[alpha_name] = 0.0
                
        # 3. 로그 기록
        entry = pd.DataFrame([contributions])
        self.contributions_log = pd.concat([self.contributions_log, entry], ignore_index=True)
        
        return contributions

    def get_summary_report(self) -> str:
        """분석 요약 리포트 (텍스트/마크다운 형태)"""
        if self.contributions_log.empty: return "No data recorded."
        
        avg_contri = self.contributions_log.mean()
        report = "--- Alpha Attribution Report ---\n"
        for k, v in avg_contri.items():
            report += f"- {k.capitalize()}: {v:+.4f} (Avg Contribution)\n"
            
        std_contri = self.contributions_log.std()
        report += "\n--- Stability of Contributions ---\n"
        for k, v in std_contri.items():
            report += f"- {k.capitalize()} Stability (Std): {v:.4f}\n"
            
        return report

class RobustnessEngine:
    """
    전략 강건성(Robustness) 검증 엔진
    - 파라미터 미세 조정(Perturbation) 시 성과 불일치 확인
    - Bootstrap 결과 분포 분석
    """
    def __init__(self):
        pass

    def calculate_robustness_score(self, 
                                   base_returns: pd.Series, 
                                   perturbed_returns_list: List[pd.Series]) -> float:
        """
        강건성 점수 산출
        - 점수 = 1 / (1 + 성과 편차의 표준편차)
        - 파라미터가 바뀌어도 성과가 일정할수록 높은 점수
        """
        if not perturbed_returns_list: return 1.0
        
        base_sharpe = self._sharpe(base_returns)
        perturbed_sharpes = [self._sharpe(r) for r in perturbed_returns_list]
        
        sharpe_std = np.std(perturbed_sharpes)
        # 점수 정규화 (0.0 ~ 1.0)
        score = 1.0 / (1.0 + sharpe_std * 5)
        
        logger.info(f"Robustness Score Calculated: {score:.2f} (Sharpe Std: {sharpe_std:.4f})")
        return score

    def _sharpe(self, returns: pd.Series) -> float:
        """연간화된 샤프 지수 (무위험 수익률 0 가정)"""
        if returns.std() == 0 or len(returns) < 2: return 0.0
        return (returns.mean() / returns.std()) * np.sqrt(252)

    def run_perturbation_test(self, 
                             scoring_engine, 
                             meta_alpha_engine,
                             factor_scores, 
                             sentiment_scores, 
                             alt_scores, 
                             volatility: pd.Series,
                             mdd: pd.Series,
                             returns: pd.DataFrame,
                             n_iter: int = 5) -> Dict:
        """매개변수(가중치)를 미세하게 조정하며 결과의 일관성 확인 (실제 리스크 데이터 사용)"""
        logger.info(f"Running Robustness Perturbation Test (n={n_iter}) with Live Risk Data...")
        
        # 1. Base Score 산정 (현재 가중치 및 실제 리스크 반영)
        raw_factor_scores = scoring_engine.calculate(factor_scores)
        base_ensemble = meta_alpha_engine.combine_scores(raw_factor_scores, None, sentiment_scores, alt_scores)
        base_scores = scoring_engine.apply_risk_penalties(base_ensemble, volatility, mdd, returns)
        
        perturbed_scores = []
        original_weights = scoring_engine.weights.copy()
        
        # 2. 가중치에 노이즈 추가 (Perturbation) 및 결과 도출
        for i in range(n_iter):
            perturbed_weights = {k: v * np.random.normal(1.0, 0.05) for k, v in original_weights.items()}
            
            # 임시 가중치 적용하여 점수 재산출
            temp_raw = scoring_engine.calculate(factor_scores, weights=perturbed_weights)
            temp_ensemble = meta_alpha_engine.combine_scores(temp_raw, None, sentiment_scores, alt_scores)
            p_score = scoring_engine.apply_risk_penalties(temp_ensemble, volatility, mdd, returns)
            perturbed_scores.append(p_score)
            
        # 3. 상태 복구
        scoring_engine.weights = original_weights
        
        # 4. 일관성 점수 계산 (변동성 분석)
        all_p = pd.concat(perturbed_scores, axis=1)
        score_stds = all_p.std(axis=1)
        relative_deviation = score_stds.mean() / (base_scores.mean() + 1e-9)
        
        # 강건성 점수 (0~1)
        robust_score = 1.0 / (1.0 + relative_deviation * 20) 
        
        return {
            "robustness_score": robust_score,
            "relative_deviation": relative_deviation,
            "iterations": n_iter
        }
