from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum
from datetime import datetime

class ActionEnum(str, Enum):
    BUY_CANDIDATE = "BUY_CANDIDATE"
    WAIT = "WAIT"
    HOLD = "HOLD"
    WATCHLIST = "WATCHLIST"
    EXIT_CANDIDATE = "EXIT_CANDIDATE"
    EXIT = "EXIT"
    NO_ACTION = "NO_ACTION"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    
    # We explicitly do NOT use PLACE_ORDER, EXECUTE_ORDER, etc., to avoid automated trading semantics.

class LifecycleState(str, Enum):
    CANDIDATE = "CANDIDATE"
    ENTRY_READY = "ENTRY_READY"
    ENTRY_1_EXECUTED = "ENTRY_1_EXECUTED"
    ENTRY_2_PENDING = "ENTRY_2_PENDING"
    FULL_POSITION = "FULL_POSITION"
    WATCH = "WATCH"
    EXIT_CANDIDATE = "EXIT_CANDIDATE"
    EXIT_CONFIRMED = "EXIT_CONFIRMED"
    EXITED = "EXITED"
    REENTRY_COOLDOWN = "REENTRY_COOLDOWN"
    ELIGIBLE_AGAIN = "ELIGIBLE_AGAIN"
    NOT_EXECUTED = "NOT_EXECUTED"

@dataclass
class SecurityDecision:
    security_id: str
    ticker: str
    company_name: str
    
    alpha_score: float
    alpha_rank: int
    entry_readiness_score: float
    entry_rank: int
    combined_rank: int
    recommendation_rank: int
    recommendation_bucket: str  # "TOP_5", "WATCHLIST_5", "OTHER"
    
    action: ActionEnum
    entry_stage: LifecycleState
    
    entry_1_weight: float
    entry_2_weight: float
    target_weight: float
    target_notional: float
    target_shares: float
    fractional_allowed: bool
    
    expected_horizon_days: int
    expected_return: float
    volatility: float
    confidence: float
    liquidity_score: float
    risk_score: float
    sector: str
    
    thesis_status: str
    exit_candidate: bool
    exit_reason: str
    hard_stop: float
    trailing_stop: float
    reentry_available_at: Optional[datetime]
    
    data_quality_status: str
    degradation_reason: str
    constraint_flags: List[str] = field(default_factory=list)
    
    # Structured reason codes
    reason_codes: List[str] = field(default_factory=list)
    explanation: str = ""


@dataclass
class PortfolioDecision:
    as_of: datetime
    market_regime: str
    capital: float
    currency: str
    
    top5: List[SecurityDecision] = field(default_factory=list)
    watchlist5: List[SecurityDecision] = field(default_factory=list)
    
    portfolio_cash: float = 0.0
    sector_exposure: Dict[str, float] = field(default_factory=dict)
    total_risk_budget: float = 0.0
    
    data_quality: str = "OK"
    model_version: str = "MODEL_RANK_E"
    strategy_version: str = "FROZEN_v1"
    generated_at: datetime = field(default_factory=datetime.utcnow)
