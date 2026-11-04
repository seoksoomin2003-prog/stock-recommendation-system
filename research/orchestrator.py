"""Canonical non-execution research runtime."""

from typing import Dict, Iterable, Optional

from contracts.research import ResearchOutput, ResearchRequest
from contracts.security import IdentityStatus
from entity.resolver_service import EntityResolutionService
from providers.adapters import (NewsProviderAdapter, SECProviderAdapter, TrendsProviderAdapter,
                                UnavailableProvider, YFinanceFinancialProvider, YFinanceMarketProvider)
from providers.base import ProviderContext, ProviderKind
from providers.orchestrator import ProviderOrchestrator
from providers.registry import ProviderRegistry
from .confidence import calculate_confidence
from .input_adapters import financial_to_frame, market_to_prices


class ResearchOrchestrator:
    """Research-only facade: deliberately imports no execution or portfolio modules."""
    def __init__(self, resolver: Optional[EntityResolutionService] = None,
                 providers: Optional[ProviderOrchestrator] = None):
        self.resolver = resolver or EntityResolutionService()
        self.providers = providers or self._default_providers()

    @staticmethod
    def _default_providers() -> ProviderOrchestrator:
        registry = ProviderRegistry()
        for provider in (YFinanceMarketProvider(), YFinanceFinancialProvider(), NewsProviderAdapter(),
                         SECProviderAdapter(), TrendsProviderAdapter(), UnavailableProvider(ProviderKind.SOCIAL),
                         UnavailableProvider(ProviderKind.MACRO)):
            registry.register(provider)
        return ProviderOrchestrator(registry)

    def research(self, request: ResearchRequest) -> ResearchOutput:
        security = self.resolver.resolve(request.query, request.request_id)
        if security.identity_status != IdentityStatus.RESOLVED:
            return ResearchOutput(request.request_id, security, None, 0.0, request.horizon, request.as_of,
                                  status=security.identity_status.value, risks=["security_not_resolved"])
        context = ProviderContext(request.request_id, request.as_of, request.lookback_days, mode=request.mode)
        values = {kind: self.providers.fetch(kind, security, context) for kind in ProviderKind}
        market, financial = values[ProviderKind.MARKET], values[ProviderKind.FINANCIAL]
        confidence = calculate_confidence(values.values())
        quality = {kind.value: {"status": item.status.value, "source": item.source,
                                "confidence": item.confidence, "observed_at": str(item.observed_at)}
                   for kind, item in values.items()}
        if market.status.value not in {"REAL", "CACHED", "STALE"} or not market.data.get("close"):
            return ResearchOutput(request.request_id, security, None, confidence, request.horizon, request.as_of,
                                  data_quality=quality, status="SCORE_UNAVAILABLE", risks=["market_unavailable"])
        import math
        import pandas as pd
        import numpy as np

        prices = market_to_prices(market)
        if prices.columns[0] is None or pd.isna(prices.columns[0]):
            prices.columns = [security.ticker]
            
        financials = financial_to_frame(financial) if financial.status.value in {"REAL", "CACHED", "STALE"} else None
        if financials is not None:
            if financials.index[0] is None or pd.isna(financials.index[0]):
                financials.index = [security.ticker]
                
        # 1. Volatility Observations
        vol_obs = len(prices)
        vol_req = 24
        vol_avail = "AVAILABLE" if vol_obs >= vol_req else "UNAVAILABLE"
        vol_reason = None if vol_avail == "AVAILABLE" else "INSUFFICIENT_HISTORY"
        
        # 2. Momentum Observations
        monthly_prices = prices.resample('ME').last()
        mom_obs = len(monthly_prices)
        mom_req = 14
        mom_avail = "AVAILABLE" if mom_obs >= mom_req else "UNAVAILABLE"
        mom_reason = None if mom_avail == "AVAILABLE" else "INSUFFICIENT_HISTORY"
        
        # 3. Value Observations
        val_obs = len(financials.dropna(subset=['per', 'pbr'])) if financials is not None and not financials.empty else 0
        val_req = 1
        val_avail = "AVAILABLE" if val_obs >= val_req else "UNAVAILABLE"
        val_reason = None if val_avail == "AVAILABLE" else "NO_FINANCIALS"
        
        # 4. Quality Observations
        qual_obs = len(financials.dropna(subset=['roe', 'profitMargin'])) if financials is not None and not financials.empty else 0
        qual_req = 1
        qual_avail = "AVAILABLE" if qual_obs >= qual_req else "UNAVAILABLE"
        qual_reason = None if qual_avail == "AVAILABLE" else "NO_FINANCIALS"

        from core.factor_engine import FactorEngine
        from core.regime_engine import RegimeEngine
        from core.scoring_engine import ScoringEngine
        from core.ranking_engine import RankingEngine

        factors = FactorEngine().get_factor_matrix(prices, financials)
        standardized = RankingEngine().apply_cross_sectional_standardization(factors)
        scores = ScoringEngine().calculate(standardized)
        
        score = float(scores.iloc[0]) if not scores.empty else np.nan
        
        # Determine risks and status based on factor availability
        risks = []
        if mom_avail == "UNAVAILABLE":
            risks.append("momentum_unavailable")
        if val_avail == "UNAVAILABLE":
            risks.append("value_unavailable")
        if qual_avail == "UNAVAILABLE":
            risks.append("quality_unavailable")
        if vol_avail == "UNAVAILABLE":
            risks.append("volatility_unavailable")
            
        # Hard NaN / Inf Gate
        if not math.isfinite(score) or pd.isna(score):
            return ResearchOutput(
                request_id=request.request_id,
                security=security,
                alpha_score=None,
                confidence=0.0,
                horizon=request.horizon,
                as_of=request.as_of,
                data_quality=quality,
                risks=risks + ["NON_FINITE_SCORE"],
                status="SCORE_UNAVAILABLE"
            )
            
        # Clipping Safety Gate: Only finite scores are clipped
        score = max(-1.0, min(1.0, score))
        
        # Reduce confidence if any core or other factor is missing
        if risks:
            confidence = max(0.0, confidence - 0.2 * len(risks))

        raw_components = {key: float(value) for key, value in factors.iloc[0].fillna(0.0).items()}
        components_mapped = {
            "momentum": raw_components.get("momentum", 0.0),
            "value": raw_components.get("value", 0.0),
            "quality": raw_components.get("quality", 0.0),
            "volatility": raw_components.get("low_volatility", 0.0),
            "news": 0.0,
            "sec": 0.0,
            "trends": 0.0
        }
        
        drivers = [
            {
                "factor": "momentum",
                "used": mom_avail == "AVAILABLE",
                "value": components_mapped["momentum"] if mom_avail == "AVAILABLE" else None,
                "status": mom_avail,
                "reason": mom_reason,
                "observations": mom_obs,
                "minimum_required_observations": mom_req
            },
            {
                "factor": "value",
                "used": val_avail == "AVAILABLE",
                "value": components_mapped["value"] if val_avail == "AVAILABLE" else None,
                "status": val_avail,
                "reason": val_reason,
                "observations": val_obs,
                "minimum_required_observations": val_req
            },
            {
                "factor": "quality",
                "used": qual_avail == "AVAILABLE",
                "value": components_mapped["quality"] if qual_avail == "AVAILABLE" else None,
                "status": qual_avail,
                "reason": qual_reason,
                "observations": qual_obs,
                "minimum_required_observations": qual_req
            },
            {
                "factor": "volatility",
                "used": vol_avail == "AVAILABLE",
                "value": components_mapped["volatility"] if vol_avail == "AVAILABLE" else None,
                "status": vol_avail,
                "reason": vol_reason,
                "observations": vol_obs,
                "minimum_required_observations": vol_req
            },
            {"factor": "news", "used": False, "value": 0.0, "reason": "isolated_from_core_factor"},
            {"factor": "sec", "used": False, "value": 0.0, "reason": "isolated_from_core_factor"},
            {"factor": "trends", "used": False, "value": 0.0, "reason": "isolated_from_core_factor"}
        ]
        
        return ResearchOutput(request.request_id, security, score, confidence, request.horizon, request.as_of,
                               components=components_mapped, drivers=drivers, data_quality=quality, risks=risks,
                               status="PARTIAL_RESULT" if risks else "OK")
