import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Union
from utils.logger import setup_logger

logger = setup_logger("PortfolioEngine")

class PortfolioEngine:
    """
    포트폴리오 구성 및 가중치 최적화 엔진
    - Softmax-weighted (가중치 ∝ exp(Score/T))
    - Score-weighted (가중치 ∝ 점수)
    - Risk Parity (가중치 ∝ 1 / Volatility)
    - Sector Exposure 제한
    """
    def __init__(self, method: Optional[str] = None):
        self.method = method

    def calculate_weights(self, 
                           scores: pd.Series, 
                           method: Optional[str] = None,
                           temperature: Optional[float] = None,
                           volatility: Optional[pd.Series] = None,
                           sectors: Optional[pd.Series] = None) -> pd.Series:
        """
        [CONVICTION-BASED] 다중 전략 가중치 산출 (Equal Weight 완전 배제)
        - Temperature-scaled Softmax (신호 강도 반영)
        - Risk Parity (자본을 리스크에 균등하게 배분)
        - Entropy 기반 집중도 로깅
        """
        from utils.config import PORTFOLIO_SETTINGS
        if scores.empty: return scores
        
        # 1. 시팅 및 메타 매개변수 우선순위 결정 (Override > Config)
        # Default: softmax-weighted
        method = method or self.method or PORTFOLIO_SETTINGS.get("method", "softmax-weighted")
        temperature = temperature or PORTFOLIO_SETTINGS.get("temperature", 0.5)
        threshold = PORTFOLIO_SETTINGS.get("min_score_threshold", 40.0)
        min_assets = PORTFOLIO_SETTINGS.get("min_assets_count", 5)
        
        # 2. 저점수 컷오프 (Tiered Cutoff) 및 최소 종목 수 보장 (Guardrail)
        filtered_scores = scores[scores >= threshold]
        
        # Guardrail: 컷오프 이후 종목이 너무 적으면 상위 N개 강제 유지
        if len(filtered_scores) < min_assets:
            filtered_scores = scores.sort_values(ascending=False).head(min_assets)
            logger.info(f"Cutoff too strict. Forced guarding top {min_assets} assets.")
        
        # 3. 가중치 산출
        # [수정] Risk Parity 옵션 지원 추가 (알파 보존 원칙)
        if method in ['softmax', 'softmax-weighted', 'equal-weight', 'equal', '1/N']:
            if method in ['equal-weight', 'equal', '1/N']:
                logger.warning(f"Equal Weighting ({method}) is FORBIDDEN. Overriding with 'softmax-weighted'.")
            
            # Numerical Stability Softmax
            shifted_scores = filtered_scores / temperature
            exp_scores = np.exp(shifted_scores - shifted_scores.max())
            weights = exp_scores / exp_scores.sum()
            
        elif method == 'risk-parity':
            # Risk Parity: 자산별 리스크(Volatility)를 균등 분배
            if volatility is None or volatility.empty:
                logger.warning("Volatility data missing for Risk Parity. Falling back to Softmax.")
                shifted_scores = filtered_scores / temperature
                exp_scores = np.exp(shifted_scores - shifted_scores.max())
                weights = exp_scores / exp_scores.sum()
            else:
                # 룩백 기간 동안의 변동성 타겟팅 (Inverse Volatility)
                vols = volatility.reindex(filtered_scores.index).fillna(volatility.median())
                inv_vol = 1.0 / (vols + 1e-9)
                weights = inv_vol / inv_vol.sum()
                logger.info(f"Risk Parity Applied (Inverse Volatility) for {len(weights)} assets.")
                
        elif method == 'linear':
            weights = filtered_scores / filtered_scores.sum()
        else:
            # [Institutional Fallback] 정의되지 않은 모드는 무조건 Softmax로 처리
            logger.warning(f"Invalid method '{method}'. Falling back to softmax-weighted.")
            shifted_scores = filtered_scores / temperature
            exp_scores = np.exp(shifted_scores - shifted_scores.max())
            weights = exp_scores / exp_scores.sum()

        # 4. 집중도 로깅
        entropy = -np.sum(weights * np.log(weights + 1e-9))
        max_entropy = np.log(len(weights))
        conviction_idx = 1 - (entropy / (max_entropy + 1e-9))
        logger.info(f"Method: {method} | Conviction Index: {conviction_idx:.2f} | Assets: {len(weights)}")

        # 3. 제약 조건 반영 (Concentration & Sector)
        max_weight = PORTFOLIO_SETTINGS.get("max_individual_weight", 0.25)
        weights = self._apply_concentration_limit(weights, max_limit=max_weight)
        
        if sectors is not None:
            max_sector = PORTFOLIO_SETTINGS.get("max_sector_exposure", 0.40)
            weights = self._apply_sector_constraints(weights, sectors, limit=max_sector)
            
        # 최종 정규화
        return weights / weights.sum()

    def _apply_concentration_limit(self, weights: pd.Series, max_limit: float = 0.20) -> pd.Series:
        """
        개별 종목 비중이 max_limit을 넘지 않도록 반복 조정 (Clip & Redistribute)
        """
        temp_weights = weights.copy()
        for _ in range(10): # 최대 10회 반복으로 수렴 유도
            over_limit = temp_weights > max_limit
            if not over_limit.any():
                break
            
            excess = temp_weights[over_limit].sum() - (over_limit.sum() * max_limit)
            temp_weights[over_limit] = max_limit
            
            # 남은 비중을 한도 미만 종목들에게 비례 배분
            under_limit = ~over_limit
            if under_limit.any():
                redistribution_ratio = excess / temp_weights[under_limit].sum()
                temp_weights[under_limit] *= (1 + redistribution_ratio)
            else:
                # 모든 종목이 한도를 넘는 불가능한 상황
                break
        return temp_weights

    def _apply_sector_constraints(self, 
                                 weights: pd.Series, 
                                 sectors: pd.Series,
                                 limit: float = 0.40) -> pd.Series:
        """
        특정 섹터의 총 가중치가 한도를 넘지 않도록 조정
        """
        # 현재 섹터별 노출도
        portfolio_sectors = sectors.loc[weights.index]
        sector_exposure = weights.groupby(portfolio_sectors).sum()
        
        for sector, exposure in sector_exposure.items():
            if exposure > limit:
                # 해당 섹터 내 종목 가중치 일괄 축소
                scale_factor = limit / exposure
                weights[portfolio_sectors == sector] *= scale_factor
                
        return weights
