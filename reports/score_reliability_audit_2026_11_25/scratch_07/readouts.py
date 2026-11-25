"""AGENT 7: (g) how much of risk and of data quality sits inside the one live score, and where the financial tilt comes from.
Recorded factor values only.  No return."""
import json, sys
import numpy as np
sys.path.insert(0, "reports/score_reliability_audit_2026_11_25/scratch_07")
from common import *

out = {}
for m, s in PROFILES:
    acc = {"rho_score_riskdomain": [], "rho_score_vol": [], "rho_attract_riskdomain": [], "rho_score_coverage": [], "share_with_missing": [], "share70_with_missing": [], "mean_gap_missing": [],
           "p90_gap_missing": [], "fin_mean": [], "nonfin_mean": [], "fin_na": [], "conf": {}, "held_back": []}
    facdiff = {}
    for d in sessions(m):
        fr = frame(m, d, s)
        X, w, dom, names, tick = fr["X"], fr["w"], fr["dom"], fr["names"], fr["tick"]
        live = wmean(X, w)
        rw = np.array([x if dd == "RISK" else 0.0 for x, dd in zip(w, dom)]); aw = w - rw
        risk = wmean(np.where(rw > 0, X, np.nan), rw); attract = wmean(np.where(aw > 0, X, np.nan), aw)
        rows = fr["slot"]["rows"]
        vol = np.array([((rows[t]["fac"].get("atr_risk") or rows[t]["fac"].get("downside_drawdown") or {}).get("raw") or {}).get("hist_vol" if s == "SWING" else "downside_vol") or np.nan for t in tick], dtype=float)
        cov = np.array([rows[t]["cov"] if rows[t]["cov"] is not None else np.nan for t in tick], dtype=float)
        acc["rho_score_riskdomain"].append(spearman(live, risk)); acc["rho_score_vol"].append(spearman(live, vol)); acc["rho_attract_riskdomain"].append(spearman(attract, risk))
        acc["rho_score_coverage"].append(spearman(live, cov))
        # missing = MISSING status of a scored factor (not NOT_APPLICABLE, not a factor nobody has)
        never = config.NEVER_AVAILABLE.get((m, s), ())
        miss = np.array([sum(1 for f in names if (rows[t]["fac"].get(f) or {}).get("st") == "MISSING" and f not in never) for t in tick])
        Zm = X.copy()
        for i, t in enumerate(tick):
            for j, f in enumerate(names):
                if (rows[t]["fac"].get(f) or {}).get("st") == "MISSING" and f not in never:
                    Zm[i, j] = config.MISSING_NEUTRAL
        cons = wmean(Zm, w)
        acc["share_with_missing"].append(float((miss > 0).mean()))
        if (live >= 70).any():
            acc["share70_with_missing"].append(float((miss[live >= 70] > 0).mean()))
        if (miss > 0).any():
            g = (live - cons)[miss > 0]
            acc["mean_gap_missing"].append(float(g.mean())); acc["p90_gap_missing"].append(float(np.percentile(np.abs(g), 90)))
        fin = np.array([x == FIN[m] for x in fr["sec"]])
        acc["fin_mean"].append(float(live[fin].mean())); acc["nonfin_mean"].append(float(live[~fin].mean()))
        na = np.array([sum(1 for f in names if (rows[t]["fac"].get(f) or {}).get("st") == "NOT_APPLICABLE") for t in tick])
        acc["fin_na"].append(float(na[fin].mean()))
        for j, f in enumerate(names):
            a, b = X[fin, j], X[~fin, j]
            facdiff.setdefault(f, []).append((np.nanmean(a) if np.isfinite(a).any() else np.nan) - np.nanmean(b))
        for t, v in zip(tick, live):
            c = rows[t]["conf"]
            acc["conf"].setdefault(c, []).append(v)
        acc["held_back"].append(sum(1 for t in tick if rows[t].get("held_back")))
    res = {k: (float(np.nanmean(v)) if isinstance(v, list) and v else None) for k, v in acc.items() if k != "conf"}
    res["by_confidence"] = {k: {"n_per_session": len(v) / len(sessions(m)), "mean_score": float(np.mean(v))} for k, v in acc["conf"].items()}
    # what the financial sector gains or loses per factor, in score points: weight share x difference of means
    tot = sum(weights(m, s)[f][0] for f in facdiff)
    res["financial_minus_other_by_factor_pts"] = {f: round(float(np.nanmean(v)) * weights(m, s)[f][0] / tot * 100, 2) for f, v in sorted(facdiff.items(), key=lambda x: -abs(np.nanmean(x[1]) * weights(m, s)[x[0]][0])) if np.isfinite(np.nanmean(v))}
    out[f"{m}_{s}"] = res
    print("==", m, s)
    print("  ", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res.items() if k not in ("by_confidence", "financial_minus_other_by_factor_pts")})
    print("   by confidence:", {k: {a: round(b, 1) for a, b in v.items()} for k, v in res["by_confidence"].items()})
    print("   financial minus other, weighted points by factor:", dict(list(res["financial_minus_other_by_factor_pts"].items())[:7]))
json.dump(out, open(HERE / "readouts.json", "w"), ensure_ascii=False, indent=1)
