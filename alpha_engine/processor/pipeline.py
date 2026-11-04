import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from utils.logger import setup_logger

logger = setup_logger("AlphaProcessor")

class AlphaProcessor:
    """
    Processing Layer: Alpha Pipeline
    - Handles statistical normalization (Z-score, Winsorization).
    - Applies Time Decay to signals.
    - Implements Event Boosting logic based on macro events.
    """
    def __init__(self, lambda_decay: float = 0.5):
        self.lambda_decay = lambda_decay

    def apply_time_decay(self, initial_score: float, t_days: float) -> float:
        """
        Score_decay = Score_initial * exp(-λ * t)
        """
        decay_score = initial_score * np.exp(-self.lambda_decay * t_days)
        return float(decay_score)

    def winsorize(self, series: pd.Series, limits: tuple = (0.05, 0.05)) -> pd.Series:
        """
        Applies winsorization to handle extreme outliers.
        """
        return series.clip(lower=series.quantile(limits[0]), upper=series.quantile(1 - limits[1]))

    def normalize_signals(self, signal_df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalizes signals using Z-score and Min-Max scaling.
        Ensures all features are comparable for the scoring engine.
        """
        if signal_df.empty:
            return signal_df

        # 1. Winsorization (limit extreme influence)
        processed_df = signal_df.apply(self.winsorize)
        
        # 2. Z-score normalization
        processed_df = (processed_df - processed_df.mean()) / (processed_df.std() + 1e-9)
        
        # 3. Final Scaling to [0, 1] or [-1, 1] depending on component
        # Here we scale to [-1, 1] to maintain directional signal
        processed_df = processed_df.apply(lambda x: 2 * (x - x.min()) / (x.max() - x.min() + 1e-9) - 1)
        
        return processed_df

    def apply_event_boost(self, weights: Dict[str, float], macro_impact: float, k: float = 1.5) -> Dict[str, float]:
        """
        If macro_event_detected: sentiment_weight *= k
        Dynamically adjusts weights based on macro regime.
        """
        new_weights = weights.copy()
        if macro_impact > 0.5:
            # Shift weight towards sentiment and macro
            boost_factor = 1.0 + (k - 1.0) * macro_impact
            if 'sentiment' in new_weights:
                new_weights['sentiment'] *= boost_factor
                logger.info(f"Macro boost applied! Sentiment weight *= {boost_factor:.2f}")
            
            # Normalize weights to sum to 1.0
            total = sum(new_weights.values())
            new_weights = {k: v / total for k, v in new_weights.items()}
            
        return new_weights
