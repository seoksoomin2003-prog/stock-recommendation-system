"""Experiment 3: weight sensitivity.  Every weight is multiplied by (1 + u), u ~ Uniform(-x, +x), 1,000 seeded draws per level;
plus the harder case of every weight moved by exactly +x or -x (random signs).  Rankings only; no return involved."""
from common import *
SEED, DRAWS = 20261125, 1000
res = {}
for market in ("US", "KR"):
    session = sessions(market)[-1][0]
    for strat in ("SWING", "LONG_TERM"):
        snaps = load(market, session)[strat]
        tick, fids, w, dom, N, A = matrix(snaps)
        S = composite(N, w)
        ok = ~np.isnan(S); N, S = N[ok], S[ok]
        n = len(S); k5 = n // 5
        top20, top5 = top_set(S, 20), top_set(S, k5)
        n70 = int((S >= 70).sum()); set70 = set(np.where(S >= 70)[0].tolist())
        rng = np.random.default_rng(SEED)
        key = f"{market}_{strat}"; res[key] = {"session": session, "n": n, "live_ge70": n70, "top_fifth_size": k5}
        for x in (0.10, 0.20, 0.50):
            for mode in ("uniform", "sign"):
                rho, t20, t5, c70, j70, dmax = [], [], [], [], [], []
                for _ in range(DRAWS):
                    u = rng.uniform(-x, x, len(w)) if mode == "uniform" else rng.choice([-x, x], len(w))
                    S2 = composite(N, w * (1 + u))
                    rho.append(spearman(S, S2))
                    t20.append(1 - len(top20 & top_set(S2, 20)) / 20)
                    t5.append(1 - len(top5 & top_set(S2, k5)) / k5)
                    s2 = set(np.where(S2 >= 70)[0].tolist())
                    c70.append(len(s2)); j70.append(len(set70 ^ s2))
                    dmax.append(float(np.max(np.abs(S2 - S))))
                q = lambda a, p: float(np.percentile(a, p))
                r = {"rho_median": q(rho, 50), "rho_p5": q(rho, 5), "rho_min": float(min(rho)), "top20_turnover_median": q(t20, 50), "top20_turnover_p95": q(t20, 95), "top20_turnover_max": float(max(t20)),
                     "top_fifth_turnover_median": q(t5, 50), "top_fifth_turnover_p95": q(t5, 95), "ge70_count_min": int(min(c70)), "ge70_count_median": q(c70, 50), "ge70_count_max": int(max(c70)),
                     "ge70_membership_changes_median": q(j70, 50), "ge70_membership_changes_p95": q(j70, 95), "max_abs_score_move_median": q(dmax, 50), "max_abs_score_move_p95": q(dmax, 95)}
                res[key][f"{mode}_{int(x*100)}"] = r
                print(f"{key:13s} ±{int(x*100):2d}% {mode:7s} rho med {r['rho_median']:.4f} p5 {r['rho_p5']:.4f} | top20 turnover med {r['top20_turnover_median']*100:4.1f}% p95 {r['top20_turnover_p95']*100:4.1f}% | top5th med {r['top_fifth_turnover_median']*100:4.1f}% p95 {r['top_fifth_turnover_p95']*100:4.1f}% | >=70: live {n70}, {r['ge70_count_min']}..{r['ge70_count_max']} (med {r['ge70_count_median']:.0f}), changes med {r['ge70_membership_changes_median']:.0f} p95 {r['ge70_membership_changes_p95']:.0f} | max |move| med {r['max_abs_score_move_median']:.2f} p95 {r['max_abs_score_move_p95']:.2f}")
        # equal weights as an extreme
        S2 = composite(N, np.ones_like(w))
        res[key]["equal_weights"] = {"rho": spearman(S, S2), "top20_turnover": 1 - len(top20 & top_set(S2, 20)) / 20, "top_fifth_turnover": 1 - len(top5 & top_set(S2, k5)) / k5, "ge70": int((S2 >= 70).sum())}
        print(f"{key:13s} equal weights: rho {res[key]['equal_weights']['rho']:.3f}, top20 turnover {res[key]['equal_weights']['top20_turnover']*100:.0f}%, top fifth {res[key]['equal_weights']['top_fifth_turnover']*100:.0f}%, >=70 {res[key]['equal_weights']['ge70']}")
        # how many scores sit within 1 and 2 points of a line
        res[key]["near_lines"] = {f"within_{d}_of_{L}": int((np.abs(S - L) < d).sum()) for L in (70, 67, 55, 40) for d in (1, 2)}
        print("   near lines:", res[key]["near_lines"])
dump("s03_weights.json", res)
