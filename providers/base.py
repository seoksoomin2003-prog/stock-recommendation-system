"""Provider boundary. Quant modules must not import this package."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol

from contracts.normalized_data import NormalizedData
from contracts.security import SecurityIdentity


class ProviderKind(str, Enum):
    MARKET = "market"
    FINANCIAL = "financial"
    NEWS = "news"
    SEC = "sec"
    TRENDS = "trends"
    SOCIAL = "social"
    MACRO = "macro"


@dataclass(frozen=True)
class ProviderContext:
    request_id: str
    as_of: datetime
    lookback_days: int
    mode: str = "local"
    timeout_seconds: int = 10
    max_retries: int = 2
    allow_stale: bool = True
    offline: bool = False


class DataProvider(Protocol):
    name: str
    kind: ProviderKind
    ttl_seconds: int

    def fetch(self, security: Optional[SecurityIdentity], context: ProviderContext) -> NormalizedData:
        ...
