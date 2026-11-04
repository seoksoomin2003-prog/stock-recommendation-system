"""P6 Architecture Research Interface.

Defines the data contracts and scoring inputs ready for transition to P6
Entry/Exit trigger research. No live trading rules are modified in P5.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass(frozen=True)
class P6ResearchInput:
    """Inputs passed from the normalized factor database to P6 signal generator."""
    security_id: str
    as_of: datetime
    alpha_score: float
    factor_scores: Dict[str, float]
    market_regime: str
    confidence: float
    volatility: float
    trend: float
    expected_horizon: int = 20


@dataclass(frozen=True)
class P6ResearchSignal:
    """Output triggers evaluated by P6 strategies (Entry, Exit, Horizon)."""
    security_id: str
    as_of: datetime
    entry_signal: bool          # WHEN TO ENTER?
    exit_signal: bool           # WHEN TO EXIT?
    expected_horizon: int       # HOW LONG TO HOLD?
    signal_strength: float      # HOW STRONG IS THE SIGNAL?
    confidence: float
    risk_reward: float
    market_regime: str
    factor_drivers: List[str]   # Drivers contributing most to the score
    invalidation_conditions: List[str]  # WHAT INVALIDATES THE SIGNAL?


class P6SignalGeneratorInterface:
    """Research interface to design, backtest, and register P6 entry/exit signals."""
    
    def generate_signal(self, data_input: P6ResearchInput) -> P6ResearchSignal:
        """Evaluates entry/exit indicators based on P5-8B cross-sectional factors."""
        # Baseline threshold logic for architectural evaluation (no live trading rules)
        is_high_conviction = data_input.alpha_score > 1.5
        is_stop_loss_hit = data_input.alpha_score < -1.5
        
        # Drivers identification
        sorted_drivers = sorted(
            data_input.factor_scores.items(),
            key=lambda x: abs(x[1]),
            reverse=True
        )
        drivers = [k for k, v in sorted_drivers if abs(v) > 1.0]
        
        # Default risk reward estimation
        risk_reward = 2.0 if is_high_conviction else 1.0
        
        # Invalidation conditions
        invalidation = []
        if data_input.volatility > 0.05:
            invalidation.append("VOLATILITY_SPIKE")
        if data_input.market_regime == "BEAR":
            invalidation.append("REGIME_DOWN_TREND")
            
        return P6ResearchSignal(
            security_id=data_input.security_id,
            as_of=data_input.as_of,
            entry_signal=is_high_conviction,
            exit_signal=is_stop_loss_hit,
            expected_horizon=data_input.expected_horizon,
            signal_strength=data_input.alpha_score,
            confidence=data_input.confidence,
            risk_reward=risk_reward,
            market_regime=data_input.market_regime,
            factor_drivers=drivers,
            invalidation_conditions=invalidation
        )
