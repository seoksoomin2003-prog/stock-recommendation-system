"""Experiment 4: leave one factor / one domain out (ranking only), and Experiment 5: fixed anchors replaced by cross-sectional
percentile (and z-score) per factor.  Sector make-up of the top fifth.  No return involved."""
import collections
from common import *
SEC = {"US": us_sectors(), "KR": kr_sectors()}
print("sector map sizes:", {k: len(v) for k, v in SEC.items()})


def sector_shares(tick, idx, market):
    c = collections.Counter(SEC[market].get(tick[i], "분류 없음") for i in idx)
    n = sum(c.values()) or 1
    return {k: v / n for k, v in c.items()}


def shift(a, b):
    """total variation distance between two sector mixes (0 = same, 1 = disjoint)."""
    return 0.5 * sum(abs(a.get(k, 0) - b.get(k, 0)) for k in set(a) | set(b))


def hhi(a):
    return sum(v * v for v in a.values())


def pct_rank(col):
    out = np.full(len(col), np.nan); ok = ~np.isnan(col)
    if ok.sum():
        out[ok] = (rank(col[ok]) - 0.5) / ok.sum()
    return out


res = {}
for market in ("US", "KR"):
    session = sessions(market)[-1][0]
    for strat in ("SWING", "LONG_TERM"):
        snaps = load(market, session)[strat]
        tick, fids, w, dom, N, A = matrix(snaps)
        S = composite(N, w); ok = ~np.isnan(S); N, S = N[ok], S[ok]; tick = [t for t, k in zip(tick, ok) if k]
        n = len(S); k5 = n // 5
        top5 = top_set(S, k5); set70 = set(np.where(S >= 70)[0].tolist()); top20 = top_set(S, 20)
        base_mix = sector_shares(tick, top5, market); all_mix = sector_shares(tick, range(n), market)
        key = f"{market}_{strat}"
        out = {"session": session, "n": n, "ge70": len(set70), "top_fifth_sector_mix": base_mix, "scan_sector_mix": all_mix, "top_fifth_vs_scan_shift": shift(base_mix, all_mix),
               "top_fifth_hhi": hhi(base_mix), "scan_hhi": hhi(all_mix), "ablation": [], "normalisation": {}}
        print(f"\n=== {key} {session} n={n} >=70: {len(set70)}; top fifth {k5}; sector mix shift top-fifth vs scan {out['top_fifth_vs_scan_shift']:.2f}; HHI top {hhi(base_mix):.3f} scan {hhi(all_mix):.3f}")
        print("   top fifth largest sectors:", sorted(((round(v, 2), k) for k, v in base_mix.items()), reverse=True)[:4], "| scan:", sorted(((round(v, 2), k) for k, v in all_mix.items()), reverse=True)[:4])

        def compare(S2, name, kind):
            t5 = top_set(S2, k5); s70 = set(np.where(S2 >= 70)[0].tolist())
            r = {"left_out": name, "kind": kind, "rho": spearman(S, S2), "top_fifth_overlap": len(top5 & t5) / k5, "top20_overlap": len(top20 & top_set(S2, 20)) / 20, "ge70_count": len(s70),
                 "ge70_overlap_of_live": (len(set70 & s70) / len(set70)) if set70 else None, "sector_shift_top_fifth": shift(base_mix, sector_shares(tick, t5, market)),
                 "mean_score_change": float(np.nanmean(S2 - S)), "max_abs_change": float(np.nanmax(np.abs(S2 - S)))}
            return r
        for j, fid in enumerate(fids):
            w2 = w.copy(); w2[j] = 0
            out["ablation"].append(compare(composite(N, w2), fid, "factor"))
        for d in sorted(set(dom)):
            w2 = np.array([0 if dd == d else x for dd, x in zip(dom, w)])
            out["ablation"].append(compare(composite(N, w2), d, "domain"))
        for r in sorted(out["ablation"], key=lambda r: r["rho"])[:8]:
            o70 = "-" if r["ge70_overlap_of_live"] is None else f"{r['ge70_overlap_of_live']*100:.0f}%"
            print(f"   -{r['left_out']:24s} [{r['kind'][:3]}] rho {r['rho']:.3f} top5th overlap {r['top_fifth_overlap']*100:3.0f}% top20 {r['top20_overlap']*100:3.0f}% >=70 {r['ge70_count']:3d} (keeps {o70} of live) sector shift {r['sector_shift_top_fifth']:.2f} mean chg {r['mean_score_change']:+.1f}")
        least = sorted((r for r in out["ablation"] if r["kind"] == "factor"), key=lambda r: -r["rho"])[:5]
        print("   factors whose removal changes nothing (rho):", [(r["left_out"], round(r["rho"], 4), f"{r['mean_score_change']:+.1f}") for r in least])
        # --- normalisation variants
        P = np.column_stack([pct_rank(N[:, j]) for j in range(N.shape[1])])
        Sp = composite(P, w)
        mu, sd = np.nanmean(N, axis=0), np.nanstd(N, axis=0)
        Z = np.where(sd > 0, (N - mu) / np.where(sd > 0, sd, 1), 0.0); Z[np.isnan(N)] = np.nan
        Sz = composite(Z, w) / 100
        for name, S2 in (("percentile", Sp), ("zscore", Sz)):
            t5 = top_set(S2, k5); mix = sector_shares(tick, t5, market)
            r = {"rho": spearman(S, S2), "top_fifth_overlap": len(top5 & t5) / k5, "top20_overlap": len(top20 & top_set(S2, 20)) / 20,
                 "sector_shift_top_fifth_vs_live": shift(base_mix, mix), "top_fifth_vs_scan_shift": shift(mix, all_mix), "top_fifth_hhi": hhi(mix), "max_sector_share": max(mix.values()), "max_sector": max(mix, key=mix.get)}
            if name == "percentile":
                r.update({"ge70_count": int((S2 >= 70).sum()), "mean": float(np.nanmean(S2)), "sd": float(np.nanstd(S2)), "max": float(np.nanmax(S2)),
                          "ge70_overlap_of_live": (len(set70 & set(np.where(S2 >= 70)[0].tolist())) / len(set70)) if set70 else None,
                          "same_count_as_live_cut": float(np.sort(S2)[::-1][len(set70) - 1]) if set70 else None})
            out["normalisation"][name] = r
        out["normalisation"]["live"] = {"mean": float(S.mean()), "sd": float(S.std()), "max": float(S.max()), "ge70_count": len(set70), "max_sector_share": max(base_mix.values()), "max_sector": max(base_mix, key=base_mix.get),
                                        "share_ge70": len(set70) / n, "percentile_of_70": float((S < 70).mean())}
        print("   live:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out["normalisation"]["live"].items()})
        for name in ("percentile", "zscore"):
            print(f"   {name}:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out["normalisation"][name].items()})
        # factor level: how far each factor's mean sits from the middle (an anchor that is off-centre moves the level of every score)
        out["anchor_centre"] = {fid: {"mean": float(np.nanmean(N[:, j])), "points_vs_middle": float(100 * w[j] * (np.nanmean(N[:, j]) - 0.5) / w.sum())} for j, fid in enumerate(fids) if not np.isnan(N[:, j]).all()}
        lvl = sorted(out["anchor_centre"].items(), key=lambda kv: kv[1]["points_vs_middle"])
        print("   level shift by off-centre anchors (points of the 0-100 score):", [(k, round(v["points_vs_middle"], 1)) for k, v in lvl[:3]], "...", [(k, round(v["points_vs_middle"], 1)) for k, v in lvl[-3:]], "sum", round(sum(v["points_vs_middle"] for _, v in lvl), 1))
        res[key] = out
dump("s04_ablation_normalisation.json", res)
