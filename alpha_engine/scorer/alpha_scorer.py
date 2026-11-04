import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from utils.logger import setup_logger

logger = setup_logger("AlphaScorer")

class AlphaScorer:
    """
    Scoring Engine Layer
    - Calculates the multi-source alpha score.
    - Implements Dynamic Weighting based on market volatility.
    - Applies Sector Adjustment logic.
    """
    def __init__(self):
        # Baseline Institutional Weights (Neutral Regime)
        self.base_weights = {
            "sentiment": 0.25,
            "buzz": 0.20,
            "trends": 0.20,
            "insider": 0.25,
            "macro": 0.10
        }

    def calculate_alpha_score(self, 
                               signals: pd.DataFrame, 
                               volatility: float, 
                               sector_data: Optional[pd.DataFrame] = None) -> pd.Series:
        """
        Main score calculation logic.
        signals: DataFrame with columns ['sentiment', 'buzz', 'trends', 'insider', 'macro']
        volatility: Market volatility (e.g., VIX or rolling std)
        """
        if signals.empty:
            return pd.Series()

        # 1. Dynamic Weighting (Vol-Aware)
        weights = self._get_dynamic_weights(volatility)
        
        # 2. Weighted Sum
        # alpha_score = Σ(w_i * signal_i)
        alpha_scores = pd.Series(0, index=signals.index)
        for col, weight in weights.items():
            if col in signals.columns:
                alpha_scores += signals[col] * weight
            else:
                logger.warning(f"Signal column {col} missing during scoring.")

        # 3. Sector Adjustment
        # final_score = 0.7 * indiv + 0.3 * sector_leader
        if sector_data is not None and 'sector' in signals.columns:
            alpha_scores = self._apply_sector_adjustment(alpha_scores, signals['sector'], sector_data)

        # 4. Standardizing Final Score to [-1, 1]
        alpha_scores = alpha_scores.clip(-1.0, 1.0)
        
        logger.info(f"Alpha scoring complete. Avg Score: {alpha_scores.mean():+.4f} | Vol Regime: {'High' if volatility > 0.02 else 'Low'}")
        return alpha_scores

    def _get_dynamic_weights(self, volatility: float) -> Dict[str, float]:
        """
        Institutional Dynamic Weighting:
        - vol > threshold: Sentiment and Macro weights increase (Fear/Greed/Event driven).
        - vol <= threshold: Trends and Insider weights increase (Mean reversion/Alpha search).
        """
        weights = self.base_weights.copy()
        
        # High Volatility Regime (> 2% daily or high VIX)
        if volatility > 0.02:
            weights['sentiment'] += 0.10
            weights['macro'] += 0.05
            weights['trends'] -= 0.10
            weights['insider'] -= 0.05
        # Low Volatility Regime
        else:
            weights['trends'] += 0.10
            weights['insider'] += 0.05
            weights['sentiment'] -= 0.10
            weights['macro'] -= 0.05

        # Normalize to ensure sum = 1.0
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}

    def _apply_sector_adjustment(self, scores: pd.Series, sectors: pd.Series, sector_data: pd.DataFrame) -> pd.Series:
        """
        Adjusts individual score based on sector leadership.
        sector_data: pd.DataFrame with index=sector, columns=['leader_score']
        """
        final_scores = scores.copy()
        for i, score in scores.items():
            sector = sectors.get(i)
            if sector and sector in sector_data.index:
                leader_score = sector_data.loc[sector, 'leader_score']
                final_scores[i] = 0.7 * score + 0.3 * leader_score
        return final_scores
