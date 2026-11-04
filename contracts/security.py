"""Canonical, provider-independent security identity."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class IdentityStatus(str, Enum):
    RESOLVED = "RESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class SecurityIdentity:
    security_id: Optional[str]
    asset_type: str = "EQUITY"
    ticker: Optional[str] = None
    company_name: str = "Unknown"
    share_class: Optional[str] = None
    exchange: Optional[str] = None
    exchange_mic: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    cik: Optional[str] = None
    isin: Optional[str] = None
    figi: Optional[str] = None
    provider_ids: Dict[str, str] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    identity_status: IdentityStatus = IdentityStatus.UNRESOLVED
    resolution_confidence: float = 0.0

    def __post_init__(self):
        if not 0.0 <= self.resolution_confidence <= 1.0:
            raise ValueError("resolution_confidence must be in [0, 1]")
        if self.identity_status == IdentityStatus.RESOLVED and not self.security_id:
            raise ValueError("resolved identities require security_id")

    @classmethod
    def unresolved(cls, query: str) -> "SecurityIdentity":
        return cls(security_id=None, ticker=None, company_name=query or "Unknown")
