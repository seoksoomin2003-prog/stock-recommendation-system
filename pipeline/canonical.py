"""The ONE canonical production route (P6-18 Phase B).

    tickers -> market data -> fundamentals -> normalisation -> provenance /
    required-data gate -> FactorEngine -> frozen ScoringEngine (DEFAULT weights)
    -> required-numeric + liquidity gate -> DecisionEngine (BEAR 75th pct ->
    MODEL_RANK_E -> sector cap / sizing -> top5 + watchlist) -> final validity

Both Automated Market Scan and Direct Ticker Evaluation call
``CanonicalPipeline.evaluate``.  This module only orchestrates and records; it
does not re-implement any frozen P6-11B rule.  Frozen behaviour lives in
``core.factor_engine``, ``core.scoring_engine``, ``core.ranking_engine``
(MODEL_RANK_E) and ``core.decision_engine`` and is invoked unchanged.

Input definitions supplied to the frozen engines (documented in
``reports/P6-18_IMPLEMENTATION_REPORT.md``):

* ``volume``  = 20-session average daily volume (the 500,000 threshold is an
  *average daily volume* rule; P6-12A researched it with 20-day ADV).  The last
  session volume is kept for diagnostics only.
* ``sector``  = provider sector label (yfinance).  The frozen sector cap
  applies to the literal ``"Technology"`` label, which is Yahoo's label; a
  missing sector is reported as ``Unknown`` and flagged, never guessed.
* ``atr`` / ``ema20`` / ``entry_readiness`` / ``alpha_percentile`` use the
  exact expressions of the P6-17.4 live route.
"""
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from utils import config as cfg
from utils.config import DEFAULT_FACTOR_WEIGHTS
from utils.logger import setup_logger
from utils.market_calendar import expected_latest_trading_session

logger = setup_logger("CanonicalPipeline")

USABLE_STATUSES = {"REAL", "CACHED", "REAL_CURRENT", "REAL_PIT_ELIGIBLE", "CACHED_PIT_ELIGIBLE"}
NO_RECOMMENDATION = "DATA-INCOMPLETE / NO VALID RECOMMENDATION"
REAL_RECOMMENDATION = "REAL RECOMMENDATION"
LIVE_DATA_UNAVAILABLE = "LIVE DATA UNAVAILABLE"
FACTOR_COLUMNS = ("momentum", "quality", "value", "low_volatility")


def _num(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


class CanonicalPipeline:
    def __init__(self, data_loader, factor_engine, ranking_engine, scoring_engine, decision_engine,
                 regime_engine, capital: float, checkpoint: Optional[Callable[..., None]] = None,
                 now: Optional[Callable[[], datetime]] = None):
        self.data_loader = data_loader
        self.factor_engine = factor_engine
        self.ranking_engine = ranking_engine
        self.scoring_engine = scoring_engine
        self.decision_engine = decision_engine
        self.regime_engine = regime_engine
        self.capital = float(capital)
        self._checkpoint = checkpoint or (lambda stage, **kw: None)
        self._now = now or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ API
    def evaluate(self, tickers: List[str], ciks: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        ciks = ciks or {}
        tickers = list(dict.fromkeys(tickers))  # stable de-duplication
        flow: Dict[str, Dict[str, Any]] = {t: {"ticker": t, "reasons": []} for t in tickers}
        if not tickers:
            return self._no_recommendation("UNIVERSE_UNAVAILABLE", flow, {}, status=LIVE_DATA_UNAVAILABLE)

        # 1. Market data acquisition (single shared download for price + volume)
        # yfinance ``end`` is exclusive: stop after the latest COMPLETED NYSE
        # session so an in-progress intraday bar is never treated as a close.
        latest_session = expected_latest_trading_session(self._now())
        end = (latest_session.tz_localize(None) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        start = (pd.Timestamp.now() - pd.Timedelta(days=cfg.LIVE_PRICE_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        prices = self.data_loader.get_price_data(tickers, start, end)
        volumes = self.data_loader.get_volume_data(tickers, start, end)
        price_status = dict(prices.attrs.get("provider_status", {}))
        volume_status = dict(volumes.attrs.get("provider_status", {}))
        market_ok = [t for t in tickers if t in prices.columns and not prices[t].dropna().empty]
        self._checkpoint("MARKET_DATA_ACQUISITION_COMPLETED",
                         requested=len(tickers), with_price_bars=len(market_ok),
                         status_counts=self._counts(price_status, tickers))
        provenance = {
            "market": {"provider": prices.attrs.get("provider", "yfinance"), "status": price_status,
                       "retrieved_at": prices.attrs.get("retrieved_at"), "last_bar": prices.attrs.get("last_bar", {})},
            "volume": {"provider": volumes.attrs.get("provider", "yfinance"), "status": volume_status,
                       "retrieved_at": volumes.attrs.get("retrieved_at")},
        }
        for t in tickers:
            flow[t].update(price_status=price_status.get(t, "UNAVAILABLE"),
                           volume_status=volume_status.get(t, "UNAVAILABLE"),
                           last_bar=prices.attrs.get("last_bar", {}).get(t))
        if not market_ok:
            # Required market-data gate failed for everyone: no secondary provider calls.
            for t in tickers:
                flow[t].update(stage_reached="MARKET_DATA", final_status="QUARANTINED",
                               reasons=["MARKET_DATA_UNAVAILABLE"])
            self._checkpoint("FINANCIAL_DATA_ACQUISITION_COMPLETED", skipped=True,
                             reason="NO_MARKET_DATA")
            return self._no_recommendation("MARKET_DATA_UNAVAILABLE", flow, provenance)

        # 2. Fundamentals (only for tickers that have market data: avoids wasted provider calls)
        financials = self.data_loader.get_financial_data(market_ok, ciks={t: ciks[t] for t in market_ok if t in ciks})
        financial_status = dict(financials.attrs.get("provider_status", {}))
        meta = dict(financials.attrs.get("security_meta", {}))
        field_prov = dict(financials.attrs.get("field_provenance", {}))
        provenance["financial"] = {"fields": field_prov, "status": financial_status}
        self._checkpoint("FINANCIAL_DATA_ACQUISITION_COMPLETED", requested=len(market_ok),
                         status_counts=self._counts(financial_status, market_ok))

        # 3. Normalisation + provenance / required-data gate (before any score exists)
        gated: List[str] = []
        for t in tickers:
            rec = flow[t]
            m = meta.get(t, {})
            rec.update(fundamental_status=financial_status.get(t, "UNAVAILABLE"),
                       name=m.get("name"), sector=m.get("sector") or "Unknown",
                       sector_source="yfinance" if m.get("sector") else None,
                       # P6-20-A5: raw provider label, normalised label, observation time and status
                       sector_raw=m.get("sector_raw"), sector_observed_at=m.get("sector_observed_at"),
                       sector_status=m.get("sector_status") or ("REAL" if m.get("sector") else "MISSING"),
                       quote_type=m.get("quote_type"), currency=m.get("currency"),
                       fundamentals={f: _num(financials.loc[t, f]) if t in financials.index else None
                                     for f in ("per", "pbr", "roe", "profitMargin")},
                       fundamental_provenance=field_prov.get(t))
            rejected = {k: rec[k] for k in ("price_status", "volume_status", "fundamental_status")
                        if rec[k] not in USABLE_STATUSES}
            if rejected:
                rec.update(stage_reached="PROVENANCE_GATE", final_status="QUARANTINED",
                           rejected_statuses=rejected)
                rec["reasons"].append("PROVENANCE_STATUS_REJECTED")
                if rec["price_status"] == "UNAVAILABLE" and not m.get("yf_info_ok", False):
                    rec["reasons"].append("SYMBOL_NOT_FOUND_OR_NO_PROVIDER_DATA")
                if rec["fundamental_status"] != "REAL":
                    missing = [f for f, v in rec["fundamentals"].items() if v is None]
                    if missing:
                        rec["missing_fundamentals"] = missing
                for fname, finfo in (field_prov.get(t) or {}).items():
                    if isinstance(finfo, dict) and (str(finfo.get("status", "")).startswith("REJECTED")
                                                    or finfo.get("rejected_provider_value")):
                        rec["reasons"].append(f"PROVIDER_VALUE_REJECTED_{fname.upper()}")
                if m.get("quote_type") and m["quote_type"] != "EQUITY":
                    rec["reasons"].append(f"NON_EQUITY_INSTRUMENT_{m['quote_type']}")
            else:
                gated.append(t)
        self._checkpoint("PROVENANCE_GATE_COMPLETED", passed=len(gated), quarantined=len(tickers) - len(gated))
        if not gated:
            return self._no_recommendation("NO_CANDIDATE_PASSED_PROVENANCE_GATE", flow, provenance)

        # 4. Frozen factor + scoring core on the gated cross-section only
        g_prices = prices[gated]
        factor_matrix = self.factor_engine.get_factor_matrix(g_prices, financials.loc[gated])
        standardized = self.ranking_engine.apply_cross_sectional_standardization(factor_matrix)
        frozen_scores = self.scoring_engine.calculate(standardized, weights=DEFAULT_FACTOR_WEIGHTS)
        percentiles = frozen_scores.rank(pct=True)
        self._checkpoint("FACTOR_ENGINE_COMPLETED", cross_section=len(gated),
                         scored=int(frozen_scores.notna().sum()),
                         factor_coverage={c: float(factor_matrix[c].notna().mean()) for c in factor_matrix.columns})

        # 5. Candidate construction + required-numeric / liquidity gate
        candidates: List[Dict[str, Any]] = []
        for t in gated:
            rec = flow[t]
            ps = g_prices[t].dropna()
            vs = volumes[t].dropna() if t in volumes else pd.Series(dtype=float)
            # P6-19 input hygiene (definition unchanged): one observation per session,
            # NaN sessions are not observations, negative volume is invalid data.
            vs = vs[~vs.index.duplicated(keep="last")].sort_index()
            vs = vs[vs >= 0]
            close = ps.iloc[-1] if not ps.empty else np.nan
            window = vs.tail(cfg.ADV_WINDOW_DAYS)
            adv = window.mean() if len(vs) >= cfg.ADV_WINDOW_DAYS else np.nan
            if len(ps) >= 15:
                atr = ps.pct_change().abs().rolling(14).mean().iloc[-1] * close
                ema20 = ps.ewm(span=20, adjust=False).mean().iloc[-1]
            else:
                atr, ema20 = np.nan, np.nan
            cand = {
                "security_id": f"live:{t}", "ticker": t, "close": close, "volume": adv,
                "alpha": frozen_scores.get(t, np.nan), "atr": atr, "ema20": ema20,
                "entry_readiness": float(close > ema20) if pd.notna(close) and pd.notna(ema20) else np.nan,
                "alpha_percentile": percentiles.get(t, np.nan),
                "sector": rec["sector"], "data_status": "REAL",
                "price_status": rec["price_status"], "volume_status": rec["volume_status"],
                "fundamental_status": rec["fundamental_status"],
            }
            rec.update(adv20_window={"observations": int(len(window)),
                                     "first": str(window.index[0].date()) if len(window) else None,
                                     "last": str(window.index[-1].date()) if len(window) else None,
                                     "unit": "shares/day (split-adjusted share volume, not dollar volume)",
                                     # P6-20-A4 provenance
                                     "source": "yfinance download Volume (auto_adjust=True)",
                                     "retrieved_at": volumes.attrs.get("retrieved_at"),
                                     "rule": "mean of last 20 valid session observations; missing != 0"},
                       close=_num(close), adv20=_num(adv), last_volume=_num(vs.iloc[-1]) if not vs.empty else None,
                       alpha=_num(cand["alpha"]), alpha_percentile=_num(cand["alpha_percentile"]),
                       atr=_num(atr), ema20=_num(ema20), entry_readiness=_num(cand["entry_readiness"]),
                       factors={c: _num(standardized.loc[t, c]) if c in standardized.columns else None
                                for c in FACTOR_COLUMNS})
            if rec["sector"] == "Unknown":
                rec["reasons"].append("SECTOR_UNKNOWN_CAP_NOT_APPLICABLE")
            if self.decision_engine._check_data_quality(cand):
                rec["liquidity"] = "PASS"
                candidates.append(cand)
                continue
            missing = [k for k in ("close", "volume", "alpha", "atr", "ema20")
                       if cand.get(k) is None or pd.isna(cand.get(k))]
            rec["stage_reached"] = "REQUIRED_DATA_GATE" if missing else "LIQUIDITY_GATE"
            rec["final_status"] = "QUARANTINED"
            if missing:
                rec["missing_fields"] = missing
                rec["reasons"].append("REQUIRED_NUMERIC_DATA_MISSING")
            elif not close > 0:
                rec["reasons"].append("NON_POSITIVE_PRICE")
            else:
                rec["liquidity"] = "FAIL"
                rec["reasons"].append("LIQUIDITY_REJECTED")
        liq_rejected = sum(1 for t in gated if flow[t].get("liquidity") == "FAIL")
        if not candidates:
            self._checkpoint("MODEL_RANK_E_COMPLETED", ranked=0, skipped=True)
            self._checkpoint("LIQUIDITY_GATE_COMPLETED", passed=0, rejected=liq_rejected)
            return self._no_recommendation("NO_CANDIDATE_PASSED_REQUIRED_DATA_OR_LIQUIDITY", flow, provenance)

        # 6. Frozen DecisionEngine: BEAR filter -> MODEL_RANK_E -> sector cap/sizing -> validity
        regime = self.regime_engine.detect_regime(
            prices[[c["ticker"] for c in candidates]].mean(axis=1)).get("regime", "sideways").upper()
        decision = self.decision_engine.evaluate_portfolio(self._now(), self.capital, regime, candidates)

        # MODEL_RANK_E evidence is read back from the frozen run (combined_score is
        # written by RankingEngine.calculate_model_rank_e inside DecisionEngine).
        ranked = sorted([c for c in candidates if "combined_score" in c],
                        key=lambda c: c["combined_score"], reverse=True)
        for rank, c in enumerate(ranked, 1):
            flow[c["ticker"]].update(model_rank_e_rank=rank, model_rank_e_score=_num(c["combined_score"]))
        self._checkpoint("MODEL_RANK_E_COMPLETED", regime=regime, ranked=len(ranked),
                         bear_filtered=len(candidates) - len(ranked))
        self._checkpoint("LIQUIDITY_GATE_COMPLETED", passed=len(candidates), rejected=liq_rejected)

        top = {s.ticker: s for s in decision.top5}
        watch = {s.ticker: s for s in decision.watchlist5}
        for c in candidates:
            rec = flow[c["ticker"]]
            rec["stage_reached"] = "PORTFOLIO_GATE"
            if "combined_score" not in c:
                rec["final_status"] = "BEAR_REJECTED"
                rec["reasons"].append("BEAR_REGIME_BELOW_75TH_PERCENTILE")
            elif c["ticker"] in top:
                s = top[c["ticker"]]
                rec.update(final_status="TOP5", recommendation_rank=s.recommendation_rank,
                           target_weight=s.target_weight, target_notional=s.target_notional,
                           target_shares=s.target_shares, entry_1_weight=s.entry_1_weight,
                           entry_2_weight=s.entry_2_weight, hard_stop=s.hard_stop,
                           trailing_stop=s.trailing_stop, horizon_days=s.expected_horizon_days,
                           reason_codes=list(s.reason_codes), explanation=s.explanation)
            elif c["ticker"] in watch:
                rec.update(final_status="WATCHLIST", reason_codes=list(watch[c["ticker"]].reason_codes))
                rec["reasons"].extend(watch[c["ticker"]].reason_codes)
            else:
                rec["final_status"] = "RANKED_NOT_SELECTED"
        self._checkpoint("PORTFOLIO_GATE_COMPLETED", top5=len(decision.top5), watchlist=len(decision.watchlist5),
                         sector_exposure=decision.sector_exposure)

        weights = pd.Series({s.ticker: s.target_weight for s in decision.top5}, dtype=float)
        scores = pd.Series({c["ticker"]: c["alpha"] for c in candidates}, dtype=float)
        quarantined = [self._quarantine_entry(flow[t]) for t in tickers if flow[t].get("final_status") == "QUARANTINED"]
        recommendation_status = decision.data_quality  # final truth, set by the last frozen gate
        self._checkpoint("FINAL_VALIDITY_GATE_COMPLETED", recommendation_status=recommendation_status)
        return {
            "status": "SUCCESS",
            "pipeline_status": "SUCCESS",
            "recommendation_status": recommendation_status,
            "model_version": decision.model_version,
            "strategy_version": decision.strategy_version,
            "scores": scores,
            "weights": weights,
            "portfolio_decision": decision,
            "quarantined_candidates": quarantined,
            "eligible_candidates_count": len(candidates),
            "final_tradable_candidates_count": len(decision.top5),
            "candidate_flow": flow,
            "funnel": self._funnel(flow, tickers, len(gated), len(candidates), len(ranked), decision),
            "diagnostics": {"provenance": provenance, "market_regime": regime},
        }

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _counts(statuses: Dict[str, str], tickers: List[str]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for t in tickers:
            s = statuses.get(t, "UNAVAILABLE")
            out[s] = out.get(s, 0) + 1
        return out

    @staticmethod
    def _quarantine_entry(rec: Dict[str, Any]) -> Dict[str, Any]:
        return {"ticker": rec["ticker"], "reason": rec["reasons"][0] if rec["reasons"] else "UNKNOWN",
                "all_reasons": list(rec["reasons"]),
                "missing_fields": rec.get("missing_fields", []),
                "rejected_statuses": rec.get("rejected_statuses", {}),
                "price_status": rec.get("price_status"), "volume_status": rec.get("volume_status"),
                "fundamental_status": rec.get("fundamental_status")}

    @staticmethod
    def _funnel(flow, tickers, gated, eligible, ranked, decision) -> Dict[str, Any]:
        reasons: Dict[str, int] = {}
        for t in tickers:
            if flow[t].get("final_status") == "QUARANTINED" and flow[t]["reasons"]:
                r = flow[t]["reasons"][0]
                reasons[r] = reasons.get(r, 0) + 1
        return {"requested": len(tickers), "passed_provenance_gate": gated,
                "passed_liquidity_and_required_data": eligible, "model_rank_e_ranked": ranked,
                "bear_rejected": eligible - ranked,
                "top5": len(decision.top5) if decision else 0,
                "watchlist": len(decision.watchlist5) if decision else 0,
                "quarantine_reasons": reasons}

    def _no_recommendation(self, reason: str, flow, provenance, status: str = LIVE_DATA_UNAVAILABLE) -> Dict[str, Any]:
        tickers = list(flow)
        for t in tickers:
            flow[t].setdefault("final_status", "QUARANTINED")
        self._checkpoint("FINAL_VALIDITY_GATE_COMPLETED", recommendation_status=NO_RECOMMENDATION, reason=reason)
        return {
            "status": status,
            "pipeline_status": reason,
            "recommendation_status": NO_RECOMMENDATION,
            "scores": pd.Series(dtype=float), "weights": pd.Series(dtype=float),
            "quarantined_candidates": [self._quarantine_entry(flow[t]) for t in tickers
                                       if flow[t].get("final_status") == "QUARANTINED"],
            "eligible_candidates_count": 0,
            "final_tradable_candidates_count": 0,
            "candidate_flow": flow,
            "funnel": self._funnel(flow, tickers, 0, 0, 0, None),
            "diagnostics": {"provenance": provenance or {}, "reason": reason},
        }
