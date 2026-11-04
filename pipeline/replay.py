"""Re-derive a run's portfolio decision from its own artifacts with the unmodified frozen
DecisionEngine (P6-19 F3; importable since P6-20). No network access."""
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from core.decision_engine import DecisionEngine


def eligible_candidates(flow: dict, exclude: Iterable[str] = ()) -> list:
    exclude = set(exclude)
    cands = []
    for t, r in flow.items():
        if r.get("liquidity") != "PASS" or t in exclude:
            continue
        cands.append({"security_id": f"live:{t}", "ticker": t, "close": r["close"], "volume": r["adv20"],
                      "alpha": r["alpha"], "atr": r["atr"], "ema20": r["ema20"],
                      "entry_readiness": r["entry_readiness"], "alpha_percentile": r["alpha_percentile"],
                      "sector": r["sector"], "data_status": "REAL", "price_status": r["price_status"],
                      "volume_status": r["volume_status"], "fundamental_status": r["fundamental_status"]})
    return cands


def decide(run_dir: Path, exclude: Iterable[str] = ()):
    run_dir = Path(run_dir)
    flow = json.loads((run_dir / "candidate_flow.json").read_text())["candidates"]
    val = json.loads((run_dir / "validation_result.json").read_text())
    cands = eligible_candidates(flow, exclude)
    decision = DecisionEngine().evaluate_portfolio(datetime.fromisoformat(val["executed_at"]), val["capital"],
                                                   val["market_regime"], cands)
    return val, cands, decision


def replay(run_dir: Path) -> dict:
    val, cands, decision = decide(run_dir)
    replay_top = [(s.ticker, round(s.target_weight, 10), round(s.target_shares, 6)) for s in decision.top5]
    recorded = [(r["ticker"], round(r["target_weight"], 10), round(r["target_shares"], 6))
                for r in val["recommendations"]]
    return {"run_id": val["run_id"], "eligible_replayed": len(cands),
            "recorded_status": val["recommendation_status"], "replayed_status": decision.data_quality,
            "recorded_top5": recorded, "replayed_top5": replay_top,
            "match": recorded == replay_top and val["recommendation_status"] == decision.data_quality}
