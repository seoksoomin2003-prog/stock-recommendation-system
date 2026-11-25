"""Experiment 6: missing-data stress on the latest recorded day.  Rules reproduced from engine.py (coverage 70%, domain minimums,
conservative score with missing factors at 0.5, buy band taken back when the conservative score falls under it).  No return involved."""
import collections, itertools
from common import *
SEED = 20261125
res = {}


def sufficiency(N, A, w, dom, strat):
    """coverage and the sufficiency rule for every stock (all present factors read as REAL: STALE is not simulated)."""
    have = ~np.isnan(N)
    app = (A * w).sum(axis=1)
    cov = np.where(app > 0, (have * w).sum(axis=1) / np.where(app > 0, app, 1), 0)
    ok = cov >= config.MIN_TOTAL_COVERAGE
    for d, m in config.MIN_DOMAIN_COVERAGE[strat].items():
        cols = np.array([dd == d for dd in dom])
        if not (w[cols] > 0).any():
            continue
        a = (A[:, cols] * w[cols]).sum(axis=1); h = (have[:, cols] * w[cols]).sum(axis=1)
        dc = np.where(a > 0, h / np.where(a > 0, a, 1), 0)
        ok &= dc >= m
    return cov, ok


def conservative(N, A, w, never):
    have = ~np.isnan(N)
    miss = (~have) & A & ~never[None, :]
    tc = np.nansum(N * w, axis=1); tw = (have * w).sum(axis=1); mw = (miss * w).sum(axis=1)
    return np.where(tw + mw > 0, 100 * (tc + 0.5 * mw) / np.where(tw + mw > 0, tw + mw, 1), np.nan)


for market in ("US", "KR"):
    session = sessions(market)[-1][0]
    for strat in ("SWING", "LONG_TERM"):
        snaps = load(market, session)[strat]
        tick, fids, w, dom, N, A = matrix(snaps)
        never = np.array([f in config.NEVER_AVAILABLE.get((market, strat), ()) for f in fids])
        S = composite(N, w)
        key = f"{market}_{strat}"; out = {"session": session, "n": len(tick)}
        # ---- (a) the recorded day as it is
        c = collections.Counter()
        partial_ge70 = []
        for t in tick:
            s = snaps[t]
            if s["score"] is None:
                continue
            rows = [f for f in s["factors"] if f.get("scored") is not False]
            miss = [f["factor"] for f in rows if f["status"] == "MISSING" and f["factor"] not in config.NEVER_AVAILABLE.get((market, strat), ())]
            # a factor built from part of its figures: a None inside its raw dict (the ledger does not keep the inputs count)
            part = [f["factor"] for f in rows if f["status"] in QUAL and isinstance(f.get("raw"), dict) and any(v is None for k, v in f["raw"].items() if k not in ("insider", "benchmark", "percentile_5y"))]
            ge = s["score"] >= 70
            c["score_ge70"] += ge
            c["ge70_insufficient_data"] += ge and s["actionability"] == "INSUFFICIENT_DATA"
            c["ge70_with_missing_factor"] += ge and bool(miss)
            c["ge70_band_held_back"] += ge and bool(s.get("band_held_back"))
            c["ge70_missing_but_band_kept"] += ge and bool(miss) and not s.get("band_held_back") and s["actionability"] != "INSUFFICIENT_DATA"
            c["ge70_with_partial_factor"] += ge and bool(part)
            c["ge70_input_coverage_lt_0.9"] += ge and (s.get("input_coverage") or 0) < 0.9
            c["ge70_confidence_" + str(s.get("confidence"))] += ge
            c["ge70_buy_band_shown"] += ge and s["band"] in engine.BUY_CODES and s["actionability"] != "INSUFFICIENT_DATA"
            c["any_missing"] += bool(miss); c["any_partial"] += bool(part)
            if ge and part:
                partial_ge70.append((t, round(s["score"], 1), part, s.get("input_coverage")))
            if ge and miss and s.get("conservative_score") is not None:
                c["ge70_missing_conservative_gap_sum_x100"] += int(round(100 * (s["score"] - s["conservative_score"])))
        out["recorded"] = dict(c); out["ge70_partial_examples"] = partial_ge70[:8]
        print(f"\n=== {key} {session}: recorded day:", dict(c))
        # which sub-figures are empty, per factor (share of stocks with the factor)
        sub = collections.defaultdict(collections.Counter)
        for t in tick:
            for f in snaps[t]["factors"]:
                if f.get("scored") is not False and f["status"] in QUAL and isinstance(f.get("raw"), dict):
                    for k, v in f["raw"].items():
                        sub[f["factor"]][k + ":none"] += v is None; sub[f["factor"]][k + ":n"] += 1
        empties = {f"{fid}.{k[:-5]}": round(v / c2[k[:-5] + ":n"], 3) for fid, c2 in sub.items() for k, v in c2.items() if k.endswith(":none") and v and v / c2[k[:-5] + ":n"] >= 0.05}
        out["sub_figures_empty_share(>=5%)"] = empties
        print("   sub-figures empty in >=5% of stocks:", empties)

        # ---- (b) remove factors from stocks that have every factor
        full = (~np.isnan(N) | ~A | never[None, :]).all(axis=1) & ~np.isnan(S)
        Nf, Af, Sf = N[full], A[full], S[full]
        rng = np.random.default_rng(SEED)
        out["full_data_stocks"] = int(full.sum())
        rand = {}
        for k in (1, 2, 3):
            ups, tops, cross, cross_kept, insuff = [], [], 0, 0, 0
            for _ in range(200):
                M = Nf.copy()
                for i in range(len(M)):
                    cand = np.where(~np.isnan(M[i]))[0]
                    M[i, rng.choice(cand, size=min(k, len(cand)), replace=False)] = np.nan
                S2 = composite(M, w); cov, ok = sufficiency(M, Af, w, dom, strat); cons = conservative(M, Af, w, never)
                d = S2 - Sf
                ups.append(float(np.percentile(d, 95))); tops.append(float(d.max()))
                up = (Sf < 70) & (S2 >= 70) & ok
                cross += int(up.sum()); cross_kept += int((up & (cons >= 70)).sum()); insuff += int((~ok).sum())
            rand[k] = {"p95_rise_mean": float(np.mean(ups)), "max_rise": float(max(tops)), "new_ge70_per_draw": cross / 200, "new_ge70_surviving_conservative_per_draw": cross_kept / 200, "insufficient_per_draw": insuff / 200}
            print(f"   random removal of {k} factor(s) ({int(full.sum())} full-data stocks, 200 draws): 95th pct rise {rand[k]['p95_rise_mean']:+.1f}, max rise {rand[k]['max_rise']:+.1f}; newly >=70 per draw {rand[k]['new_ge70_per_draw']:.1f}, of which keep the band after the conservative check {rand[k]['new_ge70_surviving_conservative_per_draw']:.1f}; judged insufficient {rand[k]['insufficient_per_draw']:.1f}")
        out["random_removal"] = rand
        # ---- (c) worst case: the stock's lowest factors go missing, as far as the sufficiency rule allows
        rises, crossed, kept = [], [], []
        for i in range(len(Nf)):
            M = Nf[i:i + 1].copy(); best = Sf[i]; order = np.argsort(np.where(np.isnan(M[0]), np.inf, M[0]))
            for j in order:
                if np.isnan(M[0, j]) or M[0, j] * 100 >= best:
                    break
                T = M.copy(); T[0, j] = np.nan
                _, ok = sufficiency(T, Af[i:i + 1], w, dom, strat)
                if not ok[0]:
                    continue
                M = T; best = composite(M, w)[0]
            cons = conservative(M, Af[i:i + 1], w, never)[0]
            rises.append(best - Sf[i]); crossed.append(Sf[i] < 70 <= best); kept.append(Sf[i] < 70 <= best and cons >= 70)
        rises = np.array(rises)
        out["worst_case"] = {"median_rise": float(np.median(rises)), "p95_rise": float(np.percentile(rises, 95)), "max_rise": float(rises.max()), "newly_ge70": int(sum(crossed)), "newly_ge70_band_kept_after_conservative": int(sum(kept)),
                             "ge70_before": int((Sf >= 70).sum())}
        print(f"   worst case (lowest factors missing, still 'sufficient'): rise median {np.median(rises):+.1f}, 95th {np.percentile(rises, 95):+.1f}, max {rises.max():+.1f}; >=70 before {int((Sf >= 70).sum())}, newly >=70: {sum(crossed)}, band still given after the conservative check: {sum(kept)}")
        # ---- (d) one named factor missing for everybody (a source outage for one factor) and whole domains
        outage = []
        for name, cols in [(fid, [j]) for j, fid in enumerate(fids)] + [(d, [j for j, dd in enumerate(dom) if dd == d]) for d in sorted(set(dom))]:
            M = Nf.copy(); M[:, cols] = np.nan
            if np.isnan(M).all():
                continue
            S2 = composite(M, w); cov, ok = sufficiency(M, Af, w, dom, strat); cons = conservative(M, Af, w, never)
            up = (Sf < 70) & (S2 >= 70)
            outage.append({"missing": name, "mean_change": float(np.nanmean(S2 - Sf)), "max_rise": float(np.nanmax(S2 - Sf)), "still_sufficient_share": float(ok.mean()), "ge70_after": int(((S2 >= 70) & ok).sum()),
                           "newly_ge70": int((up & ok).sum()), "newly_ge70_band_kept": int((up & ok & (cons >= 70)).sum()), "rho": spearman(Sf, S2)})
        out["outage"] = outage
        for r in sorted(outage, key=lambda r: -r["newly_ge70_band_kept"])[:5]:
            print(f"   outage of {r['missing']:22s}: mean {r['mean_change']:+.1f}, max rise {r['max_rise']:+.1f}, still judged {r['still_sufficient_share']*100:.0f}%, newly >=70 {r['newly_ge70']}, band kept after conservative check {r['newly_ge70_band_kept']}")
        res[key] = out
dump("s06_missing.json", res)
