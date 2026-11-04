import numpy as np
from typing import Dict, List, Optional
from utils.logger import setup_logger

logger = setup_logger("BuzzEngine")

class BuzzEngine:
    """
    Data Layer: Buzz Engine
    - Tracks "Attention Momentum" via mention counts.
    - Calculates score based on Volume, Delta (Velocity), and Acceleration.
    """
    def __init__(self):
        # In a production system, this would be a time-series DB or persistent cache
        self.history = {} # ticker -> [count_t-2, count_t-1, count_t]

    def update_and_get_score(self, ticker: str, current_count: int) -> float:
        """
        Calculates buzz score based on attention momentum.
        Formula: buzz_score = f(count, delta, acceleration)
        """
        if ticker not in self.history:
            self.history[ticker] = []
        
        counts = self.history[ticker]
        counts.append(current_count)
        
        # Keep only the last 5 periods for momentum calculation
        if len(counts) > 5:
            counts.pop(0)

        if len(counts) < 3:
            # Baseline score if not enough history
            return min(1.0, current_count / 100.0)

        # 1. Volume (scaled)
        volume = counts[-1]
        
        # 2. Delta (Velocity)
        v1 = counts[-1] - counts[-2]
        v2 = counts[-2] - counts[-3]
        
        # 3. Acceleration
        accel = v1 - v2
        
        # Combined score calculation
        # Normalize/Scale for [-1, 1] or [0, 1]? 
        # Plan says buzz_score included in alpha formula. 
        # I'll scale it so it's meaningfully informative.
        
        velocity_score = v1 / (max(counts) + 1e-9)
        accel_score = accel / (max(counts) + 1e-9)
        volume_score = min(1.0, volume / 1000.0)
        
        final_buzz = (0.4 * volume_score) + (0.4 * velocity_score) + (0.2 * accel_score)
        
        # Standardize to [-1, 1] for signal consistency
        final_buzz = max(-1.0, min(1.0, final_buzz))
        
        logger.info(f"[{ticker}] Buzz: {final_buzz:+.2f} (Vol: {volume}, Vel: {v1}, Acc: {accel})")
        return final_buzz
