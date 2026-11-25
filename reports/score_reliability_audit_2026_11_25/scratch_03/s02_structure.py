"""AGENT 3, experiment 2: structure of the score on recorded factor values (no return, no price outcome).

(a) drop-one-factor / drop-one-domain / equal-weight recomputation of the composite from the recorded normalized values:
    rank correlation with the recorded score, overlap of the top 20, count at 70+.
(b) financial companies (marked by NOT_APPLICABLE on leverage / cash_flow_quality) against the rest: score level, share at 70+.
(c) the highest value each factor reached (structural ceilings).
(d) effective bets (weighted participation ratio) on every recorded session, to see whether the one-day figure is stable.
"""
import json, sys
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np
import pandas as pd
from terminal.qsf.ledger import Ledger
from terminal.qsf.order_plan import session_snaps
from terminal.qsf import config

led = Ledger(Path("."))
SESSION = sys.argv[1] if len(sys.argv) > 1 else "2026-11-24"
OUT = Path(__file__).parent / "s02_out.json"


def rho(a, b):
    a, b = pd.Series(a), pd.Series(b)
    ok = a.notna() & b.notna()
    return float(a[ok].rank().corr(b[ok].rank()))


def composite(rows, weights):
    w = c = 0.0
    for r in rows:
        wt = weights.get(r["factor"], 0)
        if wt and r.get("status") in ("REAL", "STALE") and r.get("normalized") is not None:
            w += wt; c += wt * r["normalized"]
    return 100 * c / w if w else None


def top(scores, n=20):
    s = pd.Series(scores).dropna().sort_values(ascending=False)
    return set(s.index[:n])


res = {}
for market in ("US", "KR"):
    allsn = session_snaps(led, market, SESSION)
    for strategy in ("SWING", "LONG_TERM"):
        snaps = [s for s in allsn if s["strategy"] == strategy]
        profile = config.profile_for(market, strategy)
        W = {f: w for d in profile["domains"].values() for f, w in d.items()}
        dom = {f: d for d, fs in profile["domains"].items() for f in fs}
        live = {s["ticker"]: s["score"] for s in snaps}
        base = {s["ticker"]: composite(s["factors"], W) for s in snaps}
        chk = max(abs(base[t] - live[t]) for t in live if live[t] is not None and base[t] is not None)
        n70 = sum(1 for v in base.values() if v is not None and v >= 70)
        out = {"n": len(snaps), "recompute_max_abs_diff": chk, "ge70": n70, "drop_factor": {}, "drop_domain": {}}
        for f in W:
            alt = {s["ticker"]: composite(s["factors"], {k: v for k, v in W.items() if k != f}) for s in snaps}
            out["drop_factor"][f] = {"weight": W[f], "rho": rho(base, alt), "top20_kept": len(top(base) & top(alt)), "ge70": sum(1 for v in alt.values() if v is not None and v >= 70),
                                     "mean_shift": float(np.nanmean([alt[t] - base[t] for t in base if alt[t] is not None and base[t] is not None]))}
        for d in set(dom.values()):
            keep = {k: v for k, v in W.items() if dom[k] != d}
            if not keep:
                continue
            alt = {s["ticker"]: composite(s["factors"], keep) for s in snaps}
            out["drop_domain"][d] = {"weight": sum(v for k, v in W.items() if dom[k] == d), "rho": rho(base, alt), "top20_kept": len(top(base) & top(alt)), "ge70": sum(1 for v in alt.values() if v is not None and v >= 70)}
            only = {k: v for k, v in W.items() if dom[k] == d}
            alt2 = {s["ticker"]: composite(s["factors"], only) for s in snaps}
            out["drop_domain"][d]["domain_alone_rho_with_score"] = rho(base, alt2)
        eq = {s["ticker"]: composite(s["factors"], {k: 1 for k in W}) for s in snaps}
        out["equal_weight"] = {"rho": rho(base, eq), "top20_kept": len(top(base) & top(eq)), "ge70": sum(1 for v in eq.values() if v is not None and v >= 70)}
        # (b) financials
        fin = {s["ticker"]: any(r["factor"] in ("leverage", "cash_flow_quality") and r["status"] == "NOT_APPLICABLE" for r in s["factors"]) for s in snaps}
        fs = [base[t] for t in base if fin[t] and base[t] is not None]; nf = [base[t] for t in base if not fin[t] and base[t] is not None]
        out["financial"] = {"n": len(fs), "mean": float(np.mean(fs)) if fs else None, "ge70": sum(1 for v in fs if v >= 70), "share_ge70": float(np.mean([v >= 70 for v in fs])) if fs else None,
                            "rest_n": len(nf), "rest_mean": float(np.mean(nf)), "rest_ge70": sum(1 for v in nf if v >= 70), "rest_share_ge70": float(np.mean([v >= 70 for v in nf])),
                            "top_fifth_share_financial": float(np.mean([fin[t] for t in top(base, max(1, len(base) // 5))]))}
        # scored weight actually available per stock (what the 100 is divided by)
        avail = [sum(W.get(r["factor"], 0) for r in s["factors"] if r.get("status") in ("REAL", "STALE") and r.get("normalized") is not None) for s in snaps]
        out["available_weight"] = {"nominal": sum(W.values()), "median": float(np.median(avail)), "min": float(np.min(avail)), "p10": float(np.percentile(avail, 10)), "counter_fin": float(np.median([a for a, s in zip(avail, snaps) if fin[s["ticker"]]])) if fs else None}
        # (c) ceilings
        mx = defaultdict(float); mn = defaultdict(lambda: 1.0)
        for s in snaps:
            for r in s["factors"]:
                if r.get("normalized") is not None and W.get(r["factor"]):
                    mx[r["factor"]] = max(mx[r["factor"]], r["normalized"]); mn[r["factor"]] = min(mn[r["factor"]], r["normalized"])
        out["ceiling"] = {f: [round(mn[f], 3), round(mx[f], 3)] for f in W if f in mx}
        out["max_reachable_score_observed_ceilings"] = 100 * sum(W[f] * mx[f] for f in mx) / sum(W[f] for f in mx)
        res[f"{market}_{strategy}"] = out
        print("=" * 100); print(market, strategy, SESSION, "n", out["n"], "recompute diff", f"{chk:.2e}", "ge70", n70, "| equal weight:", out["equal_weight"])
        print("  available weight", out["available_weight"], "| max reachable with observed ceilings", round(out["max_reachable_score_observed_ceilings"], 1))
        print("  financial", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out["financial"].items()})
        for d, v in sorted(out["drop_domain"].items(), key=lambda kv: kv[1]["rho"]):
            print(f"  drop domain {d:12s} w {v['weight']:>3}  rho {v['rho']:.3f}  top20 kept {v['top20_kept']:>2}  ge70 {v['ge70']:>3}  | domain alone vs score rho {v['domain_alone_rho_with_score']:.3f}")
        for f, v in sorted(out["drop_factor"].items(), key=lambda kv: kv[1]["rho"]):
            print(f"  drop {f:26s} w {v['weight']:>3}  rho {v['rho']:.4f}  top20 kept {v['top20_kept']:>2}  ge70 {v['ge70']:>3}  mean shift {v['mean_shift']:+.2f}  range {out['ceiling'].get(f)}")
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

# (d) effective bets on every session
print("=" * 100); print("weighted participation ratio / first eigen share per session (scored factors with sd>0, mean-imputed)")
for market in ("US", "KR"):
    for r in sorted({(x["session"]) for x in led._live_rows() if x["market"] == market}):
        sn = session_snaps(led, market, r)
        line = [market, r, sn[0].get("model_version")]
        for strategy in ("SWING", "LONG_TERM"):
            snaps = [s for s in sn if s["strategy"] == strategy]
            if len(snaps) < 100:
                line.append("n<100"); continue
            Wt = {}
            for s in snaps[:1]:
                Wt = {f["factor"]: f["weight"] for f in s["factors"] if f.get("weight")}
            fs = list(Wt)
            X = np.full((len(snaps), len(fs)), np.nan)
            for i, s in enumerate(snaps):
                for f in s["factors"]:
                    if f["factor"] in Wt and f.get("normalized") is not None and f.get("status") in ("REAL", "STALE") and f.get("weight"):
                        X[i, fs.index(f["factor"])] = f["normalized"]
            keep = [j for j in range(len(fs)) if np.isfinite(X[:, j]).sum() > 0.3 * len(snaps) and np.nanstd(X[:, j]) > 1e-6]
            Xi = X[:, keep]; Xi = np.where(np.isfinite(Xi), Xi, np.nanmean(Xi, axis=0))
            w = np.array([Wt[fs[j]] for j in keep], float)
            ev = np.sort(np.linalg.eigvalsh(np.cov(Xi * w, rowvar=False)))[::-1]
            evr = np.sort(np.linalg.eigvalsh(np.corrcoef(Xi, rowvar=False)))[::-1]
            line.append(f"{strategy[:5]} k={len(keep)} PRcorr={evr.sum()**2/(evr**2).sum():.1f} PRw={ev.sum()**2/(ev**2).sum():.2f} eig1={ev[0]/ev.sum():.2f}")
        print("  ", *line)
