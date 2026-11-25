"""AGENT 7: (f) the fixed line of 70 against a percentile band, on ledger sessions and on the stored historical scores (scores
only: no price is joined); the stability of the correlation bundles; random weights; the day-to-day noise of a score.
Random numbers are used in the weight draws only (seeded).  No return is read."""
import gzip, json, sys
import numpy as np
sys.path.insert(0, "reports/score_reliability_audit_2026_11_25/scratch_07")
from common import *
from terminal.qsf import us_challenger as uc, kr_challenger as kc

out = {}
# ------------------------------------------------------------------ F1: stored historical scores of the current formula
HIST = {"US": "data/qsf/research/scores_current_us.json.gz", "KR": "research_data/krx_live/scores_current_cap.json.gz"}
hist = {}
for m, p in HIST.items():
    d = json.load(gzip.open(p, "rt"))
    by = {}
    for r in d["records"]:
        by.setdefault(r["i"], {})[r["t"]] = r
    idx = sorted(by)
    for s in ("SWING", "LONG_TERM"):
        rows = []
        prev = None
        for i in idx:
            sc = {t: r[s] for t, r in by[i].items() if r.get(s) is not None}
            v = np.array(list(sc.values()))
            tick = list(sc)
            ge = {t for t in tick if sc[t] >= 70}
            top20, top10 = top_set(v, tick, 0.2), top_set(v, tick, 0.1)
            row = {"date": d["dates"][i], "n": len(v), "ge70": len(ge), "share70": len(ge) / len(v), "median": float(np.median(v)), "p80": float(np.percentile(v, 80)), "p90": float(np.percentile(v, 90)), "sd": float(v.std())}
            if prev:
                both = set(sc) & set(prev["sc"])
                keep = lambda a, b: (len(a & b) / len(a & both)) if (a & both) else None
                row["kept70"], row["kept20"], row["kept10"] = keep(prev["ge"], ge), keep(prev["top20"], top20), keep(prev["top10"], top10)
                # a set of the same size as the day's >=70 set, chosen by rank: separates "fixed line" from "small set"
                k = len(prev["ge"])
                if k:
                    pk = set(sorted(prev["sc"], key=lambda t: -prev["sc"][t])[:k]); ck = set(sorted(sc, key=lambda t: -sc[t])[:k])
                    row["kept_topk_same_size"] = keep(pk, ck)
                dv = np.array([sc[t] - prev["sc"][t] for t in both])
                row["abs_d_median"], row["abs_d_p90"] = float(np.median(np.abs(dv))), float(np.percentile(np.abs(dv), 90))
            rows.append(row)
            prev = {"sc": sc, "ge": ge, "top20": top20, "top10": top10}
        sh = np.array([r["share70"] for r in rows]); ge = np.array([r["ge70"] for r in rows])
        yr = {}
        for r in rows:
            yr.setdefault(r["date"][:4], []).append(r["ge70"])
        m_ = lambda k: float(np.mean([r[k] for r in rows if r.get(k) is not None]))
        hist[f"{m}_{s}"] = {"dates": len(rows), "first": rows[0]["date"], "last": rows[-1]["date"], "mean_n": float(np.mean([r["n"] for r in rows])),
                            "ge70_min": int(ge.min()), "ge70_p10": float(np.percentile(ge, 10)), "ge70_median": float(np.median(ge)), "ge70_p90": float(np.percentile(ge, 90)), "ge70_max": int(ge.max()),
                            "share70_min": float(sh.min()), "share70_median": float(np.median(sh)), "share70_max": float(sh.max()), "dates_zero": int((ge == 0).sum()), "dates_under5": int((ge < 5).sum()),
                            "median_score_min": min(r["median"] for r in rows), "median_score_max": max(r["median"] for r in rows),
                            "kept70_21d": m_("kept70"), "kept_top20_21d": m_("kept20"), "kept_top10_21d": m_("kept10"), "kept_topk_same_size_21d": m_("kept_topk_same_size"),
                            "abs_d_21d_median": m_("abs_d_median"), "abs_d_21d_p90": m_("abs_d_p90"), "ge70_by_year": {y: round(float(np.mean(v)), 1) for y, v in yr.items()},
                            "corr_ge70_with_median_score": float(np.corrcoef(ge, [r["median"] for r in rows])[0, 1])}
out["history_bands"] = hist
print("== F1. stored historical scores of QSF-1.6.0 (scores only, 21 sessions apart)")
for k, v in hist.items():
    print(k, json.dumps({a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()}, ensure_ascii=False))

# ------------------------------------------------------------------ F2: ledger sessions, day to day: fixed 70 vs top x% vs buffered
led_b = {}
for m, s in PROFILES:
    days = sessions(m)
    pairs = [(a, b) for a, b in zip(days, days[1:]) if DATA[(m, a, s)]["model_versions"] == DATA[(m, b, s)]["model_versions"]]
    acc = {"kept70": [], "kept20": [], "kept10": [], "kept5": [], "flip70": [], "flip_top20": [], "near70": [], "abs_d_med": [], "abs_d_p90": [], "abs_d_p99": [], "place_d_med": [], "place_d_p90": []}
    for a, b in pairs:
        fa, fb = frame(m, a, s), frame(m, b, s)
        sa = dict(zip(fa["tick"], wmean(fa["X"], fa["w"]))); sb = dict(zip(fb["tick"], wmean(fb["X"], fb["w"])))
        common = sorted(set(sa) & set(sb))
        va, vb = np.array([sa[t] for t in common]), np.array([sb[t] for t in common])
        for name, share in (("kept20", 0.2), ("kept10", 0.1), ("kept5", 0.05)):
            A, B = top_set(va, common, share), top_set(vb, common, share)
            acc[name].append(len(A & B) / len(A))
        A70, B70 = set(np.array(common)[va >= 70]), set(np.array(common)[vb >= 70])
        if A70:
            acc["kept70"].append(len(A70 & B70) / len(A70))
        acc["flip70"].append(float(((va >= 70) != (vb >= 70)).mean()))
        cut_a, cut_b = np.percentile(va, 80), np.percentile(vb, 80)
        acc["flip_top20"].append(float(((va >= cut_a) != (vb >= cut_b)).mean()))
        acc["near70"].append(float((np.abs(va - 70) < 1.5).mean()))
        dv = np.abs(vb - va)
        acc["abs_d_med"].append(float(np.median(dv))); acc["abs_d_p90"].append(float(np.percentile(dv, 90))); acc["abs_d_p99"].append(float(np.percentile(dv, 99)))
        pa, pb = rank(va) / (len(va) - 1) * 100, rank(vb) / (len(vb) - 1) * 100
        acc["place_d_med"].append(float(np.median(np.abs(pb - pa)))); acc["place_d_p90"].append(float(np.percentile(np.abs(pb - pa), 90)))
    led_b[f"{m}_{s}"] = {"pairs": len(pairs), **{k: (float(np.mean(v)) if v else None) for k, v in acc.items()}}
out["ledger_bands"] = led_b
print("\n== F2. ledger, consecutive same-version sessions (1 day apart)")
for k, v in led_b.items():
    print(k, json.dumps({a: (round(b, 3) if isinstance(b, float) else b) for a, b in v.items()}))

# ------------------------------------------------------------------ D3: are the registered bundles still what the rule gives?
def derive(fr, at=0.5):
    X, names = fr["X"], fr["names"]
    keep = []
    for j, n in enumerate(names):
        v = X[:, j][np.isfinite(X[:, j])]
        if len(v) < 0.5 * X.shape[0]:
            continue
        _, cnt = np.unique(np.round(v, 6), return_counts=True)
        if cnt.max() / len(v) >= 0.9:
            continue
        keep.append(j)
    groups = [[j] for j in keep]
    for a in keep:
        for b in keep:
            if a < b:
                c = spearman(X[:, a], X[:, b])
                if np.isfinite(c) and abs(c) >= at:
                    ga = next(g for g in groups if a in g); gb = next(g for g in groups if b in g)
                    if ga is not gb:
                        ga.extend(gb); groups.remove(gb)
    return sorted(sorted(names[j] for j in g) for g in groups)

bund = {}
REG = {"US": uc.BUNDLES, "KR": kc.BUNDLES}
for m, s in PROFILES:
    reg = sorted(sorted(b) for b in REG[m][s])
    seen = {}
    same = 0
    ks = []
    for d in sessions(m):
        g = derive(frame(m, d, s, judged_only=False))
        key = json.dumps(g)
        seen[key] = seen.get(key, 0) + 1
        ks.append(len(g))
        same += g == reg
    bund[f"{m}_{s}"] = {"sessions": len(sessions(m)), "registered_bundles": len(reg), "sessions_equal_to_registered": same, "distinct_structures": len(seen), "bundles_min": min(ks), "bundles_max": max(ks),
                        "most_common": json.loads(max(seen, key=seen.get)), "most_common_count": max(seen.values()), "registered": reg}
out["bundle_stability"] = bund
print("\n== D3. the bundle rule re-applied to every session (threshold 0.5, same exclusions)")
for k, v in bund.items():
    print(k, {a: b for a, b in v.items() if a not in ("most_common", "registered")})
    print("   registered :", [b for b in v["registered"] if len(b) > 1], "| singles", sum(1 for b in v["registered"] if len(b) == 1))
    print("   most common:", [b for b in v["most_common"] if len(b) > 1], "| singles", sum(1 for b in v["most_common"] if len(b) == 1))

# ------------------------------------------------------------------ W6: random weights (seeded random numbers; no return)
rng = np.random.default_rng(20261125)
wsim = {}
for m, s in PROFILES:
    acc = {k: {"rho": [], "top": []} for k in ("x(0.8..1.2)", "x(0.5..1.5)", "iid_uniform", "iid_uniform_noise_factors")}
    for d in sessions(m)[-3:]:
        fr = frame(m, d, s)
        X, w = fr["X"], fr["w"]
        live = wmean(X, w)
        ltop = top_set(live, fr["tick"])
        noise = rng.random(X.shape)          # factors with no content at all, same weights: how alike two weightings of noise look
        nlive = wmean(noise, w); ntop = top_set(nlive, fr["tick"])
        for _ in range(200):
            for k, ww in (("x(0.8..1.2)", w * rng.uniform(0.8, 1.2, len(w))), ("x(0.5..1.5)", w * rng.uniform(0.5, 1.5, len(w))), ("iid_uniform", rng.uniform(0.0, 1.0, len(w)))):
                sc = wmean(X, ww)
                acc[k]["rho"].append(spearman(sc, live)); acc[k]["top"].append(len(top_set(sc, fr["tick"]) & ltop) / len(ltop))
            sc = wmean(noise, w * rng.uniform(0.8, 1.2, len(w)))
            acc["iid_uniform_noise_factors"]["rho"].append(spearman(sc, nlive)); acc["iid_uniform_noise_factors"]["top"].append(len(top_set(sc, fr["tick"]) & ntop) / len(ntop))
    wsim[f"{m}_{s}"] = {k: {"rho_median": float(np.median(v["rho"])), "rho_p5": float(np.percentile(v["rho"], 5)), "top_kept_median": float(np.median(v["top"])), "top_kept_p5": float(np.percentile(v["top"], 5))} for k, v in acc.items()}
out["random_weights"] = wsim
print("\n== W6. random weights, 200 draws x 3 newest sessions (the last row: +-20% on factors of pure noise)")
for k, v in wsim.items():
    print(k, json.dumps({a: {x: round(y, 3) for x, y in b.items()} for a, b in v.items()}))

json.dump(out, open(HERE / "bands_and_more.json", "w"), ensure_ascii=False, indent=1, default=str)
