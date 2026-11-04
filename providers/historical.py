"""Provider boundaries for P5 historical data; no Quant Engine imports."""

import os
import json
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Protocol

import requests

from contracts.historical_data import FactPeriodType, HistoricalFinancialFact
from contracts.normalized_data import DataStatus


class HistoricalFinancialProvider(Protocol):
    name: str
    def acquire(self, security_id: str, provider_identifier: str): ...


class HistoricalPriceProvider(Protocol):
    name: str
    def acquire(self, security_id: str, provider_identifier: str, start, end): ...


class CorporateActionProvider(Protocol):
    name: str
    def acquire(self, security_id: str, provider_identifier: str, start, end): ...


@dataclass(frozen=True)
class ProviderAvailability:
    provider: str
    domain: str
    status: DataStatus
    reason: str
    credential_configured: bool


class ConnectivityStatus(str, Enum):
    DNS_UNAVAILABLE = "DNS_UNAVAILABLE"
    NETWORK_UNAVAILABLE = "NETWORK_UNAVAILABLE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    AUTH_FAILED = "AUTH_FAILED"
    REACHABLE_BUT_NO_DATA = "REACHABLE_BUT_NO_DATA"
    CONNECTED = "CONNECTED"
    SCHEMA_INVALID = "SCHEMA_INVALID"


@dataclass(frozen=True)
class SecUserAgentConfig:
    """Fail-closed SEC configuration. The value is never rendered or logged."""
    value: Optional[str]

    @classmethod
    def from_environment(cls) -> "SecUserAgentConfig":
        value = os.getenv("SEC_USER_AGENT")
        return cls(value.strip() if value and value.strip() else None)

    @property
    def configured(self) -> bool:
        return self.value is not None

    def headers(self) -> Dict[str, str]:
        if not self.value:
            raise ValueError("SEC_USER_AGENT_not_configured")
        return {"User-Agent": self.value, "Accept-Encoding": "gzip, deflate"}


@dataclass(frozen=True)
class ConnectivityDiagnostic:
    provider: str
    domain: str
    dns_resolution: bool
    tcp_https_reachable: bool
    tls_success: bool
    credentials_configured: bool
    authentication: str
    sample_request: str
    sample_response_validation: str
    status: ConnectivityStatus
    detail: str


def diagnose_connectivity(provider: str, domain: str, *, credentials_configured: bool,
                          timeout_seconds: float = 2.0) -> ConnectivityDiagnostic:
    """One bounded DNS/TCP/TLS diagnostic. It never mutates system networking."""
    try:
        infos = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        return ConnectivityDiagnostic(provider, domain, False, False, False, credentials_configured,
                                      "NOT_ATTEMPTED", "NOT_ATTEMPTED", "NOT_ATTEMPTED",
                                      ConnectivityStatus.DNS_UNAVAILABLE, type(exc).__name__)
    try:
        address = infos[0][4]
        with socket.create_connection(address, timeout=timeout_seconds) as raw:
            context = ssl.create_default_context()
            with context.wrap_socket(raw, server_hostname=domain):
                pass
    except OSError as exc:
        return ConnectivityDiagnostic(provider, domain, True, False, False, credentials_configured,
                                      "NOT_ATTEMPTED", "NOT_ATTEMPTED", "NOT_ATTEMPTED",
                                      ConnectivityStatus.NETWORK_UNAVAILABLE, type(exc).__name__)
    except ssl.SSLError as exc:
        return ConnectivityDiagnostic(provider, domain, True, True, False, credentials_configured,
                                      "NOT_ATTEMPTED", "NOT_ATTEMPTED", "NOT_ATTEMPTED",
                                      ConnectivityStatus.NETWORK_UNAVAILABLE, type(exc).__name__)
    if not credentials_configured:
        return ConnectivityDiagnostic(provider, domain, True, True, True, False, "NOT_ATTEMPTED",
                                      "BLOCKED_BY_CONFIGURATION", "NOT_ATTEMPTED", ConnectivityStatus.AUTH_REQUIRED,
                                      "credential_or_SEC_USER_AGENT_missing")
    return ConnectivityDiagnostic(provider, domain, True, True, True, True, "NOT_ATTEMPTED",
                                  "NOT_ATTEMPTED", "NOT_ATTEMPTED", ConnectivityStatus.REACHABLE_BUT_NO_DATA,
                                  "endpoint_reachable; bounded authenticated probe required")


@dataclass(frozen=True)
class ProviderProbe:
    provider: str
    domain: str
    credentials_configured: bool
    network_reachable: bool
    authentication_successful: bool
    sample_record_retrieved: bool
    schema_validated: bool
    pit_timestamps_present: bool
    provenance_present: bool
    rate_limit_compliant: bool
    status: DataStatus
    detail: str


class OfficialSecHistoricalFinancialProvider:
    """Minimal official EDGAR acquisition adapter; it has no synthetic fallback.

    The provider is intentionally opt-in: a contactable SEC_USER_AGENT is
    required. Requests are serialized at no more than two per second, below
    the SEC's public 10 requests/sec ceiling.
    """
    name = "sec_edgar_official"
    _lock = threading.Lock()
    _last_request_at = 0.0
    _metric_concepts = {
        # Revenues
        "Revenues": "revenue",
        "SalesRevenueNet": "revenue",
        "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
        "RevenueFromContractWithCustomerNetOfTax": "revenue",
        
        # Net Income
        "NetIncomeLoss": "net_income",
        "ProfitLoss": "net_income",
        "NetIncomeLossAvailableToCommonStockholdersBasic": "net_income",
        
        # Operating Income
        "OperatingIncomeLoss": "operating_income",
        
        # Gross Profit
        "GrossProfit": "gross_profit",
        
        # Assets & Liabilities
        "Assets": "total_assets",
        "Liabilities": "total_liabilities",
        
        # Equity
        "StockholdersEquity": "shareholders_equity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": "shareholders_equity",
        
        # Cash & Debt
        "CashAndCashEquivalentsAtCarryingValue": "cash",
        "LongTermDebtAndFinanceLeaseObligationsCurrent": "debt",
        "LongTermDebt": "debt",
        "LongTermDebtNoncurrent": "debt",
        
        # EPS
        "EarningsPerShareBasic": "eps",
        "EarningsPerShareDiluted": "eps",
        
        # Shares Outstanding
        "EntityCommonStockSharesOutstanding": "shares_outstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic": "shares_outstanding",
        "WeightedAverageNumberOfDilutedSharesOutstanding": "shares_outstanding",
    }
    _instant = {"total_assets", "total_liabilities", "shareholders_equity", "cash", "debt", "shares_outstanding"}

    def __init__(self, user_agent: Optional[str] = None, timeout_seconds: int = 10):
        self.config = SecUserAgentConfig(user_agent.strip() if user_agent and user_agent.strip() else SecUserAgentConfig.from_environment().value)
        self.timeout_seconds = timeout_seconds
        self.cache_dir = "data/sec_cache"
        if not os.path.exists(self.cache_dir):
            try:
                os.makedirs(self.cache_dir)
            except Exception:
                pass

    def probe(self, cik: Optional[str] = None) -> ProviderProbe:
        configured = self.config.configured
        if not configured:
            return ProviderProbe(self.name, "fundamentals", False, False, False, False, False, False, False, True,
                                 DataStatus.UNAVAILABLE, "SEC_USER_AGENT_not_configured")
        if not cik:
            return ProviderProbe(self.name, "fundamentals", True, False, False, False, False, False, False, True,
                                 DataStatus.UNAVAILABLE, "sample_cik_required")
        try:
            payload = self._get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json")
            facts = self.parse_companyfacts("probe", str(cik), payload, fetched_at=datetime.now(timezone.utc))
            ok = bool(facts)
            return ProviderProbe(self.name, "fundamentals", True, True, True, ok, ok,
                                 bool(ok and all(f.filed_at and f.period_end for f in facts)),
                                 bool(ok and all(f.source and f.source_id for f in facts)), True,
                                 DataStatus.REAL if ok else DataStatus.UNAVAILABLE,
                                 "sample_facts_retrieved" if ok else "no_supported_facts")
        except requests.RequestException as exc:
            return ProviderProbe(self.name, "fundamentals", True, False, False, False, False, False, False, True,
                                 DataStatus.UNAVAILABLE, f"network_error:{type(exc).__name__}")
        except (ValueError, KeyError, TypeError) as exc:
            return ProviderProbe(self.name, "fundamentals", True, True, False, False, False, False, False, True,
                                 DataStatus.ERROR, f"schema_error:{type(exc).__name__}")

    def acquire(self, security_id: str, cik: str) -> List[HistoricalFinancialFact]:
        if not self.config.configured:
            return []
        payload = self._get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json")
        return self.parse_companyfacts(security_id, str(cik), payload, fetched_at=datetime.now(timezone.utc))

    def parse_companyfacts(self, security_id: str, cik: str, payload: Dict, *, fetched_at: datetime) -> List[HistoricalFinancialFact]:
        results: List[HistoricalFinancialFact] = []
        for taxonomy, concepts in (payload.get("facts") or {}).items():
            for concept, metric in self._metric_concepts.items():
                data = concepts.get(concept)
                if not data:
                    continue
                for unit, entries in (data.get("units") or {}).items():
                    for row in entries:
                        if not row.get("filed") or not row.get("end") or row.get("val") is None or not row.get("accn"):
                            continue
                        try:
                            period_end = date.fromisoformat(row["end"])
                            filed_at = datetime.fromisoformat(row["filed"]).replace(tzinfo=timezone.utc)
                            period_start = date.fromisoformat(row["start"]) if row.get("start") else None
                        except ValueError:
                            continue
                        period_type = FactPeriodType.INSTANT if metric in self._instant else FactPeriodType.DURATION
                        if (period_type == FactPeriodType.DURATION) != bool(period_start):
                            continue
                        
                        prevrpt_val = 0
                        if "prevrpt" in row:
                            try:
                                prevrpt_val = int(row["prevrpt"])
                            except (ValueError, TypeError):
                                prevrpt_val = 1 if row["prevrpt"] else 0

                        results.append(HistoricalFinancialFact(
                            security_id=security_id, provider=self.name, source="SEC EDGAR companyfacts",
                            accession_number=row.get("accn"), taxonomy=taxonomy, concept=concept, normalized_metric=metric,
                            period_start=period_start, period_end=period_end, filed_at=filed_at, accepted_at=None,
                            value=float(row["val"]), unit=unit, form_type=row.get("form") or "UNKNOWN",
                            fiscal_year=row.get("fy"), fiscal_period=row.get("fp"),
                            is_amended=str(row.get("form") or "").endswith("/A"), is_restated=False,
                            source_url=f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json",
                            observed_at=filed_at, ingested_at=fetched_at, source_id=row.get("accn"),
                            period_type=period_type, prevrpt=prevrpt_val))
        return results

    def _get_json(self, url: str) -> Dict:
        cik_str = None
        if "companyfacts/CIK" in url:
            parts = url.split("companyfacts/CIK")
            if len(parts) > 1:
                cik_str = parts[1].split(".")[0]
        
        cache_path = None
        if cik_str:
            cache_path = os.path.join(self.cache_dir, f"facts_{cik_str}.json")
            if os.path.exists(cache_path):
                # check TTL (1 day = 86400 seconds)
                if time.time() - os.path.getmtime(cache_path) < 86400:
                    try:
                        with open(cache_path, "r", encoding="utf-8") as f:
                            return json.load(f)
                    except Exception:
                        pass
        
        with self._lock:
            wait = 0.5 - (time.monotonic() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
            response = requests.get(url, headers=self.config.headers(),
                                    timeout=self.timeout_seconds)
            self._last_request_at = time.monotonic()
            
        response.raise_for_status()
        res_json = response.json()
        
        if cache_path:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(res_json, f)
            except Exception:
                pass
                
        return res_json


class HistoricalProviderRegistry:
    """Configuration-only provider selection; unavailable is an explicit result.

    SEC acquisition belongs behind a future official-EDGAR adapter.  The legacy
    SEC client is deliberately not registered because its fallback can return
    simulated records, which cannot enter this repository.
    """
    def availability(self) -> Dict[str, ProviderAvailability]:
        sharadar = bool(os.getenv("NASDAQ_DATA_LINK_API_KEY") or os.getenv("SHARADAR_API_KEY"))
        norgate = bool(os.getenv("NORGATE_API_KEY") or os.getenv("NORGATE_DATA_API_KEY"))
        sec_ua = bool(os.getenv("SEC_USER_AGENT"))
        return {
            "sec_edgar": ProviderAvailability("sec_edgar", "fundamentals", DataStatus.UNAVAILABLE,
                "SEC_USER_AGENT_missing" if not sec_ua else "connectivity_probe_required", sec_ua),
            "sharadar": ProviderAvailability("sharadar", "fundamentals/prices/actions", DataStatus.UNAVAILABLE,
                "credential_missing" if not sharadar else "adapter_not_installed", sharadar),
            "norgate": ProviderAvailability("norgate", "universe/prices/actions", DataStatus.UNAVAILABLE,
                "credential_missing" if not norgate else "adapter_not_installed", norgate),
        }
