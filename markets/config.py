"""Independently versioned market configurations (P6-21 §3.3).

The US configuration *describes* the existing frozen engine (it reads the frozen settings, it never
supplies them): changing it cannot change the US model.  KR settings live in a separate immutable
mapping; neither configuration can override the other (both are read-only MappingProxyType views).
"""
from types import MappingProxyType
from typing import Any, Mapping

from markets.identity import Market


def _freeze(obj):
    if isinstance(obj, dict):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(v) for v in obj)
    return obj


def _us() -> Mapping[str, Any]:
    from data.loader import DATA_INPUT_SPEC_VERSION
    return _freeze({
        "market": "US", "config_version": "US-1",
        "calendar": "NYSE (utils/market_calendar.py freshness gate; utils/nyse_calendar.py tracking)",
        "timezone": "America/New_York", "currency": "USD",
        "session": {"open": "09:30", "close": "16:00", "early_close": "13:00"},
        "universe_policy": "Current S&P 500 constituents (Wikipedia list + SEC ticker map), resolved per run",
        "providers": {"market_data": "yfinance", "fundamentals": "SEC EDGAR CompanyFacts + yfinance",
                      "filing_times": "EDGAR submissions"},
        "data_freshness": "last daily bar at most 1 NYSE session behind",
        "liquidity_policy": "ADV20 share volume >= 500,000 (frozen P6-11B rule)",
        "financial_data_rules": f"docs/DATA_INPUT_SPECIFICATION.md version {DATA_INPUT_SPEC_VERSION}",
        "data_spec_version": DATA_INPUT_SPEC_VERSION,
        "model": {"name": "MODEL_RANK_E", "version": "P6-11B FROZEN_v1", "status": "FROZEN",
                  "pinned_sources": "tests/fixtures/frozen_source_sha256_p6_19.json"},
        "portfolio_constraints": "frozen DecisionEngine: TOP-5, 30% security ceiling, Technology 2-of-5 cap, "
                                 "BEAR 75th-percentile filter",
        "benchmark": "SPY (identical windows)",
        "paper_entry_policy": "first regular-session open after the recommendation timestamp (P6-20)",
        "tracking": {"ledger": "tracking/ledger", "spec": "reports/P6-20_TRACKING_SPECIFICATION.md"},
        "runs_dir": "runs",
    })


def _kr() -> Mapping[str, Any]:
    from markets.kr import KR_DATA_SPEC_VERSION, KR_MODEL_VERSION, KR_MODEL_STATUS
    return _freeze({
        "market": "KR", "config_version": "KR-0.1",
        "calendar": "KRX, observed sessions (KOSPI index bars) + weekday rule for the next session",
        "timezone": "Asia/Seoul", "currency": "KRW",
        "session": {"open": "09:00", "close": "15:30"},
        "universe_policy": "Dynamic liquid-300: eligible KOSPI+KOSDAQ common stocks ranked by mean traded value "
                           "over the last 20 valid sessions",
        "providers": {"security_master": "KRX KIND listed-company list (public download)",
                      "market_data": "KRX Open API when KRX_API_KEY is set; otherwise yfinance (supplementary)",
                      "fundamentals": "OpenDART (OPENDART_API_KEY)"},
        "data_freshness": "last bar must equal the latest observed KRX session (KOSPI index)",
        "liquidity_policy": "relative: top 300 by ADTV20 (no absolute KRW floor without evidence)",
        "financial_data_rules": f"reports/P6-22_KR_DATA_SPECIFICATION.md version {KR_DATA_SPEC_VERSION}",
        "data_spec_version": KR_DATA_SPEC_VERSION,
        "model": {"name": "KR_RANK", "version": KR_MODEL_VERSION, "status": KR_MODEL_STATUS,
                  "spec": "reports/KR_MODEL_SPECIFICATION.md"},
        "portfolio_constraints": "TOP-10 equal weight (10%), at most 3 names per KRX industry",
        "benchmark": "matched-market index per position (KOSPI ^KS11 / KOSDAQ ^KQ11), weighted by positions",
        "paper_entry_policy": "first KRX session open after the recommendation timestamp; exit at the close of "
                              "the 20th session",
        "tracking": {"ledger": "tracking/kr/ledger", "spec": "reports/P6-25_KR_TRACKING_SPECIFICATION.md"},
        "runs_dir": "runs/KR",
    })


def market_config(market) -> Mapping[str, Any]:
    m = Market.parse(market)
    return _us() if m is Market.US else _kr()
