import json
import hashlib
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

from contracts.historical_data import (
    HistoricalFinancialFact, HistoricalPriceBar, CorporateActionEvent, PITInformationSet
)
from contracts.normalized_data import NormalizedData, DataStatus
from entity.historical_security_master import HistoricalSecurityState, ListingStatus


class HistoricalDataTranslator:
    """Translates HistoricalInformationSet components into provider-neutral NormalizedData."""

    @staticmethod
    def _check_lookahead(as_of: datetime, ts: Optional[datetime]) -> None:
        if ts is not None:
            # Ensure comparison is timezone-aware
            as_of_utc = as_of.replace(tzinfo=timezone.utc) if as_of.tzinfo is None else as_of.astimezone(timezone.utc)
            ts_utc = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
            if ts_utc > as_of_utc:
                raise ValueError("look_ahead_data_rejected")

    @classmethod
    def translate(cls, info_set: PITInformationSet) -> List[NormalizedData]:
        as_of = info_set.as_of
        security_id = info_set.security_id
        
        # 1. Look-ahead validation
        # Prices
        for p in info_set.prices:
            p_dt = datetime.combine(p.date, datetime.min.time(), timezone.utc)
            cls._check_lookahead(as_of, p_dt)
            cls._check_lookahead(as_of, p.observed_at)
            
        # Financials
        for f in info_set.financials.facts.values():
            cls._check_lookahead(as_of, f.filed_at)
            cls._check_lookahead(as_of, f.accepted_at)
            cls._check_lookahead(as_of, f.observed_at)
            
        # Corporate Actions
        for a in info_set.corporate_actions:
            cls._check_lookahead(as_of, a.effective_at)
            cls._check_lookahead(as_of, a.announced_at)
            cls._check_lookahead(as_of, a.observed_at)

        # Security Master / Universe State
        security_state = None
        universe_state = None
        if info_set.universe_state and isinstance(info_set.universe_state, dict):
            security_state = info_set.universe_state.get("security")
            universe_state = info_set.universe_state.get("universe")
            
        if security_state:
            cls._check_lookahead(as_of, security_state.valid_from)

        # 2. Translate Domains
        normalized_list = []
        
        # A. Market Data
        if info_set.prices:
            # We group all price bars into one market NormalizedData
            price_data = []
            max_observed = None
            for p in info_set.prices:
                price_data.append({
                    "date": p.date.isoformat(),
                    "open": p.open,
                    "high": p.high,
                    "low": p.low,
                    "close": p.close,
                    "adjusted_close": p.adjusted_close,
                    "volume": p.volume,
                    "source": p.source,
                    "source_id": p.source_id
                })
                if p.observed_at:
                    if max_observed is None or p.observed_at > max_observed:
                        max_observed = p.observed_at
                        
            coverage = "COMPLETE" if len(price_data) > 0 else "MISSING"
            
            # Unpack source
            src = info_set.prices[0].source
            
            normalized_list.append(NormalizedData(
                security_id=security_id,
                ticker=security_state.ticker if security_state else None,
                data_type="market",
                data=price_data,
                source=src,
                status=info_set.status,
                confidence=info_set.confidence,
                observed_at=max_observed or as_of,
                fetched_at=datetime.now(timezone.utc),
                expires_at=None,
                metadata={
                    "historical_coverage": {
                        "price_history": coverage,
                        "delisted_price_history": "PARTIAL" if security_state and security_state.listing_status == ListingStatus.DELISTED else "COMPLETE"
                    }
                }
            ))

        # B. Financial Data & SEC Data
        if info_set.financials.facts:
            financial_data = {}
            sec_data = {}
            for k, f in info_set.financials.facts.items():
                fact_dict = {
                    "metric": f.normalized_metric,
                    "value": f.value,
                    "unit": f.unit,
                    "period_start": f.period_start.isoformat() if f.period_start else None,
                    "period_end": f.period_end.isoformat(),
                    "filed_at": f.filed_at.isoformat(),
                    "accepted_at": f.accepted_at.isoformat() if f.accepted_at else None,
                    "accession_number": f.accession_number,
                    "source": f.source,
                    "source_id": f.source_id
                }
                
                # Check for synthetic marker
                if not info_set.financials.is_fallback:
                    s_upper = (f.source or "").upper()
                    if any(m in s_upper for m in ("SYNTHETIC", "TEST FIXTURE", "MOCK", "GENERATED")):
                        raise ValueError("synthetic_records_forbidden")
                
                financial_data[k] = fact_dict
                if "sec" in (f.provider or "").lower():
                    sec_data[k] = fact_dict
                    
            # Determine governance status
            as_of_utc = as_of.replace(tzinfo=timezone.utc) if as_of.tzinfo is None else as_of.astimezone(timezone.utc)
            now_utc = datetime.now(timezone.utc)
            is_live_current = (now_utc - as_of_utc).days <= 1
            
            if is_live_current:
                gov_status = DataStatus.REAL_CURRENT
            else:
                is_yfinance = any("yfinance" in (f.provider or "").lower() or "yfinance" in (f.source or "").lower() for f in info_set.financials.facts.values())
                if is_yfinance:
                    if info_set.financials.availability_status == DataStatus.CACHED:
                        gov_status = DataStatus.CACHED_PIT_UNVERIFIED
                    else:
                        gov_status = DataStatus.REAL_PIT_UNVERIFIED
                else:
                    if info_set.financials.availability_status == DataStatus.CACHED:
                        gov_status = DataStatus.CACHED_PIT_ELIGIBLE
                    else:
                        gov_status = DataStatus.REAL_PIT_ELIGIBLE

            normalized_list.append(NormalizedData(
                security_id=security_id,
                ticker=security_state.ticker if security_state else None,
                data_type="financial",
                data=financial_data,
                source=info_set.financials.source,
                status=gov_status,
                confidence=info_set.financials.confidence,
                observed_at=info_set.financials.observed_at or as_of,
                fetched_at=datetime.now(timezone.utc),
                expires_at=None,
                metadata={
                    "historical_coverage": {
                        "fundamentals": "COMPLETE" if len(financial_data) > 0 else "MISSING"
                    }
                }
            ))
            
            if sec_data:
                # SEC only data is always eligible
                sec_gov_status = DataStatus.CACHED_PIT_ELIGIBLE if info_set.financials.availability_status == DataStatus.CACHED else DataStatus.REAL_PIT_ELIGIBLE
                if is_live_current:
                    sec_gov_status = DataStatus.REAL_CURRENT
                    
                normalized_list.append(NormalizedData(
                    security_id=security_id,
                    ticker=security_state.ticker if security_state else None,
                    data_type="sec",
                    data=sec_data,
                    source=info_set.financials.source,
                    status=sec_gov_status,
                    confidence=info_set.financials.confidence,
                    observed_at=info_set.financials.observed_at or as_of,
                    fetched_at=datetime.now(timezone.utc),
                    expires_at=None
                ))


        # C. Corporate Actions
        if info_set.corporate_actions:
            action_data = []
            for a in info_set.corporate_actions:
                action_data.append({
                    "event_id": a.event_id,
                    "event_type": a.event_type.value,
                    "effective_at": a.effective_at.isoformat(),
                    "announced_at": a.announced_at.isoformat() if a.announced_at else None,
                    "old_value": a.old_value,
                    "new_value": a.new_value,
                    "ratio": a.ratio,
                    "cash_amount": a.cash_amount,
                    "shares_affected": a.shares_affected,
                    "source": a.source,
                    "source_url": a.source_url,
                    "observed_at": a.observed_at.isoformat() if a.observed_at else None,
                    "is_verified": a.is_verified
                })
            normalized_list.append(NormalizedData(
                security_id=security_id,
                ticker=security_state.ticker if security_state else None,
                data_type="corporate_actions",
                data=action_data,
                source="corporate_action",
                status=info_set.status,
                confidence=info_set.confidence,
                observed_at=as_of,
                fetched_at=datetime.now(timezone.utc),
                expires_at=None,
                metadata={
                    "historical_coverage": {
                        "corporate_actions": "COMPLETE" if len(action_data) > 0 else "MISSING"
                    }
                }
            ))

        # D. Security Master
        if security_state:
            state_dict = {
                "security_id": security_state.security_id,
                "ticker": security_state.ticker,
                "company_name": security_state.company_name,
                "listing_status": security_state.listing_status.value,
                "valid_from": security_state.valid_from.isoformat() if security_state.valid_from else None,
                "valid_to": security_state.valid_to.isoformat() if security_state.valid_to else None,
                "provider_ids": security_state.provider_ids,
                "source": security_state.source
            }
            normalized_list.append(NormalizedData(
                security_id=security_id,
                ticker=security_state.ticker,
                data_type="security_master",
                data=state_dict,
                source=security_state.source or "security_master",
                status=DataStatus.REAL,
                confidence=security_state.confidence or 1.0,
                observed_at=security_state.valid_from or as_of,
                fetched_at=datetime.now(timezone.utc),
                expires_at=None,
                metadata={
                    "historical_coverage": {
                        "security_identity": "COMPLETE",
                        "listing_history": "COMPLETE"
                    }
                }
            ))

        # E. Universe Membership
        if universe_state:
            uni_dict = {
                "universe_id": universe_state.universe_id,
                "security_id": universe_state.security_id,
                "valid_from": universe_state.valid_from.isoformat() if universe_state.valid_from else None,
                "valid_to": universe_state.valid_to.isoformat() if universe_state.valid_to else None,
                "source": universe_state.source
            }
            normalized_list.append(NormalizedData(
                security_id=security_id,
                ticker=security_state.ticker if security_state else None,
                data_type="universe",
                data=uni_dict,
                source=universe_state.source or "universe",
                status=DataStatus.REAL,
                confidence=1.0,
                observed_at=universe_state.valid_from or as_of,
                fetched_at=datetime.now(timezone.utc),
                expires_at=None,
                metadata={
                    "historical_coverage": {
                        "universe_membership": "COMPLETE"
                    }
                }
            ))

        return normalized_list


class QuantInputAdapter:
    """Adapts list of NormalizedData into format expected by existing FactorEngine."""

    @staticmethod
    def to_factor_inputs(normalized_list: List[NormalizedData], as_of: datetime) -> tuple:
        # 1. Parse Market Data (Prices DataFrame)
        price_dict = {}
        for item in normalized_list:
            if item.data_type == "market" and item.security_id:
                # item.data contains list of price bars
                for bar in item.data:
                    bar_date = date.fromisoformat(bar["date"])
                    if bar_date not in price_dict:
                        price_dict[bar_date] = {}
                    # We map security_id to close price
                    price_dict[bar_date][item.security_id] = bar["close"]
                    
        if price_dict:
            dates = sorted(price_dict.keys())
            prices_df = pd.DataFrame.from_dict(price_dict, orient='index')
            prices_df.index = pd.to_datetime(prices_df.index)
        else:
            prices_df = pd.DataFrame()

        # 2. Parse Financials DataFrame
        financials_dict = {}
        for item in normalized_list:
            if item.data_type == "financial" and item.security_id:
                # Backtest Hard Gate
                as_of_utc = as_of.replace(tzinfo=timezone.utc) if as_of.tzinfo is None else as_of.astimezone(timezone.utc)
                now_utc = datetime.now(timezone.utc)
                is_backtest = (now_utc - as_of_utc).days > 1
                
                is_unverified = item.status in {DataStatus.REAL_PIT_UNVERIFIED, DataStatus.CACHED_PIT_UNVERIFIED}
                if is_unverified and is_backtest:
                    # Skip parsing to reject this provider's data from historical factors
                    continue
                    
                facts = item.data
                
                # Fetch key variables
                net_income = facts.get("net_income", {}).get("value")
                total_equity = facts.get("shareholders_equity", {}).get("value")
                revenue = facts.get("revenue", {}).get("value")
                eps = facts.get("eps", {}).get("value")
                shares = facts.get("shares_outstanding", {}).get("value")
                
                # Find latest close price for PER/PBR calculation
                latest_close = np.nan
                if item.security_id in prices_df.columns and not prices_df.empty:
                    latest_close = prices_df[item.security_id].dropna().iloc[-1]

                # Compute value metrics
                per = np.nan
                pbr = np.nan
                roe = np.nan
                profit_margin = np.nan

                if eps and eps > 0 and not np.isnan(latest_close):
                    per = latest_close / eps
                    
                if total_equity and shares and shares > 0:
                    bps = total_equity / shares
                    if bps > 0 and not np.isnan(latest_close):
                        pbr = latest_close / bps

                if net_income is not None and total_equity:
                    roe = net_income / total_equity if total_equity != 0 else np.nan
                    
                if net_income is not None and revenue:
                    profit_margin = net_income / revenue if revenue != 0 else np.nan

                # Fallback to direct snapshot parameters if present
                per = facts.get("pe", {}).get("value", per)
                pbr = facts.get("pb", {}).get("value", pbr)
                roe = facts.get("roe", {}).get("value", roe)
                profit_margin = facts.get("profit_margin", {}).get("value", profit_margin)

                financials_dict[item.security_id] = {
                    "per": per,
                    "pbr": pbr,
                    "roe": roe,
                    "profitMargin": profit_margin
                }
                
        financial_df = pd.DataFrame.from_dict(financials_dict, orient='index')
        if financial_df.empty:
            financial_df = pd.DataFrame(columns=["per", "pbr", "roe", "profitMargin"])
            
        return prices_df, financial_df

