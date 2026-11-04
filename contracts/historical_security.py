"""Historical security states and event contracts."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime


class ListingStatus(str, Enum):
    LISTED = "LISTED"
    DELISTED = "DELISTED"
    SUSPENDED = "SUSPENDED"
    OTC = "OTC"
    RELISTED = "RELISTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HistoricalSecurityState:
    security_id: str
    provider_ids: Dict[str, str] = field(default_factory=dict)
    ticker: Optional[str] = None
    company_name: str = "Unknown"
    share_class: Optional[str] = None
    exchange: Optional[str] = None
    exchange_mic: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    listing_status: ListingStatus = ListingStatus.UNKNOWN
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    as_of: Optional[datetime] = None
    source: str = "unknown"
    confidence: float = 1.0
    schema_version: str = "1.0"


@dataclass(frozen=True)
class SecurityLifecycleEvent:
    event_id: str
    security_id: str
    event_type: str  # IPO, LISTING, TICKER_CHANGE, NAME_CHANGE, EXCHANGE_CHANGE, MERGER, ACQUISITION, SPINOFF, REVERSE_SPLIT, SPLIT, DELISTING, RELISTING, OTC_TRANSITION
    effective_at: datetime
    announced_at: Optional[datetime] = None
    source: str = "unknown"
    source_record_id: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


@dataclass(frozen=True)
class HistoricalUniverseMember:
    security_id: str
    ticker: str
    exchange_mic: Optional[str]
    share_class: Optional[str]
    listing_status: str
    universe_id: str
    valid_from: datetime
    valid_to: Optional[datetime]
    as_of: datetime
    source: str
    confidence: float
    schema_version: int = 1


@dataclass(frozen=True)
class HistoricalUniverseMembership:
    membership_id: str
    universe_id: str
    security_id: str
    valid_from: datetime
    valid_to: Optional[datetime]
    source: str
    source_record_id: Optional[str] = None
    confidence: float = 1.0
    created_at: Optional[datetime] = None
