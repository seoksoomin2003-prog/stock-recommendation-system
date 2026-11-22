"""Agent 03, second extension.  Ledger snapshots only (scores, bands, factor values and the raw inputs stored with them) and random
numbers.  No price series, no forward return, no IC against returns.  Uses the Ledger directly; one session in memory at a time."""
import sys, pathlib, json, collections
real = pathlib.Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(real))
import numpy as np
from terminal.qsf.ledger import Ledger
from terminal.qsf.factors import ramp
led = Ledger(real)
OUT = {}


def rank(a):
    a = np.asarray(a, float); o = a.argsort(); r = np.empty(len(a)); r[o] = np.arange(len(a))
    vals, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(vals)); np.add.at(sums, inv, r); return sums[inv] / cnt[inv]


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float); ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10 or np.std(x[ok]) == 0 or np.std(y[ok]) == 0: return float("nan")
    return float(np.corrcoef(rank(x[ok]), rank(y[ok]))[0, 1])


def comp(M, w):
    ok = np.isfinite(M); num = np.where(ok, M, 0.0) @ w; den = ok @ w
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, 100 * num / den, np.nan)


def band_of(x):
    return np.digitize(x, [40.0, 55.0, 70.0, 80.0])


def r3(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 3)


def load(market, session):
    out = []
    for r in led._live_rows():
        if r["market"] == market and r["session"] == session:
            out += led._load(r)
    return [s for s in out if s.get("data_date") == session and s["ticker"] != "SPY"]


rows = led._live_rows()
sessions = {m: sorted({r["session"] for r in rows if r["market"] == m}) for m in ("US", "KR")}
rng = np.random.default_rng(3)
for m in ("US", "KR"):
    # A. the lines on every recorded day: how many stocks each band held, and the highest score
    per_day = collections.defaultdict(list)
    for d in sessions[m]:
        snaps = load(m, d)
        for strat in ("SWING", "LONG_TERM"):
            sc = np.array([s["score"] for s in snaps if s["strategy"] == strat and s.get("score") is not None], float)
            if len(sc) >= 50:
                per_day[strat].append({"session": d, "version": next(s.get("model_version") for s in snaps if s["strategy"] == strat), "n": int(len(sc)), "ge80": int((sc >= 80).sum()), "ge70": int((sc >= 70).sum()),
                                       "lt40": int((sc < 40).sum()), "max": r3(sc.max()), "median": r3(np.median(sc))})
        del snaps
    snaps = load(m, sessions[m][-1])
    for strat in ("SWING", "LONG_TERM"):
        S = [s for s in snaps if s["strategy"] == strat]
        key = f"{m}_{strat}"; res = OUT[key] = {"session": sessions[m][-1], "n": len(S), "a_lines_per_day": per_day[strat]}
        scored = [(r["factor"], r["domain"], r["weight"]) for r in S[0]["factors"] if r.get("scored") is not False and r.get("weight")]
        fids = [f for f, _d, _w in scored]; w = np.array([x for _f, _d, x in scored], float)
        look = [{r["factor"]: r for r in s["factors"] if r.get("scored") is not False} for s in S]
        M = np.array([[(lk.get(f) or {}).get("normalized") if (lk.get(f) or {}).get("normalized") is not None else np.nan for f in fids] for lk in look], float)
        score = np.array([s["score"] if s.get("score") is not None else np.nan for s in S], float)
        ok = np.isfinite(score)
        # B. how much of the score a few factors reproduce (least squares on the stocks where those factors exist)
        order = sorted(range(len(fids)), key=lambda j: -abs(spearman(M[:, j], score)) if np.isfinite(spearman(M[:, j], score)) else 0)
        r2 = {}
        for k in (1, 2, 3, 5):
            cols = order[:k]; okk = ok & np.isfinite(M[:, cols]).all(axis=1)
            X = np.column_stack([np.ones(okk.sum()), M[okk][:, cols]]); beta, *_ = np.linalg.lstsq(X, score[okk], rcond=None)
            fit = X @ beta; r2[str(k)] = {"factors": [fids[j] for j in cols], "r2": r3(1 - ((score[okk] - fit) ** 2).sum() / ((score[okk] - score[okk].mean()) ** 2).sum()), "rank_rho": r3(spearman(fit, score[okk]))}
        res["b_few_factors_reproduce"] = r2
        # C. points that near-constant factors add to every stock alike (mode share >= 0.9), and the mean points each factor gives
        const = {}
        for j, f in enumerate(fids):
            v = np.round(M[np.isfinite(M[:, j]), j], 4)
            if len(v):
                vals, cnt = np.unique(v, return_counts=True)
                if cnt.max() / len(v) >= 0.9:
                    const[f] = {"mode_value": r3(vals[cnt.argmax()]), "mode_share": r3(cnt.max() / len(v)), "weight": float(w[j]), "points_of_100_at_mode": r3(100 * w[j] * vals[cnt.argmax()] / w.sum())}
        res["c_near_constant"] = {"factors": const, "weight_share": r3(sum(v["weight"] for v in const.values()) / w.sum()), "all_missing": [f for j, f in enumerate(fids) if not np.isfinite(M[:, j]).any()],
                                  "mean_points_of_100_by_factor": {f: r3(100 * w[j] * np.nanmean(M[:, j]) / w.sum()) if np.isfinite(M[:, j]).any() else None for j, f in enumerate(fids)},
                                  "max_points_of_100_by_factor": {f: r3(100 * w[j] / w.sum()) for j, f in enumerate(fids)}}
        # D. the same weights on independent random factors (uniform 0..1): what stability the arithmetic alone gives
        R = rng.uniform(0, 1, (len(S), len(fids))); base = comp(R, w)
        loo = []
        for j in range(len(fids)):
            Rj = R.copy(); Rj[:, j] = np.nan; loo.append(spearman(base, comp(Rj, w)))
        pert = [spearman(base, comp(R, w * rng.uniform(0.8, 1.2, len(w)))) for _ in range(200)]
        noise = [spearman(base, comp(np.clip(R + rng.normal(0, 0.05, R.shape), 0, 1), w)) for _ in range(200)]
        eq = spearman(base, comp(R, np.ones(len(w))))
        res["d_random_benchmark"] = {"leave_one_out_rho_min": r3(min(loo)), "weights_20pct_rho_p5": r3(np.percentile(pert, 5)), "noise_0.05_rho_median": r3(np.median(noise)), "equal_factor_rho": r3(eq), "score_sd": r3(base.std())}
        # E. swing: reward/risk against the chart factors the same score rewards
        if strat == "SWING":
            rr = np.array([((lk.get("risk_reward") or {}).get("raw") or {}).get("reward_risk") if (lk.get("risk_reward") or {}).get("raw") else np.nan for lk in look], float)
            dist = np.array([((lk.get("breakout_volume") or {}).get("raw") or {}).get("dist_high") if (lk.get("breakout_volume") or {}).get("raw") else np.nan for lk in look], float)
            j = fids.index("risk_reward")
            near = dist >= -0.03; far = dist <= -0.20
            tech = np.array([(s["domains"].get("TECHNICAL") or {}).get("score_100") if (s["domains"].get("TECHNICAL") or {}).get("score_100") is not None else np.nan for s in S], float)
            top = tech >= np.nanpercentile(tech, 80)
            res["e_reward_risk"] = {"share_rr_lt_1.5": r3(np.nanmean(rr < 1.5)), "share_rr_lt_1.0_factor_zero": r3(np.nanmean(rr <= 1.0)), "rr_median": r3(np.nanmedian(rr)),
                                    "near_high_within_3pct": {"n": int(near.sum()), "rr_median": r3(np.nanmedian(rr[near])), "share_rr_ge_1.5": r3(np.nanmean(rr[near] >= 1.5)), "factor_mean": r3(np.nanmean(M[near, j]))},
                                    "far_from_high_20pct": {"n": int(far.sum()), "rr_median": r3(np.nanmedian(rr[far])), "share_rr_ge_1.5": r3(np.nanmean(rr[far] >= 1.5)), "factor_mean": r3(np.nanmean(M[far, j]))},
                                    "top_fifth_by_chart_domain": {"n": int(top.sum()), "share_rr_ge_1.5": r3(np.nanmean(rr[top] >= 1.5)), "factor_mean": r3(np.nanmean(M[top, j]))},
                                    "rho_rr_factor_vs_dist_high": r3(spearman(M[:, j], dist)), "rho_rr_factor_vs_chart_domain": r3(spearman(M[:, j], tech)),
                                    "entry_status": dict(collections.Counter(s.get("entry_status") for s in S)), "entry_status_score_ge_70": dict(collections.Counter(s.get("entry_status") for s, sc in zip(S, score) if sc >= 70))}
        # F. QSF-1.5.0 replayed on the recorded factor values (an approximation: "losing money now" is read from a stored ROE <= 0,
        #    which misses companies with negative equity; the cash-conversion zero needs operating cash flow, which is not stored)
        if strat == "LONG_TERM":
            j = fids.index("growth_quality"); new = M.copy(); hit = 0
            for i, lk in enumerate(look):
                g = (lk.get("growth_quality") or {}).get("raw") or {}; b = (lk.get("business_quality") or {}).get("raw") or {}
                if np.isfinite(M[i, j]) and g and g.get("eps_cagr3") is None and b.get("roe") is not None and b["roe"] <= 0:
                    parts = [ramp(g.get("rev_cagr3"), -0.02, 0.15), 0.0, ramp(g.get("rev_growth"), -0.05, 0.20)]; parts = [p for p in parts if p is not None]
                    new[i, j] = sum(parts) / len(parts); hit += 1
            alt = comp(new, w); dlt = alt - score
            res["f_replay_1_5_0_growth"] = {"loss_makers_with_empty_eps_growth": hit, "growth_factor_ge_0.7_before": int(sum(1 for i in range(len(S)) if new[i, j] != M[i, j] and M[i, j] >= 0.7)),
                                            "scores_changed": int((np.abs(dlt) > 1e-9).sum()), "largest_fall": r3(np.nanmin(dlt)), "mean_fall_of_changed": r3(np.nanmean(dlt[np.abs(dlt) > 1e-9])) if (np.abs(dlt) > 1e-9).any() else None,
                                            "left_buy_band": int(((score >= 70) & (alt < 70)).sum()), "rank_rho": r3(spearman(score, alt)), "mean_score_of_changed_before": r3(np.nanmean(score[np.abs(dlt) > 1e-9])) if (np.abs(dlt) > 1e-9).any() else None}
        else:
            j = fids.index("earnings_revenue_quality"); new = M.copy(); hit = 0
            for i, lk in enumerate(look):
                g = (lk.get("earnings_revenue_quality") or {}).get("raw") or {}; b = (lk.get("profitability") or {}).get("raw") or {}
                if np.isfinite(M[i, j]) and g and g.get("eps_growth") is None and b.get("roe") is not None and b["roe"] <= 0:
                    parts = [ramp(g.get("rev_growth"), -0.05, 0.20), 0.0, ramp(g.get("ocf_to_ni"), 0.5, 1.2)]; parts = [p for p in parts if p is not None]
                    new[i, j] = sum(parts) / len(parts); hit += 1
            alt = comp(new, w); dlt = alt - score
            res["f_replay_1_5_0_eps_part_only"] = {"loss_makers_with_empty_eps_growth": hit, "scores_changed": int((np.abs(dlt) > 1e-9).sum()), "largest_fall": r3(np.nanmin(dlt)), "left_buy_band": int(((score >= 70) & (alt < 70)).sum())}
        # G. the confidence label under the input rule of 2026-11-22, from the raw inputs stored (an approximation: a raw value that is
        #    None counts as an absent input; the engine counts the figures a factor averages, which is not always the stored raw dict)
        part_w = np.zeros(len(S)); app = np.zeros(len(S))
        for i, lk in enumerate(look):
            for jj, f in enumerate(fids):
                r = lk.get(f) or {}
                if r.get("status") != "NOT_APPLICABLE": app[i] += w[jj]
                if r.get("normalized") is not None:
                    raw = r.get("raw") if isinstance(r.get("raw"), dict) else {}
                    vals = [v for k, v in raw.items() if k not in ("window_days", "window_obs", "benchmark", "issues", "insider", "from", "basis", "overdue")]
                    share = (sum(v is not None for v in vals) / len(vals)) if vals else 1.0
                    part_w[i] += w[jj] * (0.5 if r.get("status") == "STALE" else 1.0) * share
        ic = part_w / app
        res["g_input_coverage_proxy"] = {"median": r3(np.median(ic)), "p5": r3(np.percentile(ic, 5)), "share_ge_0.9": r3((ic >= 0.9).mean()), "share_0.8_0.9": r3(((ic >= 0.8) & (ic < 0.9)).mean()), "share_lt_0.8": r3((ic < 0.8).mean()),
                                         "recorded_confidence": dict(collections.Counter(s.get("confidence") for s in S))}
    del snaps
json.dump(OUT, open(pathlib.Path(__file__).parent / "exp_ext2.json", "w"), ensure_ascii=False, indent=1, default=str)
for k, r in OUT.items():
    print("\n=====", k, r["session"], "n", r["n"])
    print(" lines per day:"); [print("   ", x) for x in r["a_lines_per_day"]]
    for kk, v in r.items():
        if kk not in ("a_lines_per_day", "session", "n"): print(" ", kk, json.dumps(v, ensure_ascii=False))
