import numpy as np
import pandas as pd
from typing import Union
from utils.logger import setup_logger

logger = setup_logger("AlphaOutput")

class AlphaStandardizer:
    """
    Output Layer: Standardization
    - Clips final scores to [-1, 1].
    - Ensures no NaN values in output.
    - Standardizes the delivery format for Research Terminals.
    """
    @staticmethod
    def standardize(scores: Union[pd.Series, pd.DataFrame]) -> Union[pd.Series, pd.DataFrame]:
        """
        Final cleanup and standardization of alpha scores.
        """
        if scores.empty:
            return scores

        # 1. Fill NaNs with Neutral (0.0)
        standard_scores = scores.fillna(0.0)

        # 2. Extreme Value Clipping to Institutional Standard [-1, 1]
        standard_scores = np.clip(standard_scores, -1.0, 1.0)
        
        # 3. Precision Management (rounding for readability in research reports)
        standard_scores = standard_scores.round(4)
        
        logger.info(f"Output standardized. Non-zero signal count: {(standard_scores != 0).sum().sum()}")
        return standard_scores

    @staticmethod
    def format_for_report(ticker: str, score: float, details: dict) -> dict:
        """
        Formats the alpha engine output for institutional research consumers.
        """
        return {
            "ticker": ticker,
            "alpha_score": score,
            "components": details,
            "status": "VALID",
            "standard_range": "[-1.0, 1.0]"
        }
