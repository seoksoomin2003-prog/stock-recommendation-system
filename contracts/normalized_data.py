"""Versioned provider result contract with explicit degraded-state semantics."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class DataStatus(str, Enum):
    # Canonical production states.  The older aliases below are retained only
    # so historical/research readers can deserialize their existing records.
    REAL = "REAL"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    STALE = "STALE"
    MOCK = "MOCK"
    CACHED = "CACHED"
    # Deprecated: a fallback is always synthetic/degraded and must not be
    # considered usable production data.  Adapters should emit MOCK or
    # UNAVAILABLE instead.
    FALLBACK = "FALLBACK"
    ERROR = "ERROR"
    
    # P5-8C data governance statuses
    REAL_PIT_ELIGIBLE = "REAL_PIT_ELIGIBLE"
    REAL_PIT_UNVERIFIED = "REAL_PIT_UNVERIFIED"
    REAL_CURRENT = "REAL_CURRENT"
    CACHED_PIT_ELIGIBLE = "CACHED_PIT_ELIGIBLE"
    CACHED_PIT_UNVERIFIED = "CACHED_PIT_UNVERIFIED"


@dataclass(frozen=True)
class NormalizedData:
    security_id: Optional[str]
    ticker: Optional[str]
    data_type: str
    data: Any
    source: str
    status: DataStatus
    confidence: float
    observed_at: Optional[datetime]
    fetched_at: datetime
    expires_at: Optional[datetime]
    is_fallback: bool = False
    is_stale: bool = False
    request_id: str = ""
    schema_version: int = 1
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        
        valid_real_cached_set = {
            DataStatus.REAL, DataStatus.CACHED, DataStatus.STALE,
            DataStatus.REAL_PIT_ELIGIBLE, DataStatus.REAL_PIT_UNVERIFIED, DataStatus.REAL_CURRENT,
            DataStatus.CACHED_PIT_ELIGIBLE, DataStatus.CACHED_PIT_UNVERIFIED
        }
        if self.status in valid_real_cached_set and not self.source:
            raise ValueError("usable provider data requires source")
        if self.status == DataStatus.STALE and not self.is_stale:
            raise ValueError("STALE status requires is_stale=True")
        if self.status in {DataStatus.FALLBACK, DataStatus.MOCK} and not self.is_fallback:
            raise ValueError("synthetic status requires is_fallback=True")
        if self.status == DataStatus.ERROR and self.error_code is None:
            raise ValueError("ERROR status requires a safe error_code")
