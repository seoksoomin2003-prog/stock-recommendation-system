"""Operating modes on top of the canonical pipeline (P6-18 Phases C/E).

Mode A  run_market_scan(...)        current S&P 500 universe -> recommendations
Mode B  run_direct_evaluation(...)  user tickers evaluated inside the SAME
                                    canonical cross-section (S&P 500 + tickers)

Both modes: create a durable run directory first, call the one
``CanonicalPipeline``, then persist manifest / provider summary / candidate
flow / validation result / execution status (and failure.json on error).
"""
import re
import signal
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pipeline.canonical import (CanonicalPipeline, LIVE_DATA_UNAVAILABLE, NO_RECOMMENDATION,
                                REAL_RECOMMENDATION)
from pipeline.run_recorder import RunRecorder, frozen_config_fingerprint, peak_rss_mb
from utils import runtime_config
from utils.runtime_config import CapitalNotConfigured, parse_capital
from utils.logger import setup_logger

logger = setup_logger("PipelineService")

SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9]{0,5}([.\-][A-Z0-9]{1,3})?$")
# P6-19: there is deliberately NO default capital (the former 10,000,000 default
# silently sized portfolios for an amount the user never chose).
SECTOR_CAP_LIMIT = 0.40  # frozen value; the frozen engine enforces it for "Technology" only

OPERATIONAL_DISCLAIMER = (
    "A REAL RECOMMENDATION means the data and decision pipeline passed every operational gate. "
    "It does NOT mean the stocks will rise, that the ranking predicts returns, that the strategy is "
    "profitable, or that the system is institutionally validated. No orders are placed.")


class _Interrupted(BaseException):
    pass


def _raise_interrupt(signum, frame):  # pragma: no cover - signal path
    raise _Interrupted(f"Received signal {signum}")


def normalize_symbols(raw: List[str]) -> Dict[str, Any]:
    """Upper-case, split on commas/whitespace, map BRK.B -> BRK-B, validate format."""
    tokens: List[str] = []
    for item in raw:
        tokens.extend(t for t in re.split(r"[\s,;]+", str(item)) if t)
    valid, invalid, seen = [], [], set()
    for tok in tokens:
        sym = tok.strip().upper().lstrip("$")
        if not SYMBOL_RE.match(sym):
            invalid.append(tok)
            continue
        sym = sym.replace(".", "-")
        if sym not in seen:
            seen.add(sym)
            valid.append(sym)
    return {"valid": valid, "invalid": invalid}


def _build_system(capital: float):
    from main import QuantTradingSystemV2
    return QuantTradingSystemV2(mode="live", initial_capital=capital, run_research=False)


def _pipeline_for(system, recorder: RunRecorder) -> CanonicalPipeline:
    return CanonicalPipeline(system.data_loader, system.factor_engine, system.ranking_engine,
                             system.scoring_engine, system.decision_engine, system.regime_engine,
                             capital=system.portfolio_state.cash, checkpoint=recorder.checkpoint)


def _bootstrap_universe(recorder: RunRecorder, provider=None) -> Dict[str, Any]:
    from core.universe_provider import WikipediaSP500BootstrapProvider
    provider = provider or WikipediaSP500BootstrapProvider()
    universe = provider.get_live_universe()
    usable = universe.get("status") in {"SUCCESS", "SUCCESS_FROM_CACHE"} and universe.get("freshness_status") == "REAL"
    universe["usable"] = usable
    recorder.checkpoint("UNIVERSE_BOOTSTRAP_COMPLETED", status=universe.get("status"),
                        freshness=universe.get("freshness_status"),
                        constituents=len(universe.get("tickers", [])), ciks=len(universe.get("ciks", {})),
                        cik_map=universe.get("cik_map_provenance", {}).get("status"))
    return universe, provider


def _provider_summary(universe, system, result, extra=None) -> Dict[str, Any]:
    loader = system.data_loader
    prov = result.get("diagnostics", {}).get("provenance", {})
    flow = result.get("candidate_flow", {})

    def dist(key):
        out = {}
        for rec in flow.values():
            out[rec.get(key, "UNAVAILABLE")] = out.get(rec.get(key, "UNAVAILABLE"), 0) + 1
        return out

    field_sources: Dict[str, Dict[str, int]] = {}
    for fields in prov.get("financial", {}).get("fields", {}).values():
        for name, info in fields.items():
            if name.startswith("_") or not isinstance(info, dict):
                continue
            src = info.get("source") or "UNAVAILABLE"
            field_sources.setdefault(name, {})
            field_sources[name][src] = field_sources[name].get(src, 0) + 1
    sec_status: Dict[str, int] = {}
    cache_hits = 0
    for fields in prov.get("financial", {}).get("fields", {}).values():
        s = fields.get("_sec_status") or "NONE"
        sec_status[s] = sec_status.get(s, 0) + 1
        cache_hits += bool(fields.get("_cache_hit"))
    return {
        "universe": {k: universe.get(k) for k in ("status", "freshness_status", "source", "retrieved_at",
                                                  "constituent_count", "cache_age_days", "reason")},
        "cik_map": universe.get("cik_map_provenance") or getattr(getattr(loader, "ticker_map", None), "provenance", None),
        "market_data": {"provider": prov.get("market", {}).get("provider"),
                        "retrieved_at": prov.get("market", {}).get("retrieved_at"),
                        "price_status_distribution": dist("price_status"),
                        "volume_status_distribution": dist("volume_status"),
                        "last_bar_distribution": _value_counts(prov.get("market", {}).get("last_bar", {}))},
        "fundamentals": {"status_distribution": dist("fundamental_status"),
                         "field_source_distribution": field_sources,
                         "sec_extraction_status": sec_status, "cache_hits": cache_hits},
        "request_counts": getattr(loader, "request_counts", {}),
        "provider_events": getattr(loader, "provider_events", [])[-200:],
        "provider_event_count": len(getattr(loader, "provider_events", [])),
        **(extra or {}),
    }


def _sector_cap_warnings(exposure: Dict[str, float]) -> List[str]:
    """Display-only: the frozen engine caps 'Technology' at 2 of 5 slots; other sectors are not capped."""
    out = []
    for sector, weight in exposure.items():
        if sector != "Technology" and weight is not None and weight > SECTOR_CAP_LIMIT + 1e-9:
            out.append(f"{sector} exposure {weight:.0%} exceeds 40%: the frozen P6-11B sector cap is implemented "
                       f"for 'Technology' only, so this is reported, not enforced.")
        if sector == "Unknown":
            out.append("At least one selected position has no provider sector; the Technology cap cannot be "
                       "verified for it.")
    return out


def _value_counts(d: Dict[str, Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in d.values():
        out[str(v)] = out.get(str(v), 0) + 1
    return dict(sorted(out.items(), reverse=True))


def _recommendations(result) -> List[Dict[str, Any]]:
    flow = result.get("candidate_flow", {})
    top = [rec for rec in flow.values() if rec.get("final_status") == "TOP5"]
    return sorted(top, key=lambda r: r.get("recommendation_rank", 99))


def _watchlist(result) -> List[Dict[str, Any]]:
    flow = result.get("candidate_flow", {})
    return sorted([r for r in flow.values() if r.get("final_status") == "WATCHLIST"],
                  key=lambda r: r.get("model_rank_e_rank") or 10 ** 6)


def _display_status(result) -> str:
    if result.get("recommendation_status") == REAL_RECOMMENDATION:
        return REAL_RECOMMENDATION
    if result.get("pipeline_status") in {"UNIVERSE_UNAVAILABLE", "MARKET_DATA_UNAVAILABLE"}:
        return LIVE_DATA_UNAVAILABLE
    return NO_RECOMMENDATION


def _finish(recorder: RunRecorder, mode: str, universe, system, result, started, extra_validation=None,
            extra_provider=None) -> Dict[str, Any]:
    from pipeline import report
    flow = result.get("candidate_flow", {})
    decision = result.get("portfolio_decision")
    validation = {
        "run_id": recorder.run_id, "mode": mode,
        "executed_at": started.isoformat(),
        "pipeline_status": result.get("pipeline_status"),
        "execution_status": "PIPELINE_EXECUTED",
        "recommendation_status": result.get("recommendation_status"),
        "display_status": _display_status(result),
        "model_version": result.get("model_version"), "strategy_version": result.get("strategy_version"),
        "market_regime": result.get("diagnostics", {}).get("market_regime"),
        "capital": system.portfolio_state.cash, "currency": "USD",
        "capital_source": (getattr(recorder, "params", None) or {}).get("capital_source"),
        "sec_user_agent_status": runtime_config.sec_user_agent_status()["status"],
        "disclaimer": OPERATIONAL_DISCLAIMER,
        "eligible_candidates_count": result.get("eligible_candidates_count"),
        "final_tradable_candidates_count": result.get("final_tradable_candidates_count"),
        "funnel": result.get("funnel"),
        "recommendations": _recommendations(result),
        "watchlist": _watchlist(result),
        "sector_exposure": getattr(decision, "sector_exposure", {}),
        "sector_cap_warnings": _sector_cap_warnings(getattr(decision, "sector_exposure", {}) or {}),
        "portfolio_cash": getattr(decision, "portfolio_cash", None),
        "no_recommendation_reason": None if result.get("recommendation_status") == REAL_RECOMMENDATION else (
            result.get("diagnostics", {}).get("reason") or
            f"Only {result.get('final_tradable_candidates_count', 0)} portfolio-eligible positions; frozen rule requires 5."),
        **(extra_validation or {}),
    }
    provider = _provider_summary(universe, system, result, extra_provider)
    recorder.write("provider_summary.json", provider)
    recorder.write("candidate_flow.json", {"run_id": recorder.run_id, "funnel": result.get("funnel"),
                                           "candidates": flow})
    recorder.write("validation_result.json", validation)
    recorder.write_text("report.md", report.render_markdown(validation, provider, flow))
    recorder.write_text("report.html", report.render_html(validation, provider, flow))
    recorder.complete(recommendation_status=validation["recommendation_status"],
                      display_status=validation["display_status"],
                      peak_rss_mb=round(peak_rss_mb(), 1))
    if mode == "market_scan":
        # P6-20: immutable prospective ledger, built from the completed run's own artifacts.
        try:
            from pipeline import prospective_ledger
            from utils import config as cfg
            custom = recorder.root.resolve() != Path(cfg.RUNS_DIR).resolve()
            tracking_dir = str(recorder.root / "_tracking") if custom else None
            rec = prospective_ledger.record_run(recorder.dir, tracking_dir=tracking_dir)
            validation["forward_tracking"] = {"recorded_rows": rec.get("recorded_observations", 0),
                                              "eligible": rec.get("eligible"), "reasons": rec.get("reasons"),
                                              "ledger": rec.get("ledger")}
        except Exception as exc:  # observation must never break a run
            validation["forward_tracking"] = {"recorded_rows": 0, "error": f"{type(exc).__name__}: {exc}"}
    validation["artifact_dir"] = str(recorder.dir)
    return validation


def _guarded(mode: str, params: Dict[str, Any], body, runs_dir=None) -> Dict[str, Any]:
    recorder = RunRecorder(mode, params, runs_dir=runs_dir)
    previous = signal.signal(signal.SIGTERM, _raise_interrupt)
    try:
        return body(recorder)
    except (KeyboardInterrupt, _Interrupted) as exc:
        recorder.fail(exc, state="INTERRUPTED")
        logger.error(f"Run {recorder.run_id} interrupted; diagnostics in {recorder.dir}")
        raise
    except Exception as exc:
        recorder.fail(exc)
        logger.exception(f"Run {recorder.run_id} failed; diagnostics in {recorder.dir}")
        return {"run_id": recorder.run_id, "mode": mode, "execution_status": "FAILED",
                "display_status": LIVE_DATA_UNAVAILABLE, "recommendation_status": NO_RECOMMENDATION,
                "error": f"{type(exc).__name__}: {exc}", "artifact_dir": str(recorder.dir)}
    finally:
        signal.signal(signal.SIGTERM, previous)


def _universe_unavailable(recorder, mode, universe, system, started, extra=None):
    result = {"status": LIVE_DATA_UNAVAILABLE, "pipeline_status": "UNIVERSE_UNAVAILABLE",
              "recommendation_status": NO_RECOMMENDATION, "candidate_flow": {}, "eligible_candidates_count": 0,
              "final_tradable_candidates_count": 0,
              "funnel": {"requested": 0},
              "diagnostics": {"reason": f"Universe not usable: {universe.get('status')} "
                                        f"({universe.get('reason', 'no reason given')})"}}
    for stage in ("MARKET_DATA_ACQUISITION_COMPLETED", "FINANCIAL_DATA_ACQUISITION_COMPLETED",
                  "PROVENANCE_GATE_COMPLETED"):
        recorder.checkpoint(stage, skipped=True, reason="UNIVERSE_UNAVAILABLE")
    recorder.checkpoint("FINAL_VALIDITY_GATE_COMPLETED", recommendation_status=NO_RECOMMENDATION,
                        reason="UNIVERSE_UNAVAILABLE")
    return _finish(recorder, mode, universe, system, result, started, extra_validation=extra)


# ---------------------------------------------------------------- Mode A
def run_market_scan(capital: float, limit: Optional[int] = None,
                    runs_dir: Optional[str] = None, universe_provider=None, system=None,
                    capital_source: str = "caller") -> Dict[str, Any]:
    capital = parse_capital(capital)  # raises CapitalNotConfigured before any run or provider call
    params = {"capital": capital, "capital_source": capital_source, "limit": limit}

    def body(recorder: RunRecorder):
        started = datetime.now(timezone.utc)
        sys_ = system or _build_system(capital)
        universe, _ = _bootstrap_universe(recorder, universe_provider)
        if not universe["usable"] or not universe.get("tickers"):
            return _universe_unavailable(recorder, "market_scan", universe, sys_, started)
        tickers = list(universe["tickers"])
        scope = "full" if limit is None else "bounded"
        if limit is not None:
            tickers = tickers[:max(1, int(limit))]
        result = _pipeline_for(sys_, recorder).evaluate(tickers, universe.get("ciks", {}))
        return _finish(recorder, "market_scan", universe, sys_, result, started,
                       extra_validation={"validation_scope": scope, "universe_size": len(universe["tickers"]),
                                         "evaluated_tickers": len(tickers)})

    return _guarded("market_scan", params, body, runs_dir)


# ---------------------------------------------------------------- Mode B
def run_direct_evaluation(symbols: List[str], capital: float,
                          comparison_limit: Optional[int] = None, runs_dir: Optional[str] = None,
                          universe_provider=None, system=None, capital_source: str = "caller") -> Dict[str, Any]:
    capital = parse_capital(capital)  # raises CapitalNotConfigured before any run or provider call
    norm = normalize_symbols(symbols)
    params = {"capital": capital, "capital_source": capital_source, "symbols": symbols, "normalized": norm,
              "comparison_limit": comparison_limit}

    def body(recorder: RunRecorder):
        started = datetime.now(timezone.utc)
        sys_ = system or _build_system(capital)
        universe, provider = _bootstrap_universe(recorder, universe_provider)
        invalid = [{"input": s, "ticker": None, "verdict": "NOT_EVALUATED", "reasons": ["INVALID_SYMBOL_FORMAT"]}
                   for s in norm["invalid"]]
        if not norm["valid"]:
            raise ValueError(f"No valid ticker symbols supplied (invalid: {norm['invalid']})")
        if not universe["usable"] or not universe.get("tickers"):
            evals = invalid + [{"input": t, "ticker": t, "verdict": "NOT_EVALUATED",
                                "reasons": ["COMPARISON_UNIVERSE_UNAVAILABLE"],
                                "explanation": "The frozen model ranks cross-sectionally; without the canonical "
                                               "comparison universe no score can be produced."}
                               for t in norm["valid"]]
            return _universe_unavailable(recorder, "direct_evaluation", universe, sys_, started,
                                         extra={"ticker_evaluations": evals})
        comparison = list(universe["tickers"])
        if comparison_limit is not None:
            comparison = comparison[:max(1, int(comparison_limit))]
        members = set(universe["tickers"])
        ciks = dict(universe.get("ciks", {}))
        ticker_map = getattr(provider, "ticker_map", None)
        for t in norm["valid"]:
            if t not in ciks and ticker_map is not None:
                cik = ticker_map.cik(t)
                if cik:
                    ciks[t] = cik
        evaluated = list(dict.fromkeys(comparison + norm["valid"]))
        result = _pipeline_for(sys_, recorder).evaluate(evaluated, ciks)
        flow = result.get("candidate_flow", {})
        scored = (result.get("funnel") or {}).get("passed_provenance_gate", 0)
        evals = invalid + [ticker_verdict(t, flow.get(t, {}), t in members, t in ciks,
                                          result.get("recommendation_status"), scored, len(evaluated))
                           for t in norm["valid"]]
        return _finish(recorder, "direct_evaluation", universe, sys_, result, started,
                       extra_validation={"ticker_evaluations": evals,
                                         "comparison_universe": {"source": universe.get("source"),
                                                                 "size": len(comparison),
                                                                 "bounded": comparison_limit is not None,
                                                                 "cross_section_size": len(evaluated)}})

    return _guarded("direct_evaluation", params, body, runs_dir)


VERDICT_TEXT = {
    "TOP5": "Selected in the current frozen TOP-5 portfolio.",
    "WATCHLIST": "Eligible and ranked by MODEL_RANK_E, but placed on the watchlist (not in TOP-5).",
    "RANKED_NOT_SELECTED": "Eligible and ranked by MODEL_RANK_E, but below the TOP-5/watchlist slots.",
    "BEAR_REJECTED": "Eligible data, but BEAR regime requires alpha at or above the 75th percentile.",
    "QUARANTINED": "Not scored by the production model (see reasons).",
}


def ticker_verdict(ticker: str, rec: Dict[str, Any], in_universe: bool, has_cik: bool,
                   portfolio_status: str, cross_section: int, requested: int = None) -> Dict[str, Any]:
    status = rec.get("final_status", "QUARANTINED")
    reasons = list(rec.get("reasons", []))
    limitations = []
    if not in_universe:
        limitations.append("NOT_AN_SP500_CONSTITUENT: evaluated inside the S&P 500 comparison cross-section.")
    if not has_cik:
        limitations.append("NO_SEC_CIK: ROE/profit margin can only come from yfinance.")
    if rec.get("quote_type") and rec.get("quote_type") != "EQUITY":
        limitations.append(f"{rec.get('quote_type')}: the frozen model requires company fundamentals (PER/PBR/ROE/margin).")
    if "SYMBOL_NOT_FOUND_OR_NO_PROVIDER_DATA" in reasons:
        limitations.append("No market data or quote metadata was returned; the symbol may not exist or may be delisted.")
    return {
        "input": ticker, "ticker": ticker, "name": rec.get("name"), "in_sp500": in_universe,
        "verdict": status, "verdict_text": VERDICT_TEXT.get(status, status),
        "individual_evaluation": {
            "alpha": rec.get("alpha"), "alpha_percentile": rec.get("alpha_percentile"),
            "cross_section_size": cross_section, "requested_cross_section_size": requested,
            "factors": rec.get("factors"),
            "model_rank_e_rank": rec.get("model_rank_e_rank"), "model_rank_e_score": rec.get("model_rank_e_score"),
            "close": rec.get("close"), "adv20": rec.get("adv20"), "liquidity": rec.get("liquidity"),
            "entry_readiness": rec.get("entry_readiness"), "ema20": rec.get("ema20"), "atr": rec.get("atr"),
            "sector": rec.get("sector"), "fundamentals": rec.get("fundamentals"),
            "data_status": {k: rec.get(k) for k in ("price_status", "volume_status", "fundamental_status")},
            "last_bar": rec.get("last_bar"), "missing_fundamentals": rec.get("missing_fundamentals"),
        },
        "portfolio_level": {"portfolio_recommendation_status": portfolio_status,
                            "in_top5": status == "TOP5", "target_weight": rec.get("target_weight"),
                            "target_shares": rec.get("target_shares"), "hard_stop": rec.get("hard_stop")},
        "reasons": reasons, "limitations": limitations,
    }
