"""AGENT 7: weaknesses of the live score, measured on recorded factor values.  No return is read."""
import json, sys
import numpy as np
sys.path.insert(0, "reports/score_reliability_audit_2026_11_25/scratch_07")
from common import *

out = {}
# 0. does the live formula recomputed from stored factor values reproduce the stored score?
rep = {}
for m, s in PROFILES:
    for d in sessions(m):
        fr = frame(m, d, s, judged_only=False)
        L = wmean(fr["X"], fr["w"])
        diff = np.abs(L - fr["stored"])
        rep[f"{m}_{s}_{d}"] = {"versions": fr["versions"], "n": len(L), "max_abs_diff": float(np.nanmax(diff)), "n_diff_gt_0.01": int((diff > 0.01).sum())}
out["reproduce"] = rep
print("== reproduce stored score from stored factor values under QSF-1.6.0 weights")
for k, v in rep.items():
    print(k, v)

# 1. where the line of 70 stands
line = {}
for m, s in PROFILES:
    rows = []
    for d in sessions(m):
        fr = frame(m, d, s)
        L = wmean(fr["X"], fr["w"])
        rows.append({"session": d, "n": len(L), "ge70": int((L >= 70).sum()), "ge80": int((L >= 80).sum()), "share70": float((L >= 70).mean()), "p50": float(np.median(L)),
                     "p80": float(np.percentile(L, 80)), "p90": float(np.percentile(L, 90)), "max": float(L.max()), "sd": float(L.std())})
    line[f"{m}_{s}"] = rows
out["line70_ledger"] = line
print("\n== line of 70 (current weights on ledger factor values)")
for k, rows in line.items():
    sh = [r["share70"] for r in rows]
    print(k, "sessions", len(rows), "ge70 min/med/max", min(r["ge70"] for r in rows), int(np.median([r["ge70"] for r in rows])), max(r["ge70"] for r in rows),
          "share% min/med/max", round(100 * min(sh), 1), round(100 * float(np.median(sh)), 1), round(100 * max(sh), 1),
          "median score", round(float(np.median([r["p50"] for r in rows])), 1), "p80", round(float(np.median([r["p80"] for r in rows])), 1),
          "p90", round(float(np.median([r["p90"] for r in rows])), 1), "max", round(max(r["max"] for r in rows), 1), "sd", round(float(np.median([r["sd"] for r in rows])), 1))

# 2. factor by factor: how much it separates stocks, and its share of the score's variance against its share of the weight
fac = {}
for m, s in PROFILES:
    acc = {}
    for d in sessions(m):
        fr = frame(m, d, s)
        X, w = fr["X"], fr["w"]
        have = np.isfinite(X)
        W = (have * w).sum(axis=1)
        contrib = np.where(have, X * w, 0.0) / W[:, None] * 100
        S = contrib.sum(axis=1)
        for j, f in enumerate(fr["names"]):
            col = X[:, j]
            v = col[np.isfinite(col)]
            a = acc.setdefault(f, {"weight": float(w[j]), "domain": fr["dom"][j], "valued": [], "modal": [], "distinct": [], "sd": [], "at0": [], "at1": [], "var_share": [], "rho_score": []})
            a["valued"].append(len(v) / len(col))
            if len(v):
                vals, cnt = np.unique(np.round(v, 6), return_counts=True)
                a["modal"].append(cnt.max() / len(v)); a["distinct"].append(len(vals)); a["sd"].append(float(v.std()))
                a["at0"].append(float((v <= 1e-9).mean())); a["at1"].append(float((v >= 1 - 1e-9).mean()))
                a["rho_score"].append(spearman(col, S))
            a["var_share"].append(float(np.cov(contrib[:, j], S)[0, 1] / S.var(ddof=1)))
    tot = sum(a["weight"] for a in acc.values())
    fac[f"{m}_{s}"] = {f: {"weight": a["weight"], "weight_share": a["weight"] / tot, "domain": a["domain"], **{k: (float(np.nanmean(a[k])) if a[k] else None) for k in ("valued", "modal", "distinct", "sd", "at0", "at1", "var_share", "rho_score")}} for f, a in acc.items()}
out["factors"] = fac
print("\n== factors: weight share vs share of score variance (mean over sessions)")
for k, v in fac.items():
    print("--", k)
    for f, a in sorted(v.items(), key=lambda x: -x[1]["weight"]):
        g = lambda x, n=2: "  -  " if a[x] is None else f"{a[x]:.{n}f}"
        print(f"  {f:26s} w {a['weight']:4.0f} wshare {a['weight_share']*100:5.1f}%  varshare {a['var_share']*100:6.1f}%  valued {g('valued')} modal {g('modal')} distinct {g('distinct',0)} sd {g('sd')} at0 {g('at0')} at1 {g('at1')} rho_with_score {g('rho_score')}")

# 3. risk/reward against the trend factors (swing)
rr = {}
for m in ("US", "KR"):
    acc = {"rho_trend": [], "rho_breakout": [], "rho_score_without": [], "at0": [], "top_fifth_norr_mean_rr": [], "all_mean_rr": []}
    for d in sessions(m):
        slot = DATA[(m, d, "SWING")]
        tick = sorted(t for t, r in slot["rows"].items() if r["score"] is not None and r["act"] != "INSUFFICIENT_DATA")
        get = lambda f: np.array([(slot["rows"][t]["fac"].get(f) or {}).get("n") if (slot["rows"][t]["fac"].get(f) or {}).get("st") in OK else np.nan for t in tick], dtype=float)
        r_, tr, bo = get("risk_reward"), get("trend_structure"), get("breakout_volume")
        fr = frame(m, d, "SWING")
        j = fr["names"].index("risk_reward")
        Z = fr["X"].copy(); Z[:, j] = np.nan
        nr = wmean(Z, fr["w"])
        acc["rho_trend"].append(spearman(r_, tr)); acc["rho_breakout"].append(spearman(r_, bo)); acc["rho_score_without"].append(spearman(fr["X"][:, j], nr))
        acc["at0"].append(float((r_[np.isfinite(r_)] <= 1e-9).mean()))
        top = top_set(nr, fr["tick"])
        idx = [i for i, t in enumerate(fr["tick"]) if t in top]
        acc["top_fifth_norr_mean_rr"].append(float(np.nanmean(fr["X"][idx, j]))); acc["all_mean_rr"].append(float(np.nanmean(fr["X"][:, j])))
    rr[m] = {k: float(np.nanmean(v)) for k, v in acc.items()}
out["risk_reward"] = rr
print("\n== risk/reward (swing): rank corr with the trend factors (stored reference values in KR), share at 0, mean in the top fifth of the score without it")
print(json.dumps(rr, indent=1))

# 4. sector make-up of the top fifth (long and swing)
sec = {}
for m, s in PROFILES:
    acc = {}
    for d in sessions(m):
        fr = frame(m, d, s)
        L = wmean(fr["X"], fr["w"])
        top = top_set(L, fr["tick"])
        for t, g in zip(fr["tick"], fr["sec"]):
            a = acc.setdefault(g or "분류 없음", [0, 0])
            a[0] += 1; a[1] += t in top
    n, k = sum(a[0] for a in acc.values()), sum(a[1] for a in acc.values())
    sec[f"{m}_{s}"] = {g: {"universe_share": a[0] / n, "top_share": a[1] / k} for g, a in sorted(acc.items(), key=lambda x: -x[1][1])}
out["sector_top_fifth"] = sec
print("\n== sector share: universe vs top fifth of the live score (pooled over sessions)")
for k, v in sec.items():
    print("--", k, " | ".join(f"{g} {a['universe_share']*100:.0f}%->{a['top_share']*100:.0f}%" for g, a in list(v.items())[:6]))

# 5. Korean (and US) inputs that are empty inside a factor: share of None per raw key, newest session
emp = {}
for m, s in PROFILES:
    d = sessions(m)[-1]
    slot = DATA[(m, d, s)]
    wd = weights(m, s)
    res = {}
    for f in wd:
        keys = {}
        nrow = 0
        for t, r in slot["rows"].items():
            v = r["fac"].get(f)
            if not v or v["st"] not in OK:
                continue
            nrow += 1
            for a, b in v["raw"].items():
                keys.setdefault(a, 0)
                keys[a] += b is None
        res[f] = {"with_value": nrow, "status_missing_or_na": len(slot["rows"]) - nrow, "none_share": {a: b / nrow for a, b in keys.items() if nrow and b / nrow >= 0.2}}
    emp[f"{m}_{s}"] = res
out["empty_inputs"] = emp
print("\n== inputs that are None in >=20% of the stocks that have the factor (newest session), and stocks without the factor")
for k, v in emp.items():
    print("--", k)
    for f, a in v.items():
        if a["none_share"] or a["status_missing_or_na"] > 0.05 * (a["with_value"] + a["status_missing_or_na"]):
            print(f"  {f:26s} no factor {a['status_missing_or_na']:4d}  ", {x: round(y, 2) for x, y in a["none_share"].items()})

# 6. duplicate factors: pairs with |rank corr| >= 0.8 (mean over sessions)
dup = {}
for m, s in PROFILES:
    names = None
    mats = []
    for d in sessions(m):
        fr = frame(m, d, s)
        names = fr["names"]
        k = len(names)
        C = np.full((k, k), np.nan)
        for a in range(k):
            for b in range(a + 1, k):
                C[a, b] = spearman(fr["X"][:, a], fr["X"][:, b])
        mats.append(C)
    M = np.nanmean(np.stack(mats), axis=0)
    dup[f"{m}_{s}"] = sorted([(names[a], names[b], round(float(M[a, b]), 3)) for a in range(len(names)) for b in range(a + 1, len(names)) if np.isfinite(M[a, b]) and abs(M[a, b]) >= 0.6], key=lambda x: -abs(x[2]))
out["duplicates"] = dup
print("\n== factor pairs with mean |rank corr| >= 0.6")
for k, v in dup.items():
    print("--", k, v)

json.dump(out, open(HERE / "w_weakness.json", "w"), ensure_ascii=False, indent=1, default=str)
