"""Request and output contracts for the non-execution research runtime."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .security import SecurityIdentity


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ResearchRequest:
    query: str
    request_id: str = field(default_factory=lambda: str(uuid4()))
    as_of: datetime = field(default_factory=utc_now)
    horizon: str = "20D"
    lookback_days: int = 365
    mode: str = "local"

    def __post_init__(self):
        if self.horizon not in {"1D", "5D", "20D"}:
            raise ValueError("horizon must be one of 1D, 5D, 20D")
        if self.lookback_days <= 0:
            raise ValueError("lookback_days must be positive")


@dataclass
class ResearchOutput:
    request_id: str
    security: SecurityIdentity
    alpha_score: Optional[float]
    confidence: float
    horizon: str
    as_of: datetime
    components: Dict[str, float] = field(default_factory=dict)
    drivers: List[Dict[str, Any]] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    data_quality: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    ranking: Dict[str, Any] = field(default_factory=lambda: {"status": "UNAVAILABLE"})
    status: str = "OK"
    generated_at: datetime = field(default_factory=utc_now)
    schema_version: int = 1

    def __post_init__(self):
        if self.alpha_score is not None and not -1.0 <= self.alpha_score <= 1.0:
            raise ValueError("alpha_score must be in [-1, 1]")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
