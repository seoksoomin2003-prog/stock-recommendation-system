"""AGENT 7: alternatives to the live aggregation, built from recorded factor values, compared with the live score on what needs
no return: rank correlation, overlap of the top fifth and of the >=70 set, count >=70, sector concentration, day-to-day
stability, sensitivity to a missing factor.  Nothing is written outside scratch_07; no price or outcome is read."""
import json, sys
import numpy as np
sys.path.insert(0, "reports/score_reliability_audit_2026_11_25/scratch_07")
from common import *
from terminal.qsf import us_challenger as uc, kr_challenger as kc, research_ensemble as en

BUNDLES = {"US": uc.BUNDLES, "KR": kc.BUNDLES}
FUND_LIKE = ("FUNDAMENTAL",)          # the factors made sector-relative in B2 (plus leverage: debt/equity was in variant C's list)


def sector_pct(col, sec, min_peers=5):
    """within-sector percentile where the sector has >= min_peers valued stocks, else the absolute value (variant C's rule)."""
    out = col.copy()
    sec = np.array([s or "?" for s in sec])
    for g in set(sec):
        m = (sec == g) & np.isfinite(col)
        if g != "?" and m.sum() >= min_peers:
            out[m] = rank(col[m]) / (m.sum() - 1)
    return out


def bundle_agg(Z, names, bundles):
    """mean of the bundle means; a bundle needs half of its signals, a stock 70% of the bundles (the challengers' rule)."""
    cols = {n: Z[:, j] for j, n in enumerate(names)}
    return en.combine(cols, bundles)


def build(fr, market, strategy):
    """{alternative: (Z matrix after its own normalisation, aggregator Z -> score)}"""
    X, w, names, dom, sec = fr["X"], fr["w"], fr["names"], fr["dom"], fr["sec"]
    P = np.column_stack([pct_col(X[:, j]) for j in range(X.shape[1])])
    alts = {}
    alts["LIVE"] = (X, lambda Z: wmean(Z, w))
    alts["A_rank_norm"] = (P, lambda Z: wmean(Z, w))
    B2 = X.copy()
    for j, n in enumerate(names):
        if dom[j] in FUND_LIKE or n == "leverage":
            B2[:, j] = sector_pct(X[:, j], sec)
    alts["B2_sector_rel_fund"] = (B2, lambda Z: wmean(Z, w))
    eq = np.ones(len(w))
    alts["C1_equal_all"] = (X, lambda Z: wmean(Z, eq))
    wd = np.zeros(len(w))
    for d in set(dom):
        idx = [j for j in range(len(w)) if dom[j] == d]
        tot = w[idx].sum()
        wd[idx] = tot / len(idx)
    alts["C2_equal_in_domain"] = (X, lambda Z: wmean(Z, wd))
    bundles = BUNDLES[market][strategy]
    alts["D1_bundle_rank(challenger)"] = (P, lambda Z: bundle_agg(Z, names, bundles))
    alts["D2_bundle_abs"] = (X, lambda Z: bundle_agg(Z, names, bundles))
    if strategy == "SWING":
        wn = w.copy(); wn[names.index("risk_reward")] = 0.0
        alts["E_no_risk_reward"] = (X, lambda Z: wmean(np.where(wn > 0, Z, np.nan), wn))
    wg = np.array([0.0 if d == "RISK" else x for d, x in zip(dom, w)])
    alts["G_without_risk_domain"] = (X, lambda Z: wmean(np.where(wg > 0, Z, np.nan), wg))
    na = np.isnan(X) & ~fr["miss"]          # not applicable, or a factor no stock of the market has: stays out, as in the engine's conservative score
    alts["H_missing_at_middle"] = (X, lambda Z: wmean(np.where(np.isnan(Z) & ~na, config.MISSING_NEUTRAL, Z), w))
    return alts


def sector_demean(score, sec):
    sec = np.array([s or "?" for s in sec])
    out = np.full(len(score), np.nan)
    for g in set(sec):
        m = (sec == g) & np.isfinite(score)
        if g != "?" and m.sum() >= 3:
            out[m] = score[m] - score[m].mean()
    return out + np.nanmean(score)


def conc(top, tick, sec, market):
    s = [g or "분류 없음" for t, g in zip(tick, sec) if t in top]
    if not s:
        return None
    vals, cnt = np.unique(s, return_counts=True)
    sh = cnt / cnt.sum()
    return {"max_sector": str(vals[cnt.argmax()]), "max_share": float(sh.max()), "hhi": float((sh ** 2).sum()), "fin_share": float(np.mean([g == FIN[market] for g in s]))}


def knockout(Z, agg, base):
    """each stock's score with one of its factors removed, placed among the others' unchanged scores.
    Returns per (stock, factor) pair: change in points and change in percentile place (0..100)."""
    dpts, dpl, cross = [], [], []
    order = np.sort(base[np.isfinite(base)])
    n = len(order)
    cut = order[int(np.ceil(0.8 * n)) - 1] if n else np.nan
    for j in range(Z.shape[1]):
        if not np.isfinite(Z[:, j]).any():
            continue
        Zk = Z.copy(); Zk[:, j] = np.nan
        new = agg(Zk)
        m = np.isfinite(Z[:, j]) & np.isfinite(base) & np.isfinite(new)
        if not m.any() or np.allclose(new[m], base[m]):
            if m.any():
                dpts += [0.0] * int(m.sum()); dpl += [0.0] * int(m.sum()); cross += [False] * int(m.sum())
            continue
        p0 = np.searchsorted(order, base[m], side="left") / n * 100
        p1 = np.searchsorted(order, new[m], side="left") / n * 100
        dpts += list(new[m] - base[m]); dpl += list(p1 - p0); cross += list((base[m] > cut) != (new[m] > cut))
    dpts, dpl = np.array(dpts), np.array(dpl)
    return {"pairs": len(dpts), "mean_abs_pts": float(np.abs(dpts).mean()), "p95_abs_pts": float(np.percentile(np.abs(dpts), 95)), "share_up": float((dpts > 1e-9).mean()),
            "mean_abs_place": float(np.abs(dpl).mean()), "p95_abs_place": float(np.percentile(np.abs(dpl), 95)), "cross_top_fifth": float(np.mean(cross))}


res = {}
for market, strategy in PROFILES:
    days = sessions(market)
    per = {}
    scores = {}          # alt -> {session: {ticker: score}}
    for d in days:
        fr = frame(market, d, strategy)
        alts = build(fr, market, strategy)
        live = alts["LIVE"][1](alts["LIVE"][0])
        got = {k: agg(Z) for k, (Z, agg) in alts.items()}
        got["B1_sector_demeaned"] = sector_demean(live, fr["sec"])
        uni = conc(set(fr["tick"]), fr["tick"], fr["sec"], market)
        ltop, l70 = top_set(live, fr["tick"]), {t for t, v in zip(fr["tick"], live) if v >= 70}
        for k, sc in got.items():
            top = top_set(sc, fr["tick"])
            s70 = {t for t, v in zip(fr["tick"], sc) if np.isfinite(v) and v >= 70}
            c = conc(top, fr["tick"], fr["sec"], market)
            row = {"n": int(np.isfinite(sc).sum()), "rho_live": spearman(sc, live), "top_fifth_kept": len(top & ltop) / len(ltop), "ge70": len(s70),
                   "ge70_of_live_kept": (len(s70 & l70) / len(l70)) if l70 else None, "ge70_new": len(s70 - l70), "max_sector_share": c["max_share"], "max_sector": c["max_sector"],
                   "hhi": c["hhi"], "fin_share_top": c["fin_share"], "universe_hhi": uni["hhi"], "universe_fin": uni["fin_share"], "mean": float(np.nanmean(sc)), "sd": float(np.nanstd(sc))}
            if k in alts:
                row["knockout"] = knockout(alts[k][0], alts[k][1], sc)
            per.setdefault(k, []).append(row)
            scores.setdefault(k, {})[d] = dict(zip(fr["tick"], sc))
    # day-to-day stability on pairs of consecutive sessions recorded under one formula version
    pairs = [(a, b) for a, b in zip(days, days[1:]) if DATA[(market, a, strategy)]["model_versions"] == DATA[(market, b, strategy)]["model_versions"]]
    out = {}
    for k, rows in per.items():
        agg_ = {}
        for key in ("n", "rho_live", "top_fifth_kept", "ge70", "ge70_of_live_kept", "ge70_new", "max_sector_share", "hhi", "fin_share_top", "universe_hhi", "universe_fin", "mean", "sd"):
            v = [r[key] for r in rows if r.get(key) is not None]
            agg_[key] = float(np.mean(v)) if v else None
        agg_["ge70_min"], agg_["ge70_max"] = min(r["ge70"] for r in rows), max(r["ge70"] for r in rows)
        agg_["max_sector_mode"] = max(set(r["max_sector"] for r in rows), key=[r["max_sector"] for r in rows].count)
        if "knockout" in rows[0]:
            agg_["knockout"] = {kk: float(np.mean([r["knockout"][kk] for r in rows])) for kk in rows[0]["knockout"]}
        st = {"rho": [], "top_kept": [], "med_abs_d": [], "med_abs_d_in_sd": [], "ge70_kept": [], "top10_kept": []}
        for a, b in pairs:
            sa, sb = scores[k][a], scores[k][b]
            common = sorted(t for t in sa if t in sb and np.isfinite(sa[t]) and np.isfinite(sb[t]))
            va, vb = np.array([sa[t] for t in common]), np.array([sb[t] for t in common])
            st["rho"].append(spearman(va, vb)); st["top_kept"].append(len(top_set(va, common) & top_set(vb, common)) / max(1, len(common) // 5))
            st["top10_kept"].append(len(top_set(va, common, 0.1) & top_set(vb, common, 0.1)) / max(1, len(common) // 10))
            st["med_abs_d"].append(float(np.median(np.abs(vb - va)))); st["med_abs_d_in_sd"].append(float(np.median(np.abs(vb - va)) / va.std()))
            a70 = {t for t, v in zip(common, va) if v >= 70}
            if a70:
                st["ge70_kept"].append(len(a70 & {t for t, v in zip(common, vb) if v >= 70}) / len(a70))
        agg_["stability"] = {kk: (float(np.mean(v)) if v else None) for kk, v in st.items()}
        agg_["stability"]["pairs"] = len(pairs)
        out[k] = agg_
    res[f"{market}_{strategy}"] = {"sessions": days, "same_version_pairs": pairs, "alts": out}

json.dump(res, open(HERE / "alternatives.json", "w"), ensure_ascii=False, indent=1, default=str)
f = lambda v, n=2: "  -  " if v is None else f"{v:.{n}f}"
for prof, r in res.items():
    print(f"\n==== {prof}: {len(r['sessions'])} sessions, {len(r['same_version_pairs'])} same-version day pairs; universe HHI {r['alts']['LIVE']['universe_hhi']:.3f}, fin {r['alts']['LIVE']['universe_fin']:.2f}")
    print(f"{'alternative':30s} rho   top5kept ge70(min-max)  live70kept new70  maxsec  HHI   fin   | d2d rho  top5kept top10kept ge70kept med|d| (in sd) | knock: |pts| p95  up%  |place| p95  crossTop5")
    for k, a in r["alts"].items():
        s, ko = a["stability"], a.get("knockout")
        print(f"{k:30s} {f(a['rho_live'],3)} {f(a['top_fifth_kept'])}    {a['ge70']:5.1f} ({a['ge70_min']}-{a['ge70_max']})  {f(a['ge70_of_live_kept'])}    {a['ge70_new']:5.1f}  {f(a['max_sector_share'])}  {f(a['hhi'],3)} {f(a['fin_share_top'])} | "
              f"{f(s['rho'],3)}   {f(s['top_kept'])}     {f(s['top10_kept'])}     {f(s['ge70_kept'])}    {f(s['med_abs_d'])} ({f(s['med_abs_d_in_sd'],3)}) | "
              + (f"{f(ko['mean_abs_pts'])} {f(ko['p95_abs_pts'])} {f(ko['share_up']*100,0)}   {f(ko['mean_abs_place'])} {f(ko['p95_abs_place'])}  {f(ko['cross_top_fifth']*100,1)}%" if ko else ""))
