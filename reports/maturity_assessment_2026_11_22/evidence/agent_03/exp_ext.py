"""Agent 03 (maturity assessment 2026-11-22): extensions to exp_scores.py.  Ledger snapshots only: scores, bands, factor values.
No price, no forward return, no IC against returns is read or computed anywhere in this file.  One session is loaded at a time."""
import sys, pathlib, json, collections
real = pathlib.Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(real))
from utils import runtime_config
runtime_config.load_local_env(real / ".env")
import numpy as np
from terminal.services import Terminal
from terminal import analyst_extra as ax
from terminal.qsf import config, order_plan as op
t = Terminal(real)
OUT = {}
LINES = (80.0, 70.0, 55.0, 40.0)


def rank(a):
    a = np.asarray(a, float); o = a.argsort(); r = np.empty(len(a)); r[o] = np.arange(len(a))
    vals, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(vals)); np.add.at(sums, inv, r); return sums[inv] / cnt[inv]


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float); ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 10 or np.std(x[ok]) == 0 or np.std(y[ok]) == 0: return float("nan")
    return float(np.corrcoef(rank(x[ok]), rank(y[ok]))[0, 1])


def comp(M, w):
    """The engine's composite on a matrix of normalised values (NaN = missing or not applicable): both sums leave the gap out."""
    ok = np.isfinite(M); num = np.where(ok, M, 0.0) @ w; den = ok @ w
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, 100 * num / den, np.nan)


def band_of(x):
    return np.digitize(x, [40.0, 55.0, 70.0, 80.0])


def topk(a, k=20):
    return set(np.argsort(-np.nan_to_num(a, nan=-1))[:k])


def r3(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 3)


sessions = {m: sorted({r["session"] for r in t.qsf.ledger._live_rows() if r["market"] == m}) for m in ("US", "KR")}
rng = np.random.default_rng(20261122)
for m in ("US", "KR"):
    last = sessions[m][-1]
    snaps = [s for s in op.session_snaps(t.qsf.ledger, m, last) if s.get("data_date") == last and s["ticker"] not in ("SPY",)]
    sector = {r["ticker"]: ax.SECTOR_KO.get(r.get("sector"), r.get("sector")) for r in t.qsf.screen_rows(m).get("rows") or []}
    scores_by = {}
    for strat in ("SWING", "LONG_TERM"):
        S = [s for s in snaps if s["strategy"] == strat]
        key = f"{m}_{strat}"; res = OUT[key] = {"session": last, "n": len(S), "model": S[0].get("model_version"), "profile": S[0].get("profile")}
        scored = [(r["factor"], r["domain"], r["weight"]) for r in S[0]["factors"] if r.get("scored") is not False and r.get("weight")]
        fids = [f for f, _d, _w in scored]; doms = [d for _f, d, _w in scored]; w = np.array([x for _f, _d, x in scored], float)
        look = [{r["factor"]: r for r in s["factors"] if r.get("scored") is not False} for s in S]
        M = np.array([[(lk.get(f) or {}).get("normalized") if (lk.get(f) or {}).get("normalized") is not None else np.nan for f in fids] for lk in look], float)
        score = np.array([s["score"] if s.get("score") is not None else np.nan for s in S], float)
        base = comp(M, w); ok = np.isfinite(score)
        scores_by[strat] = {s["ticker"]: sc for s, sc in zip(S, score)}
        # X1 the script's formula against the recorded score
        res["x1_formula_check_max_abs_diff"] = r3(np.nanmax(np.abs(base - score)))
        res["x1_score_mean_sd_min_max"] = [r3(np.nanmean(score)), r3(np.nanstd(score)), r3(np.nanmin(score)), r3(np.nanmax(score))]
        res["x1_band_counts"] = {name: int(((score >= lo) & (score < hi)).sum()) for name, lo, hi in (("ge80", 80, 101), ("70_80", 70, 80), ("55_70", 55, 70), ("40_55", 40, 55), ("lt40", 0, 40))}
        # X2 how constant each factor is, and how often it was computed from part of its raw inputs
        inv = {}
        for j, f in enumerate(fids):
            col = M[:, j]; okj = np.isfinite(col); v = np.round(col[okj], 4)
            vals, cnt = np.unique(v, return_counts=True)
            raws = [(lk.get(f) or {}).get("raw") for lk in look]
            part = [any(x is None for x in rw.values()) for rw, k in zip(raws, okj) if k and isinstance(rw, dict) and rw]
            status = collections.Counter((lk.get(f) or {}).get("status") for lk in look)
            inv[f] = {"domain": doms[j], "weight": float(w[j]), "weight_share": r3(w[j] / w.sum()), "available": r3(okj.mean()), "status": dict(status),
                      "mean": r3(v.mean()) if len(v) else None, "sd": r3(v.std()) if len(v) else None, "distinct": int(len(vals)),
                      "mode_value": r3(vals[cnt.argmax()]) if len(v) else None, "mode_share": r3(cnt.max() / len(v)) if len(v) else None,
                      "at_zero": r3((v <= 0.0001).mean()) if len(v) else None, "at_one": r3((v >= 0.9999).mean()) if len(v) else None,
                      "inside_ramp": r3(((v > 0.0001) & (v < 0.9999)).mean()) if len(v) else None,
                      "raw_part_missing_share": r3(np.mean(part)) if part else None, "rho_with_score": r3(spearman(col, score))}
        res["x2_inventory"] = inv
        # X3 effective number of factors, four ways
        C = np.eye(len(fids))
        for a in range(len(fids)):
            for b in range(a + 1, len(fids)):
                C[a, b] = C[b, a] = spearman(M[:, a], M[:, b])
        Cz = np.nan_to_num(C, nan=0.0); ev = np.linalg.eigvalsh(Cz); ev = ev[ev > 1e-9]; p = ev / ev.sum()
        ws = w / w.sum()
        res["x3_effective"] = {"factors": len(fids), "participation_ratio": r3(ev.sum() ** 2 / (ev ** 2).sum()), "entropy_number": r3(np.exp(-(p * np.log(p)).sum())),
                               "eigen_gt_1": int((ev > 1).sum()), "by_weight_inverse_hhi": r3(1 / (ws ** 2).sum()),
                               "pairs_abs_rho_ge_0.3": sorted(((fids[a], fids[b], r3(C[a, b])) for a in range(len(fids)) for b in range(a + 1, len(fids)) if np.isfinite(C[a, b]) and abs(C[a, b]) >= 0.3), key=lambda x: -abs(x[2]))}
        offd = np.abs(Cz[np.triu_indices(len(fids), 1)]); res["x3_effective"]["median_abs_pair_rho"] = r3(np.median(offd)); res["x3_effective"]["share_pairs_abs_rho_lt_0.2"] = r3((offd < 0.2).mean())
        # X4 variance share of every factor and domain on ALL scored stocks: part_ij = 100 w_j n_ij / (weight present for stock i), parts add up to the score
        okM = np.isfinite(M); den = okM @ w
        parts = 100 * np.where(okM, M, 0.0) * w / den[:, None]
        tot = parts.sum(axis=1); var = tot[ok].var()
        fshare = {f: float(np.cov(parts[ok, j], tot[ok])[0, 1] * (ok.sum() - 1) / ok.sum() / var) for j, f in enumerate(fids)}
        dshare = collections.defaultdict(float); dweight = collections.defaultdict(float)
        for j, f in enumerate(fids): dshare[doms[j]] += fshare[f]; dweight[doms[j]] += ws[j]
        pos = np.array([max(v, 0) for v in fshare.values()]); pos = pos / pos.sum()
        res["x4_variance"] = {"factor_share": {f: r3(v) for f, v in sorted(fshare.items(), key=lambda kv: -kv[1])}, "domain_share": {d: r3(v) for d, v in dshare.items()}, "domain_weight": {d: r3(v) for d, v in dweight.items()},
                              "effective_factors_by_variance": r3(1 / (pos ** 2).sum()), "top3_factor_share": r3(sum(sorted(fshare.values(), reverse=True)[:3]))}
        dscore = {d: np.array([(s["domains"].get(d) or {}).get("score_100") if (s["domains"].get(d) or {}).get("score_100") is not None else np.nan for s in S], float) for d in dweight}
        res["x4_rho_score_vs_domain"] = {d: r3(spearman(score, v)) for d, v in dscore.items()}
        res["x4_rho_between_domains"] = {f"{a}|{b}": r3(spearman(dscore[a], dscore[b])) for i, a in enumerate(dscore) for b in list(dscore)[i + 1:]}
        # X5 other weightings fixed in advance of looking: every factor equal, every domain equal
        buy = np.nan_to_num(score, nan=0) >= 70
        dom_n = collections.Counter(doms)
        alts = {"equal_factor": np.ones(len(fids)), "equal_domain": np.array([1 / dom_n[d] for d in doms])}
        res["x5_other_weights"] = {}
        for name, wa in alts.items():
            alt = comp(M, wa)
            res["x5_other_weights"][name] = {"rho": r3(spearman(score, alt)), "top20_kept": len(topk(score) & topk(alt)), "buy_before_after_kept": [int(buy.sum()), int((alt >= 70).sum()), int(((alt >= 70) & buy).sum())],
                                             "band_changed_share": r3((band_of(alt[ok]) != band_of(score[ok])).mean()), "mean_abs_change": r3(np.nanmean(np.abs(alt - score)))}
        # X5b leave one factor out, every factor
        loo = {}
        for j, f in enumerate(fids):
            Mj = M.copy(); Mj[:, j] = np.nan; alt = comp(Mj, w)
            loo[f] = {"rho": r3(spearman(score, alt)), "top20_kept": len(topk(score) & topk(alt)), "buy_after": int((np.nan_to_num(alt, nan=0) >= 70).sum()), "buy_kept": int(((np.nan_to_num(alt, nan=0) >= 70) & buy).sum()),
                      "band_changed_share": r3((band_of(np.nan_to_num(alt[ok], nan=0)) != band_of(score[ok])).mean()), "max_abs_change": r3(np.nanmax(np.abs(alt - score)))}
        res["x5_leave_one_out"] = {"buy_before": int(buy.sum()), "rho_min_median": [r3(min(v["rho"] for v in loo.values())), r3(np.median([v["rho"] for v in loo.values()]))],
                                   "top20_kept_min_median": [min(v["top20_kept"] for v in loo.values()), int(np.median([v["top20_kept"] for v in loo.values()]))],
                                   "band_changed_share_max_median": [max(v["band_changed_share"] for v in loo.values()), r3(np.median([v["band_changed_share"] for v in loo.values()]))], "by_factor": loo}
        # X5c weights perturbed by a uniform factor, 300 draws each: rank, top 20, buy band, any band
        res["x5_weight_perturbation"] = {}
        for amp in (0.1, 0.2, 0.5):
            rh, ov, keep, chg, nb = [], [], [], [], []
            for _ in range(300):
                alt = comp(M, w * rng.uniform(1 - amp, 1 + amp, len(w)))
                rh.append(spearman(score, alt)); ov.append(len(topk(score) & topk(alt))); nb.append(int((alt[ok] >= 70).sum()))
                keep.append(((alt >= 70) & buy).sum() / buy.sum() if buy.sum() else np.nan); chg.append((band_of(alt[ok]) != band_of(score[ok])).mean())
            res["x5_weight_perturbation"][f"{int(amp * 100)}pct"] = {"rho_p5_median": [r3(np.percentile(rh, 5)), r3(np.median(rh))], "top20_kept_p5_median": [int(np.percentile(ov, 5)), int(np.median(ov))],
                                                                    "buy_kept_p5_median": [r3(np.nanpercentile(keep, 5)), r3(np.nanmedian(keep))] if buy.sum() else None, "buy_count_p5_p95": [int(np.percentile(nb, 5)), int(np.percentile(nb, 95))],
                                                                    "band_changed_share_median_p95": [r3(np.median(chg)), r3(np.percentile(chg, 95))]}
        # X6 small changes in the data: noise on every factor's 0..1 value (clipped), 300 draws each
        res["x6_data_noise"] = {}
        for sd in (0.02, 0.05, 0.10):
            rh, ov, keep, chg, mad, nb = [], [], [], [], [], []
            for _ in range(300):
                alt = comp(np.clip(M + rng.normal(0, sd, M.shape), 0, 1), w)
                rh.append(spearman(score, alt)); ov.append(len(topk(score) & topk(alt))); nb.append(int((alt[ok] >= 70).sum()))
                keep.append(((alt >= 70) & buy).sum() / buy.sum() if buy.sum() else np.nan); chg.append((band_of(alt[ok]) != band_of(score[ok])).mean()); mad.append(np.nanmean(np.abs(alt - score)))
            res["x6_data_noise"][f"sd_{sd}"] = {"rho_p5_median": [r3(np.percentile(rh, 5)), r3(np.median(rh))], "top20_kept_p5_median": [int(np.percentile(ov, 5)), int(np.median(ov))],
                                                 "buy_kept_p5_median": [r3(np.nanpercentile(keep, 5)), r3(np.nanmedian(keep))] if buy.sum() else None, "buy_count_p5_p95": [int(np.percentile(nb, 5)), int(np.percentile(nb, 95))],
                                                 "band_changed_share_median": r3(np.median(chg)), "mean_abs_score_change": r3(np.mean(mad))}
        # X6b one factor of one stock moves by a quarter of its scale: how many points is that
        res["x6_points_per_quarter_step"] = {f: r3(25 * w[j] / w.sum()) for j, f in enumerate(fids)}
        # X6c normalisation: cross-sectional percentile ranks, and z-scores, instead of the fixed ramps
        P = np.full_like(M, np.nan); Z = np.full_like(M, np.nan)
        for j in range(M.shape[1]):
            okj = np.isfinite(M[:, j])
            if okj.sum() > 1:
                P[okj, j] = rank(M[okj, j]) / (okj.sum() - 1); sdj = M[okj, j].std(); Z[okj, j] = (M[okj, j] - M[okj, j].mean()) / sdj if sdj > 0 else 0.0
        altp, altz = comp(P, w), comp(Z, w)
        k5 = max(1, int(ok.sum()) // 5)
        res["x6_normalisation"] = {"percentile": {"rho": r3(spearman(score, altp)), "top20_kept": len(topk(score) & topk(altp)), "top_quintile_kept_share": r3(len(topk(score, k5) & topk(altp, k5)) / k5)},
                                   "zscore": {"rho": r3(spearman(score, altz)), "top20_kept": len(topk(score) & topk(np.where(np.isfinite(altz), altz, -1e9))), "top_quintile_kept_share": r3(len(topk(score, k5) & topk(np.where(np.isfinite(altz), altz, -1e9), k5)) / k5)}}
        # X7 how many stocks stand next to each fixed line
        res["x7_near_lines"] = {str(int(L)): {f"within_{d}": int((np.abs(score[ok] - L) <= d).sum()) for d in (0.5, 1, 2, 3)} for L in LINES}
        res["x7_near_any_line_within_1_share"] = r3(np.mean([min(abs(x - L) for L in LINES) <= 1 for x in score[ok]]))
        res["x7_in_buffer_67_70"] = int(((score >= 67) & (score < 70)).sum())
        # X9 sector and size
        sec = np.array([sector.get(s["ticker"]) or "?" for s in S], dtype=object)
        by = {x: score[(sec == x) & ok] for x in set(sec) if x != "?"}
        by = {x: v for x, v in by.items() if len(v) >= 5}
        grand = np.concatenate(list(by.values()))
        eta = float(sum(len(g) * (g.mean() - grand.mean()) ** 2 for g in by.values()) / ((grand - grand.mean()) ** 2).sum())
        neutral = np.array([sc - by[x].mean() if x in by and np.isfinite(sc) else np.nan for x, sc in zip(sec, score)], float)
        topq = topk(score, k5); topn = topk(np.where(np.isfinite(neutral), neutral, -1e9), k5)
        cap = np.array([(t.qsf.stored_info(s["ticker"], m) or {}).get("marketCap") or np.nan for s in S], float)
        capq = np.full(len(S), np.nan); okc = np.isfinite(cap) & ok
        capq[okc] = np.floor(rank(cap[okc]) / okc.sum() * 5).clip(0, 4)
        res["x9_sector_size"] = {"sector_eta_squared": r3(eta), "sectors": {x: {"n": int(len(v)), "mean_minus_all": r3(v.mean() - grand.mean()), "share_universe": r3(len(v) / len(grand)), "share_top_quintile": r3(sum(1 for i in topq if sec[i] == x) / k5),
                                                                              "share_buy_band": r3(sum(1 for i in np.where(buy)[0] if sec[i] == x) / max(1, int(buy.sum())))} for x, v in sorted(by.items(), key=lambda kv: -kv[1].mean())},
                                 "sector_neutral_rho": r3(spearman(score, neutral)), "sector_neutral_top_quintile_kept_share": r3(len(topq & topn) / k5),
                                 "rho_score_vs_log_cap": r3(spearman(score, np.log(cap))), "cap_known": int(np.isfinite(cap).sum()),
                                 "mean_score_by_cap_quintile_small_to_large": [r3(np.nanmean(score[capq == q])) for q in range(5)],
                                 "buy_band_by_cap_quintile_small_to_large": [int((buy & (capq == q)).sum()) for q in range(5)],
                                 "rho_factor_vs_log_cap_abs_ge_0.2": {f: r3(spearman(M[:, j], np.log(cap))) for j, f in enumerate(fids) if abs(spearman(M[:, j], np.log(cap))) >= 0.2}}
        res["x9_coverage"] = {"confidence": dict(collections.Counter(s.get("confidence") for s in S)), "coverage_p5_min": [r3(np.nanpercentile([s.get("coverage") or np.nan for s in S], 5)), r3(np.nanmin([s.get("coverage") or np.nan for s in S]))],
                              "actionability": dict(collections.Counter(s.get("actionability") for s in S)), "gaps_per_stock_mean": r3((~np.isfinite(M)).sum(axis=1).mean())}
    both = sorted(set(scores_by["SWING"]) & set(scores_by["LONG_TERM"]))
    OUT[f"{m}_SWING"]["x10_rho_swing_vs_long_same_day"] = OUT[f"{m}_LONG_TERM"]["x10_rho_swing_vs_long_same_day"] = r3(spearman([scores_by["SWING"][k] for k in both], [scores_by["LONG_TERM"][k] for k in both]))
    del snaps
    # X8 the lines over the recorded days: scores and labels only.  Hard line of 70 against the 70-in / 67-out rule of QSF-1.5.0.
    for strat in ("SWING", "LONG_TERM"):
        seq = []
        for d in sessions[m]:
            ss = [s for s in op.session_snaps(t.qsf.ledger, m, d) if s.get("data_date") == d and s["strategy"] == strat and s.get("score") is not None and s["ticker"] != "SPY"]
            if len(ss) >= 50:
                seq.append((d, ss[0].get("model_version"), {s["ticker"]: (float(s["score"]), s.get("actionability") == "ACTIONABLE") for s in ss}))
            del ss
        days = []
        for (d0, v0, a), (d1, v1, b) in zip(seq, seq[1:]):
            common = sorted(set(a) & set(b)); x = np.array([a[k][0] for k in common]); y = np.array([b[k][0] for k in common]); dlt = y - x
            days.append({"from": d0, "to": d1, "versions": [v0, v1], "n": len(common), "rho": r3(spearman(x, y)), "abs_change_median_p90_p99": [r3(np.median(np.abs(dlt))), r3(np.percentile(np.abs(dlt), 90)), r3(np.percentile(np.abs(dlt), 99))],
                         "share_abs_change_gt_3": r3((np.abs(dlt) > 3).mean()), "band_changed_share": r3((band_of(x) != band_of(y)).mean()), "buy_before_after_kept": [int((x >= 70).sum()), int((y >= 70).sum()), int(((x >= 70) & (y >= 70)).sum())],
                         "top20_kept": len(set(sorted(a, key=lambda k: -a[k][0])[:20]) & set(sorted(b, key=lambda k: -b[k][0])[:20]))})
        def flips(seq_part, buffered):
            state, n, held_days, entered = {}, 0, 0, 0
            for _d, _v, day in seq_part:
                nxt = {}
                for k, (sc, act) in day.items():
                    was = state.get(k)
                    inb = sc >= 70 or (buffered and was is not None and was[0] and was[1] and sc >= config.BUY_BAND_EXIT)
                    if was is not None and was[0] != inb: n += 1
                    if was is not None and not was[0] and inb: entered += 1
                    held_days += inb; nxt[k] = (inb, act)
                state = nxt
            return {"label_changes": n, "entries": entered, "stock_days_in_buy_band": int(held_days)}
        same = [x for x in seq if x[1] == seq[-1][1]]
        OUT[f"{m}_{strat}"]["x8_day_to_day"] = days
        OUT[f"{m}_{strat}"]["x8_buffer_replay"] = {"all_recorded_days": {"days": len(seq), "hard_70": flips(seq, False), "in_70_out_67": flips(seq, True)},
                                                   "days_of_newest_version": {"days": len(same), "version": seq[-1][1], "hard_70": flips(same, False), "in_70_out_67": flips(same, True)}}
        OUT[f"{m}_{strat}"]["x8_versions"] = [(d, v, len(day)) for d, v, day in seq]
json.dump(OUT, open(pathlib.Path(__file__).parent / "exp_ext.json", "w"), ensure_ascii=False, indent=1, default=str)
for k, r in OUT.items():
    print("\n=====", k, r["session"], "n", r["n"], r["model"], r["profile"])
    print(" formula check:", r["x1_formula_check_max_abs_diff"], "| score mean/sd/min/max:", r["x1_score_mean_sd_min_max"], "| bands:", r["x1_band_counts"])
    print(" effective:", {a: b for a, b in r["x3_effective"].items() if a != "pairs_abs_rho_ge_0.3"}); print("  pairs>=0.3:", r["x3_effective"]["pairs_abs_rho_ge_0.3"])
    print(" variance:", r["x4_variance"]); print(" rho score~domain:", r["x4_rho_score_vs_domain"], "| between domains:", r["x4_rho_between_domains"])
    print(" other weights:", r["x5_other_weights"]); print(" leave one out:", {a: b for a, b in r["x5_leave_one_out"].items() if a != "by_factor"})
    print("  worst three:", sorted(((f, v["rho"], v["top20_kept"], v["buy_after"], v["buy_kept"], v["band_changed_share"]) for f, v in r["x5_leave_one_out"]["by_factor"].items()), key=lambda x: x[1])[:3])
    print(" weight perturbation:", r["x5_weight_perturbation"]); print(" data noise:", r["x6_data_noise"]); print(" points per quarter step:", r["x6_points_per_quarter_step"])
    print(" normalisation:", r["x6_normalisation"]); print(" near lines:", r["x7_near_lines"], "| any line ±1:", r["x7_near_any_line_within_1_share"], "| 67-70:", r["x7_in_buffer_67_70"])
    print(" sector/size:", r["x9_sector_size"]); print(" coverage:", r["x9_coverage"]); print(" swing~long rho:", r["x10_rho_swing_vs_long_same_day"])
    print(" day to day:"); [print("  ", x) for x in r["x8_day_to_day"]]; print(" buffer replay:", r["x8_buffer_replay"])
    print(" inventory:"); [print("  ", f, v) for f, v in r["x2_inventory"].items()]
