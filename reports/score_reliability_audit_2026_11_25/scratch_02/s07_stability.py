"""Experiment 7: stability of scores and ranks from one recorded session to the next (ledger, same model_version only for the
headline), the 70/67 lines, and month-to-month stability in the stored historical scores.  Scores only; no price, no return."""
import collections, gzip, json
from common import *
res = {}
for market in ("US", "KR"):
    ss = sessions(market)
    for strat in ("SWING", "LONG_TERM"):
        key = f"{market}_{strat}"; pairs = []
        for (s0, v0), (s1, v1) in zip(ss, ss[1:]):
            a, b = load(market, s0)[strat], load(market, s1)[strat]
            common = sorted(t for t in set(a) & set(b) if a[t]["score"] is not None and b[t]["score"] is not None)
            x = np.array([a[t]["score"] for t in common]); y = np.array([b[t]["score"] for t in common])
            n = len(common); k5 = n // 5
            g0, g1 = set(np.where(x >= 70)[0].tolist()), set(np.where(y >= 70)[0].tolist())
            left = g0 - g1
            pairs.append({"from": s0, "to": s1, "same_version": v0 == v1, "version": v1 if v0 == v1 else f"{v0}->{v1}", "n": n, "rho": spearman(x, y), "mean_abs_change": float(np.abs(y - x).mean()),
                          "p95_abs_change": float(np.percentile(np.abs(y - x), 95)), "max_abs_change": float(np.abs(y - x).max()), "mean_change": float((y - x).mean()),
                          "top20_turnover": 1 - len(top_set(x, 20) & top_set(y, 20)) / 20, "top_fifth_turnover": 1 - len(top_set(x, k5) & top_set(y, k5)) / k5,
                          "ge70_before": len(g0), "ge70_after": len(g1), "ge70_left": len(left), "ge70_entered": len(g1 - g0),
                          "ge70_left_but_still_ge67": int(sum(1 for i in left if y[i] >= 67)), "ge70_turnover": (len(left) / len(g0)) if g0 else None,
                          "band_changed": int(sum(1 for t in common if a[t]["band"] != b[t]["band"]))})
        res[key] = {"pairs": pairs}
        same = [p for p in pairs if p["same_version"]]; diff = [p for p in pairs if not p["same_version"]]
        def avg(ps, k):
            v = [p[k] for p in ps if p[k] is not None]
            return float(np.mean(v)) if v else None
        res[key]["same_version_summary"] = {k: avg(same, k) for k in ("rho", "mean_abs_change", "p95_abs_change", "top20_turnover", "top_fifth_turnover", "ge70_turnover")} | {"pairs": len(same),
                                            "ge70_left_total": sum(p["ge70_left"] for p in same), "of_which_still_ge67": sum(p["ge70_left_but_still_ge67"] for p in same), "ge70_entered_total": sum(p["ge70_entered"] for p in same)}
        res[key]["version_change_summary"] = {k: avg(diff, k) for k in ("rho", "mean_abs_change", "p95_abs_change", "top20_turnover", "top_fifth_turnover", "ge70_turnover")} | {"pairs": len(diff)}
        print(f"\n=== {key}: same-version day pairs {len(same)}, version-change pairs {len(diff)}")
        for p in pairs:
            t70 = "-" if p["ge70_turnover"] is None else f"{p['ge70_turnover']*100:.0f}%"
            print(f"   {p['from']}->{p['to']} {'same' if p['same_version'] else 'CHG '} {p['version']:22s} rho {p['rho']:.3f} |d| mean {p['mean_abs_change']:.2f} p95 {p['p95_abs_change']:.2f} max {p['max_abs_change']:.1f} shift {p['mean_change']:+.2f} top20 turn {p['top20_turnover']*100:3.0f}% top5th {p['top_fifth_turnover']*100:3.0f}% >=70 {p['ge70_before']}->{p['ge70_after']} left {p['ge70_left']} (>=67: {p['ge70_left_but_still_ge67']}) in {p['ge70_entered']} turn {t70}")
        print("   same-version mean:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res[key]["same_version_summary"].items()})
        print("   version-change mean:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res[key]["version_change_summary"].items()})
        # ---- the longest same-version run: crossings of 70 with and without the buffer
        runs, cur = [], [ss[0]]
        for a, b in zip(ss, ss[1:]):
            if a[1] == b[1]:
                cur.append(b)
            else:
                runs.append(cur); cur = [b]
        runs.append(cur)
        run = max(runs, key=len)
        days = [s for s, _ in run]
        tick = sorted(set.intersection(*[set(load(market, s)[strat]) for s in days]))
        M = np.array([[load(market, s)[strat][t]["score"] if load(market, s)[strat][t]["score"] is not None else np.nan for s in days] for t in tick])
        plain = M >= 70
        flips_plain = (plain[:, 1:] != plain[:, :-1]).sum(axis=1)
        buf = np.zeros_like(plain); buf[:, 0] = plain[:, 0]
        for d in range(1, M.shape[1]):
            buf[:, d] = (M[:, d] >= 70) | (buf[:, d - 1] & (M[:, d] >= 67))
        flips_buf = (buf[:, 1:] != buf[:, :-1]).sum(axis=1)
        rng_ = np.nanmax(M, axis=1) - np.nanmin(M, axis=1)
        res[key]["longest_run"] = {"version": run[0][1], "days": days, "stocks": len(tick), "ever_ge70": int(plain.any(axis=1).sum()), "always_ge70": int(plain.all(axis=1).sum()),
                                   "label_changes_plain_70": int(flips_plain.sum()), "stocks_flipping_twice_or_more_plain": int((flips_plain >= 2).sum()),
                                   "label_changes_with_67_buffer": int(flips_buf.sum()), "stocks_flipping_twice_or_more_buffer": int((flips_buf >= 2).sum()),
                                   "score_range_over_run_median": float(np.nanmedian(rng_)), "score_range_over_run_p95": float(np.nanpercentile(rng_, 95)),
                                   "day_sd_of_a_stock_median": float(np.nanmedian(np.nanstd(M, axis=1)))}
        print("   longest same-version run:", res[key]["longest_run"])

# ---- stored historical scores: month-to-month (scores only)
for label, path, market in (("US", "data/qsf/research/scores_current_us.json.gz", "US"), ("KR", "research_data/krx_live/scores_current_cap.json.gz", "KR")):
    d = json.load(gzip.open(path))
    by = collections.defaultdict(dict)
    for r in d["records"]:
        by[r["i"]][r["t"]] = r
    idx = sorted(by)
    gaps = collections.Counter(b - a for a, b in zip(idx, idx[1:]))
    for strat in ("SWING", "LONG_TERM"):
        rho, t5, t70, share, n70, mean = [], [], [], [], [], []
        for a, b in zip(idx, idx[1:]):
            common = sorted(t for t in set(by[a]) & set(by[b]) if by[a][t][strat] is not None and by[b][t][strat] is not None)
            if len(common) < 50:
                continue
            x = np.array([by[a][t][strat] for t in common]); y = np.array([by[b][t][strat] for t in common]); k5 = len(common) // 5
            rho.append(spearman(x, y)); t5.append(1 - len(top_set(x, k5) & top_set(y, k5)) / k5)
            g0, g1 = set(np.where(x >= 70)[0].tolist()), set(np.where(y >= 70)[0].tolist())
            if g0:
                t70.append(len(g0 - g1) / len(g0))
        for i in idx:
            v = np.array([r[strat] for r in by[i].values() if r[strat] is not None])
            if len(v):
                share.append(float((v >= 70).mean())); n70.append(int((v >= 70).sum())); mean.append(float(v.mean()))
        key = f"{label}_{strat}"
        res[key]["history"] = {"file": path, "model_version": d.get("model_version"), "dates": len(idx), "first": d["dates"][idx[0]], "last": d["dates"][idx[-1]], "gap_sessions": dict(gaps.most_common(3)),
                               "rho_mean": float(np.mean(rho)), "rho_min": float(np.min(rho)), "top_fifth_turnover_mean": float(np.mean(t5)), "ge70_turnover_mean": float(np.mean(t70)) if t70 else None,
                               "share_ge70_mean": float(np.mean(share)), "share_ge70_min": float(np.min(share)), "share_ge70_max": float(np.max(share)), "share_ge70_p10": float(np.percentile(share, 10)), "share_ge70_p90": float(np.percentile(share, 90)),
                               "dates_with_zero_ge70": int(sum(1 for x in n70 if x == 0)), "mean_score_min": float(np.min(mean)), "mean_score_max": float(np.max(mean)), "mean_score_mean": float(np.mean(mean))}
        print(f"\n=== history {key}:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res[key]["history"].items()})
dump("s07_stability.json", res)
