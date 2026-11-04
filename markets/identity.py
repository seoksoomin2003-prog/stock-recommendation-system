"""Market and security identity (P6-21 §3.2).

Ticker symbols overlap between markets (e.g. a 6-digit KRX code can never be inferred to be
Korean from its format alone, and US tickers such as "A" exist).  Every record therefore carries an
explicit market, and securities are identified by a composite key, never by the bare symbol.
"""
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class Market(str, Enum):
    US = "US"
    KR = "KR"

    @classmethod
    def parse(cls, value) -> "Market":
        if isinstance(value, Market):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            raise ValueError(f"Unknown market {value!r}; expected one of {[m.value for m in cls]}")


@dataclass(frozen=True)
class SecurityId:
    market: Market
    exchange: str            # e.g. "KOSPI", "KOSDAQ", "NYSE", "NASDAQ", "US-UNSPECIFIED"
    symbol: str              # canonical symbol in its own market (KRX 6-char code, US ticker)
    currency: str            # ISO 4217
    instrument_type: str     # e.g. "COMMON_STOCK"
    identifiers: Dict[str, str] = field(default_factory=dict, compare=False, hash=False)

    @property
    def key(self) -> str:
        """Composite identity: market:exchange:symbol (currency and type are attributes)."""
        return f"{self.market.value}:{self.exchange}:{self.symbol}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["market"] = self.market.value
        d["key"] = self.key
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SecurityId":
        return cls(Market.parse(d["market"]), d["exchange"], d["symbol"], d["currency"],
                   d["instrument_type"], dict(d.get("identifiers") or {}))


def us_security(ticker: str, exchange: Optional[str] = None, cik: Optional[str] = None) -> SecurityId:
    ids = {"yahoo": ticker}
    if cik:
        ids["sec_cik"] = str(cik)
    return SecurityId(Market.US, exchange or "US-UNSPECIFIED", ticker, "USD", "COMMON_STOCK", ids)


KR_YAHOO_SUFFIX = {"KOSPI": ".KS", "KOSDAQ": ".KQ"}


def kr_security(code: str, exchange: str, identifiers: Optional[Dict[str, str]] = None) -> SecurityId:
    if exchange not in KR_YAHOO_SUFFIX:
        raise ValueError(f"KR exchange must be KOSPI or KOSDAQ, got {exchange!r}")
    ids = {"krx_code": code, "yahoo": f"{code}{KR_YAHOO_SUFFIX[exchange]}"}
    ids.update(identifiers or {})
    return SecurityId(Market.KR, exchange, code, "KRW", "COMMON_STOCK", ids)
