"""P6-20 ranking and data diagnostics (read-only, HYPOTHETICAL where marked).

Nothing here feeds back into production: scores, ranks, weights, eligibility and
portfolio construction are only *read* from run artifacts. Leave-one-out and
factor-ablation views are labelled hypothetical and are never offered as an
alternative recommendation.
"""
import json
import math
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

HYPOTHETICAL = "HYPOTHETICAL DIAGNOSTIC - does not change production scores, ranks, weights or portfolio"
EXTREME_Z = 3.0
DOMINANCE_SHARE = 0.5
SECTOR_WARN = 0.40


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def _flow(run_dir: Path) -> Dict[str, Any]:
    return json.loads((Path(run_dir) / "candidate_flow.json").read_text())["candidates"]


def factor_extremes(flow: Dict[str, Any], top_n: int = 3) -> Dict[str, Any]:
    scored = {t: c for t, c in flow.items() if c.get("factors") and c.get("alpha") is not None}
    out = {}
    factors = sorted({f for c in scored.values() for f in c["factors"]})
    for f in factors:
        vals = sorted(((t, c["factors"][f]) for t, c in scored.items() if _finite(c["factors"].get(f))),
                      key=lambda x: x[1])
        if not vals:
            continue
        arr = np.array([v for _, v in vals])
        out[f] = {"n": len(vals), "median": float(np.median(arr)), "min": vals[0], "max": vals[-1],
                  "lowest": vals[:top_n], "highest": vals[-top_n:][::-1],
                  "count_abs_z_gt_3": int((np.abs(arr) > EXTREME_Z).sum()),
                  "count_abs_z_gt_10": int((np.abs(arr) > 10).sum())}
    return out


def contribution_view(flow: Dict[str, Any], weights: Dict[str, float], tickers: List[str]) -> Dict[str, Any]:
    """Exact decomposition of the frozen alpha (weights renormalised over available factors)."""
    ranked = {t: c for t, c in flow.items() if c.get("model_rank_e_rank") is not None}
    alpha_order = sorted(ranked, key=lambda t: -ranked[t]["alpha"])
    out = {}
    for t in tickers:
        c = flow.get(t) or {}
        fz = c.get("factors") or {}
        avail = {f: w for f, w in weights.items() if _finite(fz.get(f))}
        tot = sum(avail.values())
        if not avail or not tot:
            out[t] = {"available": False}
            continue
        contrib = {f: w / tot * fz[f] for f, w in avail.items()}
        abs_tot = sum(abs(v) for v in contrib.values()) or 1.0
        dom = max(contrib, key=lambda f: abs(contrib[f]))
        ablation = {}
        for f in avail:
            rest = {g: w for g, w in avail.items() if g != f}
            rt = sum(rest.values())
            alt = sum(w / rt * fz[g] for g, w in rest.items()) if rt else float("nan")
            # alpha rank among ranked names if only this ticker's alpha were recomputed without f
            others = [ranked[o]["alpha"] for o in alpha_order if o != t]
            ablation[f] = {"alpha_without_factor": alt,
                           "alpha_rank_without_factor": 1 + sum(1 for a in others if a > alt) if _finite(alt) else None}
        out[t] = {"available": True, "alpha": c.get("alpha"), "contributions": contrib,
                  "reconstruction_error": abs(sum(contrib.values()) - c["alpha"]) if _finite(c.get("alpha")) else None,
                  "dominant_factor": dom, "dominant_share_of_abs": abs(contrib[dom]) / abs_tot,
                  "single_factor_dominates": abs(contrib[dom]) / abs_tot > DOMINANCE_SHARE,
                  "alpha_rank": (alpha_order.index(t) + 1) if t in alpha_order else None,
                  "factor_ablation": {"label": HYPOTHETICAL, "views": ablation}}
    return out


def leave_one_out(run_dir: Path, top5: List[str]) -> Dict[str, Any]:
    """Portfolio-stage sensitivity: remove one TOP-5 name, re-run the frozen DecisionEngine with
    every other score held fixed, and show which name would take the slot."""
    from pipeline.replay import decide
    out = {"label": HYPOTHETICAL + " (scores held fixed; cross-sectional z-scores not recomputed)", "views": {}}
    for t in top5:
        _, _, dec = decide(run_dir, exclude=[t])
        new = [s.ticker for s in dec.top5]
        out["views"][t] = {"top5_without": new, "entered": [x for x in new if x not in top5],
                           "status": dec.data_quality}
    return out


def sector_view(flow: Dict[str, Any], top5_exposure: Dict[str, float], top_n: int = 20) -> Dict[str, Any]:
    ranked = sorted((c for c in flow.values() if c.get("model_rank_e_rank") is not None),
                    key=lambda c: c["model_rank_e_rank"])
    dist: Dict[str, int] = {}
    for c in ranked[:top_n]:
        dist[c.get("sector") or "Unknown"] = dist.get(c.get("sector") or "Unknown", 0) + 1
    return {"top5_exposure": top5_exposure,
            "top5_over_40pct": {s: w for s, w in (top5_exposure or {}).items() if w > SECTOR_WARN + 1e-12},
            "frozen_cap_scope": "Technology only (approved P6-11B rule; see reports/P6-20_SECTOR_CAP_REVIEW.md)",
            f"ranked_top{top_n}_sector_counts": dict(sorted(dist.items(), key=lambda x: -x[1]))}


def stop_distance(flow: Dict[str, Any], top5: List[str]) -> Dict[str, Any]:
    out = {}
    for t in top5:
        c = flow.get(t) or {}
        if _finite(c.get("close")) and _finite(c.get("hard_stop")) and c["close"]:
            out[t] = {"close": c["close"], "hard_stop": c["hard_stop"], "atr": c.get("atr"),
                      "distance_pct": 1 - c["hard_stop"] / c["close"]}
    return out


def run_diagnostics(run_record: Dict[str, Any], runs_dir="runs", weights=None) -> Dict[str, Any]:
    d = Path(runs_dir) / run_record["run_id"]
    if not (d / "candidate_flow.json").exists():
        return {"run_id": run_record["run_id"], "available": False, "reason": "RUN_ARTIFACTS_MISSING"}
    flow = _flow(d)
    manifest = json.loads((d / "run_manifest.json").read_text())
    weights = weights or ((manifest.get("frozen_core") or {}).get("values") or {}).get("DEFAULT_FACTOR_WEIGHTS", {})
    top5 = [p["ticker"] for p in run_record.get("top5") or []]
    return {"run_id": run_record["run_id"], "available": True,
            "factor_extremes": factor_extremes(flow),
            "top5_contributions": contribution_view(flow, weights, top5),
            "leave_one_out": leave_one_out(d, top5),
            "sector": sector_view(flow, run_record.get("sector_exposure") or {}),
            "hard_stop_distance": stop_distance(flow, top5)}


def ranking_stability(run_records: List[Dict[str, Any]], cohorts: Dict[str, str]) -> List[Dict[str, Any]]:
    """Consecutive full scans: TOP-5 Jaccard and Spearman rank correlation of MODEL_RANK_E."""
    runs = sorted(run_records, key=lambda r: r["recommendation_timestamp_utc"])
    out = []
    for a, b in zip(runs, runs[1:]):
        ta, tb = {p["ticker"] for p in a["top5"]}, {p["ticker"] for p in b["top5"]}
        ra, rb = a.get("ranked_model_rank_e") or {}, b.get("ranked_model_rank_e") or {}
        common = sorted(set(ra) & set(rb))
        rho = None
        if len(common) >= 3:
            x = np.argsort(np.argsort([ra[t] for t in common]))
            y = np.argsort(np.argsort([rb[t] for t in common]))
            rho = float(np.corrcoef(x, y)[0, 1])
        out.append({"from": a["run_id"], "to": b["run_id"], "from_cohort": cohorts.get(a["run_id"]),
                    "to_cohort": cohorts.get(b["run_id"]), "top5_jaccard": len(ta & tb) / len(ta | tb),
                    "common_ranked": len(common), "spearman_model_rank_e": rho})
    return out
