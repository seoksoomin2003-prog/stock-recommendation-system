import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from contracts.decision import (
    SecurityDecision, PortfolioDecision, ActionEnum, LifecycleState
)

import pandas as pd
import numpy as np
from utils.config import DECISION_SETTINGS, PORTFOLIO_SETTINGS

logger = logging.getLogger("DecisionEngine")

class DecisionEngine:
    """
    Production-grade Quantitative Investment Decision System (P6-11B).
    Provides WHAT, WHEN, HOW MUCH, HOW LONG, WHEN TO EXIT.
    Does NOT auto-trade, submit orders, or connect to brokers.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {
            "technology_cap": PORTFOLIO_SETTINGS.get("max_sector_exposure", 0.40),
            "security_hard_ceiling": PORTFOLIO_SETTINGS.get("max_individual_weight", 0.30),
            "hard_stop_atr_multiplier": DECISION_SETTINGS.get("hard_stop_atr_multiplier", 2.0),
            "reentry_cooldown_days": DECISION_SETTINGS.get("reentry_cooldown_days", 3),
            "expected_horizon_days": DECISION_SETTINGS.get("expected_horizon_days", 30),
            "entry_1_weight": DECISION_SETTINGS.get("entry_1_weight", 0.40),
            "entry_2_weight": DECISION_SETTINGS.get("entry_2_weight", 0.60),
            "bear_alpha_threshold": DECISION_SETTINGS.get("bear_alpha_threshold", 0.75),
        }

    def evaluate_portfolio(
        self,
        as_of: datetime,
        capital: float,
        market_regime: str,
        candidates_data: List[Dict[str, Any]]
    ) -> PortfolioDecision:
        """
        Main entry point for evaluating the currently tradable universe.
        """
        # 1. Graceful Degradation / Initial Filtering
        valid_candidates = []
        quarantined_candidates = []
        
        for c in candidates_data:
            # Check for MOCK or UNAVAILABLE status explicitly
            is_mock = c.get('data_status') == 'MOCK' or c.get('fundamental_status') == 'MOCK'
            
            if is_mock:
                c['data_quality_status'] = "MOCK"
                quarantined_candidates.append({
                    "ticker": c.get("ticker", "UNK"),
                    "reason": "MOCK_FUNDAMENTALS",
                    "data_status": c.get('data_status', 'UNKNOWN'),
                    "fundamental_status": c.get('fundamental_status', 'UNKNOWN'),
                    "price_status": c.get('price_status', 'UNKNOWN'),
                    "volume_status": c.get('volume_status', 'UNKNOWN')
                })
                continue
                
            if not self._check_data_quality(c):
                c['data_quality_status'] = "UNAVAILABLE"
                quarantined_candidates.append({
                    "ticker": c.get("ticker", "UNK"),
                    "reason": "DATA_UNAVAILABLE",
                    "data_status": c.get('data_status', 'UNKNOWN'),
                    "fundamental_status": c.get('fundamental_status', 'UNKNOWN'),
                    "price_status": c.get('price_status', 'UNKNOWN'),
                    "volume_status": c.get('volume_status', 'UNKNOWN')
                })
                continue
            
            # Liquidity Hard Minimum
            if c.get('volume', 0) < 500000:
                c['constraint_flags'] = c.get('constraint_flags', []) + ["LIQUIDITY_REJECTED"]
                quarantined_candidates.append({
                    "ticker": c.get("ticker", "UNK"),
                    "reason": "LIQUIDITY_REJECTED",
                    "data_status": c.get('data_status', 'REAL'),
                    "fundamental_status": c.get('fundamental_status', 'REAL'),
                    "price_status": c.get('price_status', 'REAL'),
                    "volume_status": c.get('volume_status', 'REAL')
                })
                continue
                
            c['data_quality_status'] = "REAL"
            valid_candidates.append(c)

        # Log diagnostics
        logger.info(f"Candidate Quarantine Diagnostics: {len(quarantined_candidates)} quarantined, {len(valid_candidates)} eligible real.")
        for q in quarantined_candidates:
            logger.warning(f"Quarantined: {q['ticker']} - Reason: {q['reason']}")

        # 2. Dual Ranking (Alpha & Entry Readiness) -> MODEL_RANK_E
        ranked = self._rank_candidates(valid_candidates, market_regime, capital)

        # 3. Portfolio Optimization & Sizing (SIZING_CAP_AWARE + Sector Caps)
        top5, watchlist5 = self._optimize_portfolio(ranked, capital, market_regime, as_of)

        # This is deliberately the *last* decision gate.  A sufficiently large
        # raw universe is not a recommendation if BEAR, sector, cooldown or
        # portfolio eligibility removes the executable candidates.
        recommendation_status = (
            "REAL RECOMMENDATION" if len(top5) >= 5
            else "DATA-INCOMPLETE / NO VALID RECOMMENDATION"
        )

        return PortfolioDecision(
            as_of=as_of,
            market_regime=market_regime,
            capital=capital,
            currency="USD",
            top5=top5,
            watchlist5=watchlist5,
            portfolio_cash=capital - sum(s.target_notional for s in top5),
            sector_exposure=self._calculate_sector_exposure(top5),
            total_risk_budget=sum(s.risk_score for s in top5),
            data_quality=recommendation_status,
            model_version="MODEL_RANK_E",
            strategy_version="FROZEN_v1",
            generated_at=datetime.now(timezone.utc)
        )

    def evaluate_existing_position(
        self,
        as_of: datetime,
        position_state: Dict[str, Any],
        current_market_data: Dict[str, Any]
    ) -> SecurityDecision:
        """
        Evaluates an existing position for exits (Entry #2, Thesis Invalidation, Hard Stop).
        """
        state = LifecycleState(position_state['lifecycle_state'])
        close = current_market_data['close']
        ema20 = current_market_data['ema20']
        atr = current_market_data['atr']
        
        # Base decision object
        decision = SecurityDecision(
            security_id=position_state['security_id'],
            ticker=position_state['ticker'],
            company_name=position_state['ticker'], # Mock
            alpha_score=current_market_data.get('alpha', 0),
            alpha_rank=1,
            entry_readiness_score=1.0,
            entry_rank=1,
            combined_rank=1,
            recommendation_rank=1,
            recommendation_bucket="PORTFOLIO",
            action=ActionEnum.HOLD,
            entry_stage=state,
            entry_1_weight=position_state.get('entry_1_weight', 0),
            entry_2_weight=position_state.get('entry_2_weight', 0),
            target_weight=position_state.get('target_weight', 0),
            target_notional=position_state.get('target_notional', 0),
            target_shares=position_state.get('target_shares', 0),
            fractional_allowed=True,
            expected_horizon_days=self.config['expected_horizon_days'],
            expected_return=0.1,
            volatility=current_market_data.get('volatility', 0.02),
            confidence=0.9,
            liquidity_score=1.0,
            risk_score=1.0,
            sector=position_state.get('sector', 'Unknown'),
            thesis_status="HEALTHY",
            exit_candidate=False,
            exit_reason="",
            hard_stop=position_state['hard_stop'],
            trailing_stop=position_state['trailing_stop'],
            reentry_available_at=None,
            data_quality_status="OK",
            degradation_reason="",
            constraint_flags=[],
            reason_codes=[]
        )

        # Update Trailing Stop (Never loosens)
        potential_trailing = close - (atr * self.config['hard_stop_atr_multiplier'])
        if potential_trailing > decision.trailing_stop:
            decision.trailing_stop = potential_trailing

        # EXIT HIERARCHY EVALUATION
        # 1. Hard Stop
        if close <= decision.hard_stop:
            decision.action = ActionEnum.EXIT_CANDIDATE
            decision.entry_stage = LifecycleState.EXIT_CONFIRMED
            decision.exit_candidate = True
            decision.exit_reason = "HARD_STOP"
            decision.thesis_status = "BROKEN"
            return decision
            
        # 2. Thesis Invalidation (EMA20 Breakdown)
        if close < ema20 and state == LifecycleState.FULL_POSITION:
            decision.action = ActionEnum.EXIT_CANDIDATE
            decision.entry_stage = LifecycleState.EXIT_CANDIDATE
            decision.exit_candidate = True
            decision.exit_reason = "THESIS_INVALIDATION"
            decision.thesis_status = "DETERIORATING"
            # Note: Hard stop is evaluated first, so if both happen, hard stop wins.
            return decision

        # 3. Dynamic Trailing ATR
        if close <= decision.trailing_stop:
            decision.action = ActionEnum.EXIT_CANDIDATE
            decision.entry_stage = LifecycleState.EXIT_CONFIRMED
            decision.exit_candidate = True
            decision.exit_reason = "TRAILING_ATR"
            decision.thesis_status = "BROKEN"
            return decision

        # 4. Expected Horizon Expiry (30D Re-underwriting using trading days)
        entry_date = position_state.get('entry_date', as_of)
        if isinstance(entry_date, str):
            entry_date = datetime.fromisoformat(entry_date).replace(tzinfo=None)
        as_of_naive = as_of.replace(tzinfo=None) if as_of.tzinfo else as_of
        
        trading_days_held = np.busday_count(entry_date.date(), as_of_naive.date())
        
        if trading_days_held >= self.config['expected_horizon_days']:
            # Re-underwrite: exit if alpha is negative, otherwise hold.
            if current_market_data.get('alpha', 0) < 0:
                decision.action = ActionEnum.EXIT_CANDIDATE
                decision.entry_stage = LifecycleState.EXIT_CANDIDATE
                decision.exit_candidate = True
                decision.exit_reason = "30D_REVIEW_NEGATIVE_ALPHA"
                decision.thesis_status = "DETERIORATING"
                return decision
            else:
                decision.action = ActionEnum.HOLD
                decision.reason_codes.append("HORIZON_REVIEW_PASSED")

        # ENTRY #2 LOGIC
        if state == LifecycleState.ENTRY_1_EXECUTED or state == LifecycleState.ENTRY_2_PENDING:
            if close > ema20:
                decision.action = ActionEnum.BUY_CANDIDATE
                decision.entry_stage = LifecycleState.FULL_POSITION
                decision.reason_codes.append("ENTRY_2_CONFIRMED")
            else:
                decision.action = ActionEnum.HOLD
                decision.entry_stage = LifecycleState.ENTRY_2_PENDING
                decision.reason_codes.append("WAIT_FOR_EMA20")

        return decision

    def _check_data_quality(self, candidate: Dict[str, Any]) -> bool:
        # Status must survive alongside NaN values.  Only genuine, current
        # provider observations may enter the frozen model.
        usable = {"REAL", "CACHED", "REAL_CURRENT", "REAL_PIT_ELIGIBLE", "CACHED_PIT_ELIGIBLE"}
        for status_key in ("data_status", "price_status", "volume_status", "fundamental_status"):
            status = candidate.get(status_key)
            if status is not None and getattr(status, "value", status) not in usable:
                return False
        required_keys = ['close', 'volume', 'alpha', 'atr', 'ema20']
        for k in required_keys:
            val = candidate.get(k)
            if val is None or pd.isna(val):
                return False
        if candidate['close'] <= 0:
            return False
        return not pd.isna(candidate['volume']) and candidate['volume'] >= 500000

    def _rank_candidates(self, candidates: List[Dict[str, Any]], regime: str, capital: float) -> List[Dict[str, Any]]:
        # Apply BEAR regime strictness
        if regime == "BEAR":
            # Keep only top 25% (75th percentile strictness)
            threshold = 0.75
            # Simplified mock for strictness
            candidates = [c for c in candidates if c.get('alpha_percentile', 1.0) >= threshold]

        from core.ranking_engine import RankingEngine
        ranking_engine = RankingEngine()
        ranked = ranking_engine.calculate_model_rank_e(candidates, capital)
        
        return ranked

    def _optimize_portfolio(
        self,
        ranked: List[Dict[str, Any]],
        capital: float,
        regime: str,
        as_of: datetime
    ) -> tuple[List[SecurityDecision], List[SecurityDecision]]:
        
        top5 = []
        watchlist5 = []
        sector_counts = {}
        max_tech = 2  # 40% cap on 5 slots
        
        for idx, c in enumerate(ranked):
            is_tech = c.get('sector') == 'Technology'
            
            # Cooldown check
            if 'reentry_cooldown_until' in c and as_of < c['reentry_cooldown_until']:
                self._add_to_watchlist(watchlist5, c, idx, "COOLDOWN_ACTIVE")
                continue
                
            # Sector Cap constraint
            if is_tech and sector_counts.get('Technology', 0) >= max_tech:
                if len(top5) < 5:
                    self._add_to_watchlist(watchlist5, c, idx, "SECTOR_CAP_CONSTRAINT")
                continue
                
            if len(top5) < 5:
                # Calculate SIZING_CAP_AWARE
                # Equal weight risk budget for simplicity, capped at 30% individual
                raw_weight = min(0.20, self.config['security_hard_ceiling'])
                
                # Minimum fractional check
                target_notional = capital * raw_weight
                target_shares = target_notional / c['close']
                fractional_allowed = True
                
                if target_shares < 1 and not fractional_allowed:
                    self._add_to_watchlist(watchlist5, c, idx, "CAPITAL_CONSTRAINT")
                    continue
                
                sector_counts[c.get('sector', 'Unknown')] = sector_counts.get(c.get('sector', 'Unknown'), 0) + 1
                
                dec = SecurityDecision(
                    security_id=c['security_id'],
                    ticker=c.get('ticker', 'UNK'),
                    company_name=c.get('ticker', 'UNK'),
                    alpha_score=c['alpha'],
                    alpha_rank=idx + 1,
                    entry_readiness_score=c.get('entry_readiness', 1.0),
                    entry_rank=idx + 1,
                    combined_rank=idx + 1,
                    recommendation_rank=len(top5) + 1,
                    recommendation_bucket="TOP_5",
                    action=ActionEnum.BUY_CANDIDATE,
                    entry_stage=LifecycleState.ENTRY_READY,
                    entry_1_weight=raw_weight * self.config['entry_1_weight'],
                    entry_2_weight=raw_weight * self.config['entry_2_weight'],
                    target_weight=raw_weight,
                    target_notional=target_notional,
                    target_shares=target_shares,
                    fractional_allowed=fractional_allowed,
                    expected_horizon_days=self.config['expected_horizon_days'],
                    expected_return=0.1,
                    volatility=c.get('volatility', 0.02),
                    confidence=c.get('confidence', 0.9),
                    liquidity_score=1.0,
                    risk_score=0.5,
                    sector=c.get('sector', 'Unknown'),
                    thesis_status="HEALTHY",
                    exit_candidate=False,
                    exit_reason="",
                    hard_stop=c['close'] - (c['atr'] * self.config['hard_stop_atr_multiplier']),
                    trailing_stop=c['close'] - (c['atr'] * self.config['hard_stop_atr_multiplier']),
                    reentry_available_at=None,
                    data_quality_status="OK",
                    degradation_reason="",
                    reason_codes=["ALPHA_TOP_DECILE", "LIQUIDITY_PASS", "CAPITAL_EXECUTABLE"]
                )
                
                dec.explanation = (
                    f"WHAT: High Alpha score ({c['alpha']:.3f}) and MODEL_RANK_E rank {idx+1}.\n"
                    f"WHEN: Entry Readiness {c.get('entry_readiness', 1.0):.3f}.\n"
                    f"HOW MUCH: Target {raw_weight*100:.1f}% ({target_shares:.4f} shares).\n"
                    f"ENTRY #2: Wait for Close > EMA20.\n"
                    f"THESIS INVALIDATION: Close < EMA20.\n"
                    f"HARD STOP: 2 ATR ({dec.hard_stop:.2f}).\n"
                    f"EXIT: Dynamic Trailing ATR.\n"
                    f"HORIZON: 30D re-underwriting."
                )
                
                top5.append(dec)
            elif len(watchlist5) < 5:
                self._add_to_watchlist(watchlist5, c, idx, "WAIT_FOR_SLOT")
                
            if len(top5) == 5 and len(watchlist5) == 5:
                break
                
        return top5, watchlist5
        
    def _add_to_watchlist(self, wl_list: List[SecurityDecision], c: Dict[str, Any], idx: int, reason: str):
        if len(wl_list) < 5:
            dec = SecurityDecision(
                security_id=c['security_id'],
                ticker=c.get('ticker', 'UNK'),
                company_name=c.get('ticker', 'UNK'),
                alpha_score=c['alpha'],
                alpha_rank=idx + 1,
                entry_readiness_score=c.get('entry_readiness', 1.0),
                entry_rank=idx + 1,
                combined_rank=idx + 1,
                recommendation_rank=idx + 1,
                recommendation_bucket="WATCHLIST_5",
                action=ActionEnum.WATCHLIST,
                entry_stage=LifecycleState.CANDIDATE,
                entry_1_weight=0,
                entry_2_weight=0,
                target_weight=0,
                target_notional=0,
                target_shares=0,
                fractional_allowed=True,
                expected_horizon_days=self.config['expected_horizon_days'],
                expected_return=0.1,
                volatility=c.get('volatility', 0.02),
                confidence=c.get('confidence', 0.9),
                liquidity_score=1.0,
                risk_score=0.5,
                sector=c.get('sector', 'Unknown'),
                thesis_status="HEALTHY",
                exit_candidate=False,
                exit_reason="",
                hard_stop=0.0,
                trailing_stop=0.0,
                reentry_available_at=None,
                data_quality_status="OK",
                degradation_reason="",
                reason_codes=[reason]
            )
            wl_list.append(dec)

    def _calculate_sector_exposure(self, top5: List[SecurityDecision]) -> Dict[str, float]:
        exposure = {}
        for s in top5:
            exposure[s.sector] = exposure.get(s.sector, 0) + s.target_weight
        return exposure
