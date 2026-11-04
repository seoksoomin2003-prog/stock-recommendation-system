"""Point-in-time contracts for the P5 historical information layer.

These contracts intentionally stop before ``NormalizedData``.  P5-6 owns that
translation boundary; keeping it here would let provider-specific historical
semantics leak into the current research runtime.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from contracts.normalized_data import DataStatus


class FactPeriodType(str, Enum):
    INSTANT = "INSTANT"
    DURATION = "DURATION"


class CorporateActionType(str, Enum):
    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    DIVIDEND = "DIVIDEND"
    SPECIAL_DIVIDEND = "SPECIAL_DIVIDEND"
    MERGER = "MERGER"
    ACQUISITION = "ACQUISITION"
    SPINOFF = "SPINOFF"
    TICKER_CHANGE = "TICKER_CHANGE"
    NAME_CHANGE = "NAME_CHANGE"
    DELISTING = "DELISTING"
    RELISTING = "RELISTING"


@dataclass(frozen=True)
class HistoricalFinancialFact:
    security_id: str
    provider: str
    source: str
    accession_number: Optional[str]
    taxonomy: str
    concept: str
    normalized_metric: str
    period_start: Optional[date]
    period_end: date
    filed_at: datetime
    accepted_at: Optional[datetime]
    value: float
    unit: str
    form_type: str
    fiscal_year: Optional[int] = None
    fiscal_period: Optional[str] = None
    is_amended: bool = False
    is_restated: bool = False
    source_url: Optional[str] = None
    observed_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None
    schema_version: str = "1.0"
    period_type: FactPeriodType = FactPeriodType.DURATION
    source_id: Optional[str] = None
    prevrpt: Optional[int] = 0


@dataclass(frozen=True)
class HistoricalFinancialSnapshot:
    security_id: str
    as_of: datetime
    metrics: Dict[str, Optional[float]]
    facts: Dict[str, HistoricalFinancialFact]
    availability_status: DataStatus
    source: str
    confidence: float
    observed_at: Optional[datetime]
    filed_at: Optional[datetime]
    accepted_at: Optional[datetime]
    is_fallback: bool
    is_stale: bool
    provenance: Dict[str, Any]
    completeness: float
    schema_version: str = "1.0"


@dataclass(frozen=True)
class HistoricalPriceBar:
    security_id: str
    provider: str
    date: date
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    adjusted_close: Optional[float]
    volume: Optional[float]
    source: str
    observed_at: Optional[datetime] = None
    ingested_at: Optional[datetime] = None
    schema_version: str = "1.0"
    source_id: Optional[str] = None


@dataclass(frozen=True)
class CorporateActionEvent:
    security_id: str
    event_id: str
    event_type: CorporateActionType
    effective_at: datetime
    announced_at: Optional[datetime]
    old_value: Optional[str]
    new_value: Optional[str]
    ratio: Optional[float]
    cash_amount: Optional[float]
    shares_affected: Optional[float]
    source: str
    source_url: Optional[str]
    observed_at: Optional[datetime]
    is_verified: bool
    schema_version: str = "1.0"

    def information_available_at(self) -> datetime:
        # An event with no announcement is not knowable before its effective time.
        return self.announced_at or self.effective_at


@dataclass(frozen=True)
class PITInformationSet:
    security_id: str
    as_of: datetime
    universe_state: Any
    financials: HistoricalFinancialSnapshot
    prices: List[HistoricalPriceBar]
    corporate_actions: List[CorporateActionEvent]
    provenance: Dict[str, Any]
    completeness: float
    status: DataStatus
    confidence: float
    snapshot_hash: str
    schema_version: str = "1.0"
