"""Agent 03, analysis 1: cross-sectional structure of the QSF-1.5.1 scores and factor values on the 2026-11-20 session.

Reads big/cards_151.json (offline dry scan with today's code).  Only statistics of scores and factor values: no return, IC or
performance figure.  Output: an1_structure.json and a printed summary.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
REPO = HERE.resolve().parents[3]
sys.path.insert(0, str(REPO))
from terminal.qsf import config

D = json.loads((HERE / "big" / "cards_151.json").read_text(encoding="utf-8"))
OUT = {}


def frame(market, strategy):
    cards = [c for c in D[market]["cards"].values() if c["strategy"] == strategy and c["score"] is not None]
    prof = config.profile_for(market, strategy)
    w = {f: wt for d in prof["domains"].values() for f, wt in d.items()}
    dom = {f: d for d, fs in prof["domains"].items() for f in fs}
    X = pd.DataFrame({c["ticker"]: {f["factor"]: f["normalized"] for f in c["factors"] if f.get("scored") is not False and f["status"] in ("REAL", "STALE")} for c in cards}).T
    X = X.reindex(columns=list(w)).astype(float)
    meta = pd.DataFrame({c["ticker"]: {"score": c["score"], "cons": c["conservative"], "band": c["band"], "act": c["actionability"], "conf": c["confidence"], "sector": c["sector"],
                                       "mcap": (c["fund"] or {}).get("market_cap"), "fin": bool((c["fund"] or {}).get("is_financial")), "entry": c["entry_status"],
                                       "held_back": c["held_back"], "cov": c["coverage"], "incov": c["input_coverage"]} for c in cards}).T
    meta["score"] = meta["score"].astype(float)
    status = pd.DataFrame({c["ticker"]: {f["factor"]: f["status"] for f in c["factors"] if f.get("scored") is not False} for c in cards}).T.reindex(columns=list(w))
    return cards, X, pd.Series(w), dom, meta, status


def score_of(X, w):
    have = X.notna()
    return 100 * (X.fillna(0) * w).sum(axis=1) / (have * w).sum(axis=1)


def parts(X, w):
    """Per stock, each factor's part of the score: 100 * w * x / available weight.  Rows sum to the score."""
    avail = (X.notna() * w).sum(axis=1)
    return (X.fillna(0) * w).div(avail, axis=0) * 100


for market in ("US", "KR"):
    for strategy in ("SWING", "LONG_TERM"):
        key = f"{market}_{strategy}"
        cards, X, w, dom, meta, status = frame(market, strategy)
        s = meta["score"]
        re = score_of(X, w)
        o = {"n": int(len(s)), "factors_scored": int(len(w)), "weight_total": float(w.sum()), "recompute_max_abs_diff": float((re - s).abs().max()),
             "mean": float(s.mean()), "sd": float(s.std()), "min": float(s.min()), "p25": float(s.quantile(.25)), "median": float(s.median()), "p75": float(s.quantile(.75)), "p90": float(s.quantile(.9)),
             "max": float(s.max()), "ge80": int((s >= 80).sum()), "ge75": int((s >= 75).sum()), "ge70": int((s >= 70).sum()), "ge67": int((s >= 67).sum()), "ge55": int((s >= 55).sum()), "lt40": int((s < 40).sum()),
             "share_ge70": float((s >= 70).mean()), "within1_of_70": int(((s - 70).abs() <= 1).sum()), "within2_of_70": int(((s - 70).abs() <= 2).sum()),
             "actionable": int((meta["act"] == "ACTIONABLE").sum()), "buy_band_actionable": int(((meta["act"] == "ACTIONABLE") & meta["band"].isin(["BUY_CANDIDATE", "STRONG_BUY_CANDIDATE"])).sum()),
             "score_ge70_actionable": int(((meta["act"] == "ACTIONABLE") & (s >= 70)).sum()), "held_back": int(meta["held_back"].fillna(False).astype(bool).sum())}
        # per factor
        fac = {}
        for f in w.index:
            col = X[f].dropna()
            st = status[f].value_counts().to_dict()
            if len(col) == 0:
                fac[f] = {"weight": float(w[f]), "domain": dom[f], "present": 0.0, "status": st}
                continue
            mode_share = float(col.round(4).value_counts(normalize=True).iloc[0])
            fac[f] = {"weight": float(w[f]), "domain": dom[f], "present": float(len(col) / len(X)), "mean": float(col.mean()), "sd": float(col.std()), "at0": float((col <= 1e-9).mean()), "at1": float((col >= 1 - 1e-9).mean()),
                      "mode_share": mode_share, "mode": float(col.round(4).value_counts().index[0]), "distinct": int(col.round(4).nunique()), "status": st,
                      "spearman_with_score": float(pd.concat([col, s], axis=1).corr(method="spearman").iloc[0, 1]) if col.nunique() > 1 else None}
        o["factors"] = fac
        # variance decomposition (parts sum to the score exactly)
        P = parts(X, w)
        var = float(s.var())
        contrib = {f: float(np.cov(P[f], re)[0, 1] / re.var()) for f in w.index}
        o["var_share_factor"] = contrib
        dshare, wshare = {}, {}
        for d in config.DOMAINS:
            fs = [f for f in w.index if dom[f] == d]
            if fs:
                dshare[d] = float(sum(contrib[f] for f in fs))
                wshare[d] = float(w[fs].sum() / w.sum())
        o["domain_var_share"], o["domain_weight_share"] = dshare, wshare
        pos = np.array([max(v, 0) for v in contrib.values()])
        pos = pos / pos.sum()
        o["enb_contrib"] = float(1 / (pos ** 2).sum())
        o["top3_var_share"] = float(sum(sorted(contrib.values(), reverse=True)[:3]))
        o["top3_factors"] = sorted(contrib, key=contrib.get, reverse=True)[:3]
        # correlation structure (factors with variance and enough coverage)
        use = [f for f in w.index if X[f].notna().mean() > 0.5 and X[f].nunique() > 2]
        C = np.array(X[use].corr(method="spearman", min_periods=30).fillna(0).values, dtype=float)
        np.fill_diagonal(C, 1.0)
        ev = np.clip(np.linalg.eigvalsh(C), 0, None)
        o["corr_factors_used"] = use
        o["enb_participation"] = float(ev.sum() ** 2 / (ev ** 2).sum())
        o["eig_gt1"] = int((ev > 1).sum())
        o["eig_top"] = [float(x) for x in sorted(ev, reverse=True)[:6]]
        pairs = []
        for i, a in enumerate(use):
            for j in range(i + 1, len(use)):
                if abs(C[i, j]) >= 0.5:
                    pairs.append([a, use[j], round(float(C[i, j]), 3)])
        o["pairs_abs_ge_0_5"] = sorted(pairs, key=lambda p: -abs(p[2]))
        o["share_pairs_lt_0_2"] = float((np.abs(C[np.triu_indices(len(use), 1)]) < 0.2).mean())
        # R2 of the score on its best 1 / 3 / 5 factors (greedy, OLS on mean-filled values)
        Xf = X.fillna(X.mean())
        Xf = Xf.loc[:, Xf.std() > 0]
        chosen, r2s = [], []
        for _ in range(5):
            best, bestr = None, -1
            for f in Xf.columns:
                if f in chosen:
                    continue
                A = np.column_stack([np.ones(len(Xf))] + [Xf[c].values for c in chosen + [f]])
                beta = np.linalg.lstsq(A, s.values, rcond=None)[0]
                r2 = 1 - ((s.values - A @ beta) ** 2).sum() / ((s.values - s.mean()) ** 2).sum()
                if r2 > bestr:
                    best, bestr = f, r2
            chosen.append(best)
            r2s.append(round(float(bestr), 3))
        o["greedy_r2"] = list(zip(chosen, r2s))
        # sector and size
        sec = meta["sector"].fillna("분류 없음")
        grand = s.mean()
        g = s.groupby(sec)
        ssb = float((g.size() * (g.mean() - grand) ** 2).sum())
        o["sector_eta2"] = ssb / float(((s - grand) ** 2).sum())
        buy = s >= 70
        o["sector_table"] = {k: {"n": int(g.size()[k]), "mean_dev": round(float(g.mean()[k] - grand), 2), "universe_share": round(float(g.size()[k] / len(s)), 3),
                                 "ge70": int(buy[sec == k].sum()), "ge70_share": round(float(buy[sec == k].sum() / max(buy.sum(), 1)), 3)} for k in g.size().index}
        adj = s - g.transform("mean")
        top = int(len(s) * 0.2)
        o["top20pct_overlap_after_sector_demean"] = float(len(set(s.nlargest(top).index) & set(adj.nlargest(top).index)) / top)
        mc = pd.to_numeric(meta["mcap"], errors="coerce")
        ok = mc.notna()
        o["size_spearman"] = float(pd.concat([s[ok], mc[ok]], axis=1).corr(method="spearman").iloc[0, 1])
        q = pd.qcut(mc[ok], 5, labels=False)
        o["size_quintile_mean"] = [round(float(s[ok][q == i].mean()), 1) for i in range(5)]
        o["fin_mean"], o["nonfin_mean"], o["fin_n"] = float(s[meta["fin"].astype(bool)].mean()), float(s[~meta["fin"].astype(bool)].mean()), int(meta["fin"].astype(bool).sum())
        o["fin_ge70"], o["nonfin_ge70"] = int(buy[meta["fin"].astype(bool)].sum()), int(buy[~meta["fin"].astype(bool)].sum())
        o["conf"] = meta["conf"].value_counts().to_dict()
        o["entry"] = meta["entry"].value_counts().to_dict()
        o["entry_in_buy_band"] = meta.loc[(meta["act"] == "ACTIONABLE") & meta["band"].isin(["BUY_CANDIDATE", "STRONG_BUY_CANDIDATE"]), "entry"].value_counts().to_dict()
        OUT[key] = o
    # swing vs long, same market
    a = {c["ticker"]: c["score"] for c in D[market]["cards"].values() if c["strategy"] == "SWING" and c["score"] is not None}
    b = {c["ticker"]: c["score"] for c in D[market]["cards"].values() if c["strategy"] == "LONG_TERM" and c["score"] is not None}
    common = sorted(set(a) & set(b))
    OUT[f"{market}_swing_long_spearman"] = float(pd.DataFrame({"a": [a[t] for t in common], "b": [b[t] for t in common]}).corr(method="spearman").iloc[0, 1])

(HERE / "an1_structure.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
for k, o in OUT.items():
    if not isinstance(o, dict):
        print(k, round(o, 3))
        continue
    print("=====", k)
    print({x: (round(o[x], 3) if isinstance(o[x], float) else o[x]) for x in ("n", "factors_scored", "weight_total", "recompute_max_abs_diff", "mean", "sd", "min", "median", "p90", "max", "ge80", "ge75", "ge70", "ge67", "share_ge70", "within1_of_70", "within2_of_70", "actionable", "buy_band_actionable", "score_ge70_actionable", "held_back")})
    print("ENB contrib", round(o["enb_contrib"], 2), "participation", round(o["enb_participation"], 2), "eig>1", o["eig_gt1"], "top3 var", o["top3_factors"], round(o["top3_var_share"], 3), "greedy R2", o["greedy_r2"])
    print("domain weight->var", {d: (round(o["domain_weight_share"][d], 3), round(o["domain_var_share"][d], 3)) for d in o["domain_var_share"]})
    for f, v in o["factors"].items():
        print("  %-26s w=%-3g pres=%.2f mean=%s sd=%s at0=%s at1=%s mode=%s(%s) rho=%s var=%.3f %s" % (f, v["weight"], v["present"], *(("%.2f" % v[x]) if v.get(x) is not None else "-" for x in ("mean", "sd", "at0", "at1", "mode", "mode_share")),
                                                                                               ("%.2f" % v["spearman_with_score"]) if v.get("spearman_with_score") is not None else "-", o["var_share_factor"][f], {k2: v2 for k2, v2 in v["status"].items() if k2 != "REAL"}))
    print("pairs", o["pairs_abs_ge_0_5"], "share<0.2", round(o["share_pairs_lt_0_2"], 2))
    print("sector eta2", round(o["sector_eta2"], 3), "overlap", round(o["top20pct_overlap_after_sector_demean"], 2), "size rho", round(o["size_spearman"], 2), o["size_quintile_mean"], "fin", o["fin_n"], round(o["fin_mean"], 1), round(o["nonfin_mean"], 1), "ge70 fin/non", o["fin_ge70"], o["nonfin_ge70"])
    print("sectors", o["sector_table"])
    print("conf", o["conf"], "entry", o["entry"], "entry in buy band", o["entry_in_buy_band"])
