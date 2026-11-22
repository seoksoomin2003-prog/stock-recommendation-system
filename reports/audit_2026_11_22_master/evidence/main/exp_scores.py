"""Audit 6 (2026-11-22): robustness experiments on the stored QSF scores.  Reads ledger snapshots (scores and factor values) only.
No forward return is computed anywhere in this file."""
import sys, pathlib, json, math, random, collections, statistics
real = pathlib.Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(real))
from utils import runtime_config
runtime_config.load_local_env(real / ".env")
import numpy as np
from terminal.services import Terminal
from terminal import assistant, analyst_extra as ax
from terminal.qsf import config, order_plan as op
t = Terminal(real)
OUT = {}
def rank(a):
    a = np.asarray(a, float); o = a.argsort(); r = np.empty(len(a)); r[o] = np.arange(len(a))
    # average ranks for ties
    vals, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(vals)); np.add.at(sums, inv, r); return sums[inv] / cnt[inv]
def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float); ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10 or np.std(x[ok]) == 0 or np.std(y[ok]) == 0: return float("nan")
    return float(np.corrcoef(rank(x[ok]), rank(y[ok]))[0, 1])
def composite(rows, weights=None, drop=None, impute=None):
    w = c = 0.0
    for r in rows:
        if r.get("scored") is False or not r.get("weight"): continue
        if drop and r["factor"] in drop: continue
        n = r.get("normalized")
        if n is None:
            if impute is None or r.get("status") == "NOT_APPLICABLE": continue
            n = impute[r["factor"]] if isinstance(impute, dict) else impute
        wt = (weights or {}).get(r["factor"], r["weight"])
        w += wt; c += wt * n
    return 100 * c / w if w else None

sessions = {m: sorted({r["session"] for r in t.qsf.ledger._live_rows() if r["market"] == m}) for m in ("US", "KR")}
print("sessions:", {m: (len(v), v[0], v[-1]) for m, v in sessions.items()})
for m in ("US", "KR"):
    last = sessions[m][-1]
    snaps = [s for s in op.session_snaps(t.qsf.ledger, m, last) if s.get("data_date") == last and s["ticker"] not in ("SPY",)]
    sector = {r["ticker"]: ax.SECTOR_KO.get(r.get("sector"), r.get("sector")) for r in t.qsf.screen_rows(m).get("rows") or []}
    for strat in ("SWING", "LONG_TERM"):
        S = [s for s in snaps if s["strategy"] == strat]
        key = f"{m}_{strat}"; res = OUT[key] = {"session": last, "n": len(S), "model": S[0].get("model_version"), "profile": S[0].get("profile")}
        scored = [(r["factor"], r["domain"], r["weight"]) for r in S[0]["factors"] if r.get("scored") is not False and r.get("weight")]
        ref = [(r["factor"], r["domain"], r.get("reference_weight")) for r in S[0]["factors"] if r.get("scored") is False]
        W = sum(w for _f, _d, w in scored)
        res["factors"] = len(scored); res["reference_factors"] = len(ref); res["total_weight"] = W
        dom = collections.defaultdict(float)
        for _f, d, w in scored: dom[d] += w
        res["domain_weight_share"] = {d: round(w / W, 3) for d, w in dom.items()}
        res["largest_factor_weight_share"] = {f: round(w / W, 3) for f, _d, w in sorted(scored, key=lambda x: -x[2])[:4]}
        fids = [f for f, _d, _w in scored]
        M = np.array([[next((r.get("normalized") if r.get("normalized") is not None else np.nan for r in s["factors"] if r["factor"] == f and r.get("scored") is not False), np.nan) for f in fids] for s in S], float)
        score = np.array([s["score"] if s.get("score") is not None else np.nan for s in S], float)
        # E1 inventory
        inv = {}
        for j, (f, d, w) in enumerate(scored):
            col = M[:, j]; ok = np.isfinite(col)
            inv[f] = {"domain": d, "weight_share": round(w / W, 3), "available": round(float(ok.mean()), 3), "mean": round(float(np.nanmean(col)), 3), "sd": round(float(np.nanstd(col)), 3),
                      "at_zero": round(float((col[ok] <= 0.0001).mean()), 3), "at_one": round(float((col[ok] >= 0.9999).mean()), 3), "rho_with_score": round(spearman(col, score), 3)}
        res["inventory"] = inv
        # E2 redundancy
        C = np.full((len(fids), len(fids)), np.nan)
        for a in range(len(fids)):
            for b in range(len(fids)):
                C[a, b] = 1.0 if a == b else spearman(M[:, a], M[:, b])
        pairs = sorted(((abs(C[a, b]), fids[a], fids[b], C[a, b]) for a in range(len(fids)) for b in range(a + 1, len(fids)) if np.isfinite(C[a, b])), reverse=True)
        res["pairs_abs_rho_ge_0.5"] = [(x[1], x[2], round(x[3], 2)) for x in pairs if x[0] >= 0.5]
        Cz = np.nan_to_num(C, nan=0.0); ev = np.linalg.eigvalsh(Cz); ev = ev[ev > 1e-9]
        res["effective_factors_participation"] = round(float(ev.sum() ** 2 / (ev ** 2).sum()), 2); res["eigen_top3_share"] = [round(float(x), 3) for x in sorted(ev / ev.sum(), reverse=True)[:3]]
        # E3 dominance: share of score variance carried by each factor and domain (complete rows only)
        full = np.isfinite(M).all(axis=1) & np.isfinite(score)
        res["complete_rows"] = int(full.sum())
        if full.sum() > 30:
            wv = np.array([w for _f, _d, w in scored], float); contrib = M[full] * wv / wv.sum() * 100
            tot = contrib.sum(axis=1); var = tot.var()
            share = {f: round(float(np.cov(contrib[:, j], tot)[0, 1] / var), 3) for j, f in enumerate(fids)}
            res["variance_share_top"] = dict(sorted(share.items(), key=lambda kv: -kv[1])[:6])
            dshare = collections.defaultdict(float)
            for j, (f, d, _w) in enumerate(scored): dshare[d] += share[f]
            res["variance_share_domain"] = {d: round(v, 3) for d, v in dshare.items()}
        ok = np.isfinite(score); base = score[ok]; rows_ok = [s["factors"] for s, k in zip(S, ok) if k]
        top = lambda a, k=20: set(np.argsort(-a)[:k])      # noqa: E731
        buy = base >= 70
        res["buy_band"] = int(buy.sum()); res["near_70_within_1"] = int((abs(base - 70) <= 1).sum()); res["near_70_within_2"] = int((abs(base - 70) <= 2).sum()); res["near_55_within_1"] = int((abs(base - 55) <= 1).sum())
        res["score_quantiles"] = [round(float(x), 1) for x in np.percentile(base, [5, 25, 50, 75, 95, 100])]
        # E4 ablation
        abl = {}
        for f in fids:
            alt = np.array([composite(r, drop={f}) for r in rows_ok], float)
            abl[f] = {"rho": round(spearman(base, alt), 3), "top20_kept": len(top(base) & top(alt)), "buy_before_after": [int(buy.sum()), int((alt >= 70).sum())], "max_abs_change": round(float(np.nanmax(abs(alt - base))), 1)}
        res["ablation"] = dict(sorted(abl.items(), key=lambda kv: kv[1]["rho"])[:8])
        for d in dom:
            alt = np.array([composite(r, drop={f for f, dd, _w in scored if dd == d}) or np.nan for r in rows_ok], float)
            res.setdefault("ablation_domain", {})[d] = {"rho": round(spearman(base, alt), 3), "top20_kept": len(top(base) & top(np.nan_to_num(alt, nan=-1))), "buy_after": int((alt >= 70).sum())}
        # E5 weight perturbation
        rng = random.Random(20261122)
        for amp in (0.2, 0.5):
            rh, ov, keep = [], [], []
            for _ in range(300):
                wts = {f: w * rng.uniform(1 - amp, 1 + amp) for f, _d, w in scored}
                alt = np.array([composite(r, weights=wts) for r in rows_ok], float)
                rh.append(spearman(base, alt)); ov.append(len(top(base) & top(alt)))
                keep.append(float(((alt >= 70) & buy).sum() / buy.sum()) if buy.sum() else float("nan"))
            res[f"weight_perturb_{int(amp*100)}pct"] = {"rho_p5_median": [round(float(np.percentile(rh, 5)), 3), round(float(np.median(rh)), 3)], "top20_kept_p5_median": [int(np.percentile(ov, 5)), int(np.median(ov))],
                                                       "buy_band_kept_p5_median": [round(float(np.nanpercentile(keep, 5)), 2), round(float(np.nanmedian(keep)), 2)] if buy.sum() else None}
        # E6 normalisation sensitivity: replace each factor's 0..1 value by its cross-sectional percentile rank
        P = np.full_like(M, np.nan)
        for j in range(M.shape[1]):
            okj = np.isfinite(M[:, j])
            if okj.sum() > 1: P[okj, j] = rank(M[okj, j]) / (okj.sum() - 1)
        wv = np.array([w for _f, _d, w in scored], float)
        alt = np.array([100 * np.nansum(P[i] * wv) / wv[np.isfinite(P[i])].sum() if np.isfinite(P[i]).any() else np.nan for i in range(len(S))], float)
        res["rank_normalised_rho"] = round(spearman(score, alt), 3); res["rank_normalised_top20_kept"] = len(set(np.argsort(-np.nan_to_num(score, nan=-1))[:20]) & set(np.argsort(-np.nan_to_num(alt, nan=-1))[:20]))
        # E7 missing data
        nmiss = np.array([sum(1 for r in s["factors"] if r.get("scored") is not False and r.get("weight") and r.get("normalized") is None and r.get("status") != "NOT_APPLICABLE") for s in S])
        nna = np.array([sum(1 for r in s["factors"] if r.get("scored") is not False and r.get("weight") and r.get("status") == "NOT_APPLICABLE") for s in S])
        res["missing"] = {"stocks_with_missing": int((nmiss > 0).sum()), "stocks_with_not_applicable": int((nna > 0).sum()), "rho_missing_count_vs_score": round(spearman(nmiss + nna, score), 3),
                          "mean_score_by_gaps": {str(k): round(float(np.nanmean(score[(nmiss + nna) == k])), 1) for k in sorted(set(nmiss + nna)) if ((nmiss + nna) == k).sum() >= 5}}
        med = {f: float(np.nanmedian(M[:, j])) for j, f in enumerate(fids)}
        gap = [(s, sc) for s, sc, g in zip(S, score, nmiss + nna) if g > 0 and np.isfinite(sc)]
        if gap:
            d_neutral = np.array([composite(s["factors"], impute=0.5) - sc for s, sc in gap]); d_med = np.array([composite(s["factors"], impute=med) - sc for s, sc in gap])
            sm = np.array([sum(1 for r in s["factors"] if r.get("scored") is not False and r.get("weight") and r.get("normalized") is None and r.get("status") != "NOT_APPLICABLE") for s, _ in gap])
            res["missing"]["truly_missing_only"] = {"n": int((sm > 0).sum())}
            dm = np.array([composite([r for r in s["factors"]], impute=med) for s, sc in gap])
            res["missing"]["if_gaps_were_median"] = {"n": len(gap), "mean_change": round(float(d_med.mean()), 2), "p5_p95": [round(float(np.percentile(d_med, 5)), 1), round(float(np.percentile(d_med, 95)), 1)],
                                                     "buy_now": int(sum(1 for _s, sc in gap if sc >= 70)), "buy_if_median": int((np.array([sc for _s, sc in gap]) + d_med >= 70).sum())}
            res["missing"]["if_gaps_were_neutral_0.5"] = {"mean_change": round(float(d_neutral.mean()), 2), "buy_if_neutral": int((np.array([sc for _s, sc in gap]) + d_neutral >= 70).sum())}
        # counterfactual: a stock's worst factor goes missing
        infl = []
        for r, b in zip(rows_ok, base):
            live = [x for x in r if x.get("scored") is not False and x.get("weight") and x.get("normalized") is not None]
            worst = min(live, key=lambda x: (x["normalized"] - b / 100) * x["weight"])
            infl.append(composite(r, drop={worst["factor"]}) - b)
        infl = np.array(infl); res["missing"]["if_worst_factor_went_missing"] = {"median_gain": round(float(np.median(infl)), 2), "p95_gain": round(float(np.percentile(infl, 95)), 2), "max_gain": round(float(infl.max()), 2),
                                                                                "new_buy_band": int(((base + infl >= 70) & ~buy).sum())}
        cov = np.array([s.get("coverage") or np.nan for s in S], float); conf = collections.Counter(s.get("confidence") for s in S)
        res["coverage"] = {"min": round(float(np.nanmin(cov)), 3), "p5": round(float(np.nanpercentile(cov, 5)), 3), "confidence": dict(conf),
                           "buy_band_min_coverage": round(float(np.nanmin(cov[np.nan_to_num(score, nan=0) >= 70])), 3) if (np.nan_to_num(score, nan=0) >= 70).any() else None,
                           "buy_band_confidence": dict(collections.Counter(s.get("confidence") for s in S if (s.get("score") or 0) >= 70))}
        res["actions"] = dict(collections.Counter(s.get("action") for s in S)); res["actionability"] = dict(collections.Counter(s.get("actionability") for s in S))
        res["entry_status_in_buy_band"] = dict(collections.Counter(s.get("entry_status") for s in S if (s.get("score") or 0) >= 70))
        res["gates"] = dict(collections.Counter(g["code"] for s in S for g in (s.get("gates") or [])))
        # E8 sector and size
        sec = [sector.get(s["ticker"]) for s in S]
        by = collections.defaultdict(list)
        for x, sc in zip(sec, score):
            if x and np.isfinite(sc): by[x].append(sc)
        allmean = float(np.nanmean(score)); k5 = max(1, len(S) // 5); topq = set(np.argsort(-np.nan_to_num(score, nan=-1))[:k5])
        res["sector"] = {x: {"n": len(v), "mean_minus_all": round(float(np.mean(v)) - allmean, 1), "share_universe": round(len(v) / len(S), 3),
                             "share_top_quintile": round(sum(1 for i in topq if sec[i] == x) / k5, 3), "share_buy_band": round(sum(1 for i, sc in enumerate(score) if sec[i] == x and sc >= 70) / max(1, int(buy.sum())), 3)}
                         for x, v in sorted(by.items(), key=lambda kv: -np.mean(kv[1])) if len(v) >= 5}
        groups = [np.array(v) for v in by.values() if len(v) >= 5]; grand = np.concatenate(groups)
        res["sector_eta_squared"] = round(float(sum(len(g) * (g.mean() - grand.mean()) ** 2 for g in groups) / ((grand - grand.mean()) ** 2).sum()), 3)
        cap = np.array([(t.qsf.stored_info(s["ticker"], m) or {}).get("marketCap") or np.nan for s in S], float)
        res["rho_score_vs_market_cap"] = round(spearman(score, np.log(cap)), 3); res["cap_known"] = int(np.isfinite(cap).sum())
    # E9 stability across sessions of the same model version
    for strat in ("SWING", "LONG_TERM"):
        seq = []
        for d in sessions[m]:
            ss = [s for s in op.session_snaps(t.qsf.ledger, m, d) if s.get("data_date") == d and s["strategy"] == strat and s.get("score") is not None]
            if ss: seq.append((d, ss[0].get("model_version"), {s["ticker"]: s["score"] for s in ss}))
        out = []
        for (d0, v0, a), (d1, v1, b) in zip(seq, seq[1:]):
            common = sorted(set(a) & set(b)); x = np.array([a[k] for k in common]); y = np.array([b[k] for k in common])
            ta, tb = set(sorted(a, key=a.get, reverse=True)[:20]), set(sorted(b, key=b.get, reverse=True)[:20])
            ba, bb = {k for k in a if a[k] >= 70}, {k for k in b if b[k] >= 70}
            out.append({"from": d0, "to": d1, "same_version": v0 == v1, "rho": round(spearman(x, y), 3), "top20_kept": len(ta & tb), "buy": [len(ba), len(bb)], "buy_kept": len(ba & bb), "mean_abs_change": round(float(np.mean(abs(x - y))), 2)})
        OUT[f"{m}_{strat}"]["day_to_day"] = out
        OUT[f"{m}_{strat}"]["versions"] = [(d, v) for d, v, _ in seq]
json.dump(OUT, open(pathlib.Path(__file__).parent / "exp_scores.json", "w"), ensure_ascii=False, indent=1, default=str)
for k, r in OUT.items():
    print("\n=====", k, r["session"], "n", r["n"], r["model"], r["profile"], "| factors", r["factors"], "ref", r["reference_factors"])
    print(" domain weight:", r["domain_weight_share"], "| largest:", r["largest_factor_weight_share"])
    print(" effective factors:", r["effective_factors_participation"], "eig top3:", r["eigen_top3_share"], "| pairs>=0.5:", r["pairs_abs_rho_ge_0.5"])
    print(" variance share top:", r.get("variance_share_top"), "| by domain:", r.get("variance_share_domain"), "complete rows", r["complete_rows"])
    print(" score q[5,25,50,75,95,max]:", r["score_quantiles"], "| buy", r["buy_band"], "near70±1", r["near_70_within_1"], "±2", r["near_70_within_2"], "near55±1", r["near_55_within_1"])
    print(" ablation (most changing):", {f: (v["rho"], v["top20_kept"], v["buy_before_after"]) for f, v in list(r["ablation"].items())[:5]})
    print(" ablation by domain:", r["ablation_domain"])
    print(" weights ±20%:", r["weight_perturb_20pct"], "| ±50%:", r["weight_perturb_50pct"])
    print(" rank-normalised: rho", r["rank_normalised_rho"], "top20 kept", r["rank_normalised_top20_kept"])
    print(" missing:", r["missing"])
    print(" coverage:", r["coverage"]); print(" actions:", r["actions"], r["actionability"], "| entry in buy band:", r["entry_status_in_buy_band"], "| gates:", r["gates"])
    print(" sector eta²:", r["sector_eta_squared"], "| rho(score, cap):", r["rho_score_vs_market_cap"], "| sectors:", {x: (v["n"], v["mean_minus_all"], v["share_universe"], v["share_top_quintile"]) for x, v in r["sector"].items()})
    dd = [x for x in r["day_to_day"] if x["same_version"]]
    print(" day-to-day same version: n", len(dd), "rho median", round(float(np.median([x["rho"] for x in dd])), 3) if dd else None, "top20 kept median", int(np.median([x["top20_kept"] for x in dd])) if dd else None,
          "buy kept/before:", [(x["buy_kept"], x["buy"][0]) for x in dd][-4:], "| version changes:", sum(1 for x in r["day_to_day"] if not x["same_version"]))
    print(" inventory saturation (at_zero>=0.4 or at_one>=0.4 or available<0.8):", {f: (v["available"], v["at_zero"], v["at_one"]) for f, v in r["inventory"].items() if v["at_zero"] >= 0.4 or v["at_one"] >= 0.4 or v["available"] < 0.8})
