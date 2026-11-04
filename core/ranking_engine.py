import pandas as pd
import numpy as np
from typing import List, Union, Tuple
from utils.logger import setup_logger

logger = setup_logger("RankingEngine")

class RankingEngine:
    """
    종목 간 상대적 알파를 강화하는 랭킹 엔진
    - Percentile Ranking
    - Z-score Standardizing
    - Cross-sectional Scaling
    - Long-Short Universe Setup
    """
    def __init__(self):
        pass

    def get_percentile_rank(self, scores: pd.Series) -> pd.Series:
        """
        각 종목 점수를 백분위로 변환 (0 ~ 1)
        """
        if scores.empty: return scores
        return scores.rank(pct=True)

    def get_z_score(self, scores: pd.Series) -> pd.Series:
        """
        Z-score 정규화 (전체 시장 대비 상대적 위치)
        """
        import numpy as np
        if scores.isna().all():
            return scores
        if scores.empty or scores.std() == 0 or np.isnan(scores.std()) or len(scores) <= 1:
            return pd.Series(0.0, index=scores.index)
        return (scores - scores.mean()) / scores.std()

    def apply_cross_sectional_standardization(self, factor_df: pd.DataFrame) -> pd.DataFrame:
        """
        대규모 종목 처리를 위한 벡터화 연산 기반 교차 섹션 표준화
        """
        # 각 팩터별로 Z-score 적용
        return factor_df.apply(lambda x: self.get_z_score(x), axis=0)

    def construct_long_short_portfolio(self, 
                                     scores: pd.Series, 
                                     top_pct: float = 0.1, 
                                     bottom_pct: float = 0.1) -> Tuple[List[str], List[str]]:
        """
        상위 n% (Long) 및 하위 n% (Short) 종목 선정
        """
        if scores.empty: return [], []
        
        num_long = max(1, int(len(scores) * top_pct))
        num_short = max(1, int(len(scores) * bottom_pct))
        
        long_candidates = scores.nlargest(num_long).index.tolist()
        short_candidates = scores.nsmallest(num_short).index.tolist()
        
        logger.info(f"Long-Short Universe Setup: Long({len(long_candidates)}), Short({len(short_candidates)})")
        return long_candidates, short_candidates

    def scale_to_unit_exposure(self, scores: pd.Series) -> pd.Series:
        """
        포트폴리오 총 노출도를 1(또는 특정 단위)로 스케일링
        """
        if scores.empty: return scores
        abs_sum = scores.abs().sum()
        if abs_sum == 0: return scores
        return scores / abs_sum

    def calculate_model_rank_e(self, candidates: List[dict], capital: float) -> List[dict]:
        """
        MODEL_RANK_E: Capital-aware composite ranking model (P6).
        Combines Alpha (WHAT) and Entry Readiness (WHEN), while adjusting for Volatility, Confidence, and Liquidity.
        """
        if not candidates:
            return []
            
        for c in candidates:
            alpha = c.get('alpha', 0.0)
            entry_readiness = c.get('entry_readiness', 0.0)
            volatility = c.get('volatility', 0.02)
            confidence = c.get('confidence', 0.9)
            liquidity = c.get('liquidity_score', 1.0)
            
            # Base composite: 60% Alpha, 40% Entry Timing
            base_score = (alpha * 0.6) + (entry_readiness * 0.4)
            
            # Adjustments
            # Penalty for high volatility (if unconfident)
            vol_penalty = volatility * (1 - confidence)
            
            # Liquidity multiplier
            liq_multiplier = min(1.0, liquidity)
            
            # Capital awareness: Penalize if one share takes up a massive portion of the portfolio
            capital_penalty = 0.0
            price = c.get('close', 1e9)
            if capital > 0 and price > (capital * 0.1):
                capital_penalty = 0.1
                
            c['combined_score'] = (base_score * liq_multiplier) - vol_penalty - capital_penalty
            
        return sorted(candidates, key=lambda x: x.get('combined_score', 0.0), reverse=True)
