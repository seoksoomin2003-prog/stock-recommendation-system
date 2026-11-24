"""Agent 03: cross-sectional structure of the four QSF-1.5.2 profiles on the 2026-11-23 live record.
Only factor VALUES and scores of one stored session are used.  No return, IC or performance figure.  Random numbers serve as baselines."""
import json, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
from terminal.qsf import config
rng = np.random.default_rng(20261125)
BUY = ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE")


def rank(x):
    """Average ranks (ties share their mean rank); a first version without tie handling gave spurious correlations."""
    x = np.asarray(x, float)
    order = np.argsort(x, kind="mergesort")
    r = np.empty(len(x))
    xs = x[order]
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


def spear(a, b):
    ok = ~(np.isnan(a) | np.isnan(b))
    if ok.sum() < 10:
        return np.nan
    ra, rb = rank(a[ok]), rank(b[ok])
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def topk(s, k):
    return set(np.argsort(-s)[:k])


def composite(N, W):
    """N: cards x factors normalized with nan; W: weights vector (or matrix per draw)."""
    av = ~np.isnan(N)
    Nz = np.where(av, N, 0.0)
    return 100 * (Nz @ W) / (av.astype(float) @ W)


def pr(C):
    ev = np.linalg.eigvalsh(C)
    ev = np.clip(ev, 0, None)
    return float(ev.sum() ** 2 / (ev ** 2).sum()), int((ev > 1).sum())


def corrmat(N):
    X = N.copy()
    for j in range(X.shape[1]):
        col = X[:, j]
        col[np.isnan(col)] = np.nanmean(col) if np.isfinite(np.nanmean(col)) else 0.5
        X[:, j] = rank(col)
    C = np.corrcoef(X, rowvar=False)
    return np.nan_to_num(C, nan=0.0) + np.eye(X.shape[1]) * (np.isnan(np.corrcoef(X, rowvar=False)).any(axis=1) * 1.0)


out = {}
for market in ("US", "KR"):
    d = json.loads((HERE / "big" / f"s1123_{market}.json").read_text())
    for strat in ("SWING", "LONG_TERM"):
        cards = [c for c in d["cards"] if c["strategy"] == strat and c["score"] is not None]
        prof = config.profile_for(market, strat)
        fids = [f for dom in config.DOMAINS for f in prof["domains"][dom]]
        dom_of = {f: dom for dom in config.DOMAINS for f in prof["domains"][dom]}
        w = np.array([prof["domains"][dom_of[f]][f] for f in fids], float)
        N = np.array([[(c["f"].get(f) or [None, None])[1] if (c["f"].get(f) or ["x"])[0] in ("REAL", "STALE") else np.nan for f in fids] for c in cards], float)
        N = np.where(N is None, np.nan, N)
        st = [[(c["f"].get(f) or ["ABSENT"])[0] for f in fids] for c in cards]
        score = np.array([c["score"] for c in cards])
        S = composite(N, w)
        err = float(np.nanmax(np.abs(S - score)))
        # conservative re-computation
        never = config.NEVER_AVAILABLE.get((market, strat), ())
        cons_err = []
        for i, c in enumerate(cards):
            miss = sum(w[j] for j, f in enumerate(fids) if st[i][j] == "MISSING" and f not in never)
            av = ~np.isnan(N[i])
            tc, tw = float(np.nansum(N[i] * w)), float(w[av].sum())
            cons = 100 * (tc + 0.5 * miss) / (tw + miss)
            if c.get("cons") is not None:
                cons_err.append(abs(cons - c["cons"]))
        act = np.array([c["act"] == "ACTIONABLE" for c in cards])
        band = [c["band"] for c in cards]
        r = {"n": len(cards), "factors": len(fids), "points": float(w.sum()), "reproduce_max_err": err, "cons_max_err": max(cons_err) if cons_err else None,
             "mean": float(score.mean()), "sd": float(score.std()), "max": float(score.max()),
             "ge70": int((score >= 70).sum()), "ge80": int((score >= 80).sum()), "ge67": int((score >= 67).sum()), "ge75": int((score >= 75).sum()),
             "within1_of70": int((np.abs(score - 70) <= 1).sum()), "within2_of70": int((np.abs(score - 70) <= 2).sum()),
             "share_ge70": float((score >= 70).mean()),
             "buy_band_actionable": int(sum(1 for i, b in enumerate(band) if b in BUY and act[i])),
             "held_back": int(sum(1 for c in cards if c.get("held_back"))),
             "held_back_list": [(c["ticker"], round(c["score"], 2), round(c["cons"], 2)) for c in cards if c.get("held_back")],
             "entry_in_buy_band": {}, "entry_all_actionable": {}}
        for i, c in enumerate(cards):
            if act[i]:
                r["entry_all_actionable"][c["entry"]] = r["entry_all_actionable"].get(c["entry"], 0) + 1
            if band[i] in BUY and act[i]:
                r["entry_in_buy_band"][c["entry"]] = r["entry_in_buy_band"].get(c["entry"], 0) + 1
        r["missing_factor_cards"] = {f: int(sum(1 for i in range(len(cards)) if st[i][j] == "MISSING")) for j, f in enumerate(fids)}
        r["na_factor_cards"] = {f: int(sum(1 for i in range(len(cards)) if st[i][j] == "NOT_APPLICABLE")) for j, f in enumerate(fids)}
        fs = {}
        for j, f in enumerate(fids):
            col = N[:, j][~np.isnan(N[:, j])]
            if len(col) == 0:
                fs[f] = None
                continue
            vals, cnt = np.unique(np.round(col, 3), return_counts=True)
            fs[f] = {"w": float(w[j]), "mean": round(float(col.mean()), 3), "sd": round(float(col.std()), 3), "at0": round(float((col <= 1e-9).mean()), 3), "at1": round(float((col >= 1 - 1e-9).mean()), 3),
                     "mode": float(vals[cnt.argmax()]), "mode_share": round(float(cnt.max() / len(col)), 3), "max": round(float(col.max()), 3), "rho_score": round(spear(N[:, j], score), 3)}
        r["factor_stats"] = fs
        # correlation
        C = corrmat(N)
        pairs = []
        for a in range(len(fids)):
            for b in range(a + 1, len(fids)):
                rho = spear(N[:, a], N[:, b])
                if rho == rho and abs(rho) >= 0.5:
                    pairs.append((fids[a], fids[b], round(rho, 3)))
        r["pairs_ge_0_5"] = sorted(pairs, key=lambda x: -abs(x[2]))
        valid = [j for j in range(len(fids)) if np.nanstd(N[:, j]) > 0]
        Cv = C[np.ix_(valid, valid)]
        r["participation_ratio"], r["eig_gt1"] = pr(Cv)
        base_pr, base_eig = [], []
        for _ in range(100):
            R = rng.random((len(cards), len(valid)))
            p, e = pr(np.corrcoef(R, rowvar=False))
            base_pr.append(p); base_eig.append(e)
        r["pr_independent_baseline"] = round(float(np.mean(base_pr)), 2)
        r["eig_gt1_independent_baseline"] = round(float(np.mean(base_eig)), 2)
        # contribution variance shares (covariance attribution)
        av = ~np.isnan(N)
        denom = (av.astype(float) @ w)
        contrib = 100 * np.where(av, N, 0.0) * w / denom[:, None]
        var = S.var()
        share = {fids[j]: float(np.cov(contrib[:, j], S, bias=True)[0, 1] / var) for j in range(len(fids))}
        r["var_share_factor"] = {k: round(v, 3) for k, v in sorted(share.items(), key=lambda kv: -kv[1])}
        r["var_share_domain"] = {dom: round(sum(v for k, v in share.items() if dom_of[k] == dom), 3) for dom in config.DOMAINS if any(dom_of[k] == dom for k in fids)}
        r["weight_share_domain"] = {dom: round(sum(w[j] for j, k in enumerate(fids) if dom_of[k] == dom) / w.sum(), 3) for dom in r["var_share_domain"]}
        pos = np.clip(np.array(list(share.values())), 0, None)
        pos = pos / pos.sum()
        r["eff_factors_by_share"] = round(float(1 / (pos ** 2).sum()), 2)
        r["top3_share"] = round(float(np.sort(pos)[::-1][:3].sum()), 3)
        # leave one domain out
        k20 = 20
        base20, base_q = topk(S, k20), topk(S, len(S) // 5)
        lodo = {}
        for dom in r["var_share_domain"]:
            w2 = w.copy(); w2[[j for j, k in enumerate(fids) if dom_of[k] == dom]] = 0
            if w2.sum() == 0:
                continue
            S2 = composite(N, w2)
            lodo[dom] = {"rho": round(spear(S, S2), 3), "top20_kept": len(base20 & topk(S2, k20)), "top_quintile_kept": round(len(base_q & topk(S2, len(S) // 5)) / len(base_q), 3),
                         "ge70": int((S2 >= 70).sum())}
        r["leave_domain_out"] = lodo
        # leave one factor out (ge70 count moves)
        lofo = {}
        for j, f in enumerate(fids):
            w2 = w.copy(); w2[j] = 0
            S2 = composite(N, w2)
            lofo[f] = {"rho": round(spear(S, S2), 3), "top20_kept": len(base20 & topk(S2, k20)), "ge70": int((S2 >= 70).sum())}
        r["leave_factor_out"] = lofo
        # weight perturbation vs baselines
        Nshuf = N.copy()
        for j in range(N.shape[1]):
            Nshuf[:, j] = rng.permutation(N[:, j])
        Nrand = np.where(np.isnan(N), np.nan, rng.random(N.shape))
        pert = {}
        for name, draw in (("pm20", lambda: rng.uniform(0.8, 1.2, len(w))), ("pm50", lambda: rng.uniform(0.5, 1.5, len(w))),
                           ("x2_half", lambda: np.exp(rng.uniform(np.log(0.5), np.log(2.0), len(w))))):
            res = {}
            for lab, M in (("real", N), ("shuffled_columns", Nshuf), ("uniform_random", Nrand)):
                S0 = composite(M, w); b20 = topk(S0, k20)
                rhos, kept, ge = [], [], []
                for _ in range(300):
                    S2 = composite(M, w * draw())
                    rhos.append(spear(S0, S2)); kept.append(len(b20 & topk(S2, k20))); ge.append(int((S2 >= 70).sum()))
                res[lab] = {"rho_p5": round(float(np.percentile(rhos, 5)), 3), "top20_p5": int(np.percentile(kept, 5)), "top20_median": int(np.median(kept)),
                            "ge70_p5_p50_p95": [int(np.percentile(ge, q)) for q in (5, 50, 95)]}
            pert[name] = res
        r["weight_perturbation"] = pert
        S_eq = composite(N, np.ones_like(w))
        r["equal_weights"] = {"rho": round(spear(S, S_eq), 3), "top20_kept": len(base20 & topk(S_eq, k20)), "ge70": int((S_eq >= 70).sum())}
        # most dominant single factor
        r["max_single_factor_rho"] = max(((f, fs[f]["rho_score"]) for f in fids if fs[f]), key=lambda x: abs(x[1]))
        # sector and size
        sec = np.array([c.get("sector") or "?" for c in cards])
        ok = sec != "?"
        grand = S[ok].mean()
        ss_b = sum((S[ok & (sec == g)].mean() - grand) ** 2 * (ok & (sec == g)).sum() for g in set(sec[ok]))
        r["sector_eta2"] = round(float(ss_b / ((S[ok] - grand) ** 2).sum()), 3)
        tab = []
        for g in sorted(set(sec[ok])):
            m = ok & (sec == g)
            tab.append({"sector": g, "n": int(m.sum()), "share": round(float(m.sum() / ok.sum()), 3), "mean_minus_all": round(float(S[m].mean() - grand), 1),
                        "ge70": int(((S >= 70) & m).sum())})
        r["sector_table"] = sorted(tab, key=lambda t: -t["mean_minus_all"])
        r["ge70_total_with_sector"] = int(((S >= 70) & ok).sum())
        dem = S.copy()
        for g in set(sec[ok]):
            m = ok & (sec == g); dem[m] = S[m] - S[m].mean()
        q = len(S) // 5
        r["sector_demeaned_top_quintile_overlap"] = round(len(topk(S, q) & topk(dem, q)) / q, 3)
        mc = np.array([c.get("mcap") if c.get("mcap") else np.nan for c in cards], float)
        r["rho_score_mcap"] = round(spear(S, mc), 3)
        fin = np.array([bool(c.get("is_fin")) for c in cards])
        r["financials"] = {"n": int(fin.sum()), "share": round(float(fin.mean()), 3), "ge70": int(((S >= 70) & fin).sum()), "share_of_ge70": round(float(((S >= 70) & fin).sum() / max(1, (S >= 70).sum())), 3)}
        out[f"{market}_{strat}"] = r
    # swing vs long rank agreement
    sw = {c["ticker"]: c["score"] for c in d["cards"] if c["strategy"] == "SWING" and c["score"] is not None}
    lo = {c["ticker"]: c["score"] for c in d["cards"] if c["strategy"] == "LONG_TERM" and c["score"] is not None}
    common = sorted(set(sw) & set(lo))
    out[f"{market}_swing_vs_long_rho"] = round(spear(np.array([sw[t] for t in common]), np.array([lo[t] for t in common])), 3)
(HERE / "an_structure_1123.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
for k, r in out.items():
    if not isinstance(r, dict):
        print(k, r); continue
    print("==", k, {x: r[x] for x in ("n", "factors", "points", "reproduce_max_err", "cons_max_err", "mean", "sd", "max", "ge70", "ge80", "ge75", "ge67", "within1_of70", "within2_of70", "buy_band_actionable", "held_back")})
    print("  entry in buy band", r["entry_in_buy_band"])
    print("  PR", r["participation_ratio"], "vs", r["pr_independent_baseline"], "eig>1", r["eig_gt1"], "vs", r["eig_gt1_independent_baseline"], "eff by share", r["eff_factors_by_share"], "top3", r["top3_share"])
    print("  var dom", r["var_share_domain"], "weight dom", r["weight_share_domain"])
    print("  pairs", r["pairs_ge_0_5"])
    print("  lodo", r["leave_domain_out"])
    print("  pert", json.dumps(r["weight_perturbation"]))
    print("  equal", r["equal_weights"], "maxsingle", r["max_single_factor_rho"])
    print("  sector eta2", r["sector_eta2"], "demeaned overlap", r["sector_demeaned_top_quintile_overlap"], "mcap rho", r["rho_score_mcap"], "fin", r["financials"])
