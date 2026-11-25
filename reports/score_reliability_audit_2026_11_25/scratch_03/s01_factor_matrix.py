"""AGENT 3, experiment 1: recorded factor values -> descriptive statistics, redundancy, effective bets, sector dependence.

Reads ONLY the QSF ledger's factor rows (normalized values, status, weights) and score of recorded sessions, the cached company
records for sector labels (data/qsf/cache/info_*.json: only the "sector" field) and the Korean master file (industry).
No price, no return, no outcome is read or computed.  Writes s01_out.json in this folder.
"""
import gzip, json, sys, glob, hashlib, math
from pathlib import Path
from collections import Counter, defaultdict
import numpy as np
import pandas as pd


def rankdata(a):
    return pd.Series(a).rank(method="average").to_numpy()


def spearmanr(a, b):
    """Spearman rank correlation (average ranks for ties); returned as a 1-tuple-like for the scipy call shape."""
    ra, rb = rankdata(np.asarray(a, float)), rankdata(np.asarray(b, float))
    if np.std(ra) == 0 or np.std(rb) == 0:
        return (float("nan"),)
    return (float(np.corrcoef(ra, rb)[0, 1]),)


def average_linkage_clusters(D, cut):
    """Agglomerative clustering, average linkage, merge while the smallest average distance is under ``cut``.  Returns labels."""
    groups = [[i] for i in range(len(D))]
    while len(groups) > 1:
        best, pair = None, None
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                d = np.mean([D[i, j] for i in groups[a] for j in groups[b]])
                if best is None or d < best:
                    best, pair = d, (a, b)
        if best >= cut:
            break
        a, b = pair
        groups[a] = groups[a] + groups[b]; del groups[b]
    lab = np.zeros(len(D), int)
    for l, g in enumerate(groups, 1):
        for i in g:
            lab[i] = l
    return lab

from terminal.qsf.ledger import Ledger
from terminal.qsf.order_plan import session_snaps
from terminal.qsf import config
from terminal import kr_sectors

BASE = Path(".")
OUT = Path(__file__).parent / "s01_out.json"
SESSIONS = sys.argv[1:] or ["2026-11-24", "2026-11-16"]
led = Ledger(BASE)


def us_sectors():
    out = {}
    for p in glob.glob("data/qsf/cache/info_*.json"):
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        key = d.get("key", "")
        sec = (d.get("data") or {}).get("sector")
        if key.startswith("info:") and sec:
            out[key[5:]] = sec
    return out


def kr_sector_map():
    import pandas as pd
    sdir = BASE / "data" / "kr" / "security_master"
    meta = json.loads((sdir / "LATEST.json").read_text(encoding="utf-8"))
    df = pd.read_csv(sdir / meta["file"], dtype=str, usecols=lambda c: c in ("canonical_ticker", "industry", "company_name"))
    return {c: kr_sectors.broad_sector(c, i, n if isinstance(n, str) else None) for c, i, n in zip(df["canonical_ticker"], df["industry"], df.get("company_name", [None] * len(df)))
            if isinstance(c, str) and isinstance(i, str) and i.strip()}


US_SEC, KR_SEC = us_sectors(), kr_sector_map()


def eta2(vals, groups):
    """Between-group share of variance (one-way)."""
    ok = [(v, g) for v, g in zip(vals, groups) if v is not None and g]
    if len(ok) < 30:
        return None, 0
    v = np.array([a for a, _ in ok]); g = [b for _, b in ok]
    tot = ((v - v.mean()) ** 2).sum()
    if tot <= 0:
        return None, len(ok)
    by = defaultdict(list)
    for a, b in ok:
        by[b].append(a)
    between = sum(len(x) * (np.mean(x) - v.mean()) ** 2 for x in by.values())
    k, n = len(by), len(ok)
    # also the value expected with no sector effect: (k-1)/(n-1)
    return float(between / tot), n, float((k - 1) / (n - 1))


def analyse(market, strategy, session):
    snaps = [s for s in session_snaps(led, market, session) if s.get("strategy") == strategy]
    if not snaps:
        return None
    profile = config.profile_for(market, strategy)
    weights = {f: w for d in profile["domains"].values() for f, w in d.items()}
    refs = {f: w for d in (profile.get("reference") or {}).values() for f, w in d.items()}
    dom = {}
    fids = []
    for s in snaps:
        for f in s["factors"]:
            if f["factor"] not in dom:
                dom[f["factor"]] = f["domain"]; fids.append(f["factor"])
    tick = [s["ticker"] for s in snaps]
    sector = [(US_SEC.get(t) if market == "US" else KR_SEC.get(t)) for t in tick]
    X = np.full((len(snaps), len(fids)), np.nan)
    status = {f: Counter() for f in fids}
    rawnone = defaultdict(Counter)      # factor -> raw key -> count of None among rows whose factor has a raw dict
    rawhave = Counter()
    recorded_w = {}
    for i, s in enumerate(snaps):
        for f in s["factors"]:
            j = fids.index(f["factor"])
            status[f["factor"]][f.get("status")] += 1
            recorded_w.setdefault(f["factor"], f.get("weight") if f.get("scored") is not False else 0)
            if f.get("normalized") is not None and f.get("status") in ("REAL", "STALE"):
                X[i, j] = f["normalized"]
            if isinstance(f.get("raw"), dict):
                rawhave[f["factor"]] += 1
                for k, v in f["raw"].items():
                    if v is None:
                        rawnone[f["factor"]][k] += 1
    score = np.array([s["score"] if s.get("score") is not None else np.nan for s in snaps])
    n = len(snaps)
    desc = {}
    for j, f in enumerate(fids):
        col = X[:, j]; v = col[np.isfinite(col)]
        if len(v) == 0:
            desc[f] = {"domain": dom[f], "weight": weights.get(f, 0), "reference_weight": refs.get(f), "n": 0, "status": dict(status[f])}
            continue
        mode_val, mode_n = Counter(np.round(v, 6)).most_common(1)[0]
        e = eta2([None if not np.isfinite(x) else float(x) for x in col], sector)
        ok = np.isfinite(col) & np.isfinite(score)
        rs = float(spearmanr(col[ok], score[ok])[0]) if ok.sum() > 30 and np.std(col[ok]) > 0 else None
        desc[f] = {"domain": dom[f], "weight": weights.get(f, 0), "reference_weight": refs.get(f), "n": int(len(v)), "status": dict(status[f]),
                   "mean": float(v.mean()), "sd": float(v.std(ddof=1)) if len(v) > 1 else 0.0, "p25": float(np.percentile(v, 25)), "median": float(np.median(v)), "p75": float(np.percentile(v, 75)),
                   "share_0": float((v <= 1e-9).mean()), "share_1": float((v >= 1 - 1e-9).mean()), "mode": float(mode_val), "share_mode": float(mode_n / len(v)), "distinct": int(len(set(np.round(v, 6)))),
                   "eta2_sector": e[0], "eta2_n": e[1], "eta2_null": e[2] if len(e) > 2 else None, "spearman_with_score": rs,
                   "raw_none_share": {k: c / rawhave[f] for k, c in rawnone[f].items()} if rawhave[f] else {}}
    # ---- redundancy among the scored factors that vary
    scored = [f for f in fids if weights.get(f, 0) > 0 and desc[f].get("n", 0) >= 0.3 * n and desc[f].get("sd", 0) > 1e-6]
    idx = [fids.index(f) for f in scored]
    Xs = X[:, idx]
    k = len(scored)
    P = np.eye(k); S = np.eye(k); N = np.zeros((k, k), int)
    for a in range(k):
        for b in range(a + 1, k):
            ok = np.isfinite(Xs[:, a]) & np.isfinite(Xs[:, b])
            N[a, b] = N[b, a] = ok.sum()
            if ok.sum() > 30 and np.std(Xs[ok, a]) > 0 and np.std(Xs[ok, b]) > 0:
                P[a, b] = P[b, a] = np.corrcoef(Xs[ok, a], Xs[ok, b])[0, 1]
                S[a, b] = S[b, a] = spearmanr(Xs[ok, a], Xs[ok, b])[0]
            else:
                P[a, b] = P[b, a] = S[a, b] = S[b, a] = 0.0
    # eigen on the mean-imputed matrix (a proper correlation matrix); the pairwise one is reported for the pairs
    Xi = np.where(np.isfinite(Xs), Xs, np.nanmean(Xs, axis=0))
    R = np.corrcoef(Xi, rowvar=False)
    Rr = np.corrcoef(np.apply_along_axis(rankdata, 0, Xi), rowvar=False)
    ev = np.sort(np.linalg.eigvalsh(R))[::-1]; evr = np.sort(np.linalg.eigvalsh(Rr))[::-1]
    pr = float(ev.sum() ** 2 / (ev ** 2).sum()); prr = float(evr.sum() ** 2 / (evr ** 2).sum())
    pe = ev / ev.sum(); ent = float(np.exp(-(pe[pe > 0] * np.log(pe[pe > 0])).sum()))
    # the score's own bets: covariance of the weighted contributions w_i * x_i (mean-imputed), as the score is their sum over a near-constant denominator
    w = np.array([weights[f] for f in scored], float)
    C = np.cov(Xi * w, rowvar=False)
    evc = np.sort(np.linalg.eigvalsh(C))[::-1]
    prc = float(evc.sum() ** 2 / (evc ** 2).sum())
    tot = (Xi * w).sum(axis=1)
    var_share = {f: float(np.cov(Xi[:, a] * w[a], tot)[0, 1] / np.var(tot, ddof=1)) for a, f in enumerate(scored)}
    own_var = {f: float(np.var(Xi[:, a] * w[a], ddof=1) / np.var(tot, ddof=1)) for a, f in enumerate(scored)}
    sum_corr = float(spearmanr(tot[np.isfinite(score)], score[np.isfinite(score)])[0])
    # clusters: average linkage on 1 - |Spearman|, cut at 0.5 (|rho| >= 0.5 inside a cluster on average)
    D = 1 - np.abs(S); np.fill_diagonal(D, 0)
    lab = average_linkage_clusters(D, 0.5)
    clusters = defaultdict(list)
    for f, l in zip(scored, lab):
        clusters[int(l)].append(f)
    wsum = sum(weights[f] for f in scored)
    cl = []
    for l, fs in clusters.items():
        cl.append({"factors": fs, "weight": sum(weights[f] for f in fs), "weight_share": sum(weights[f] for f in fs) / wsum, "variance_share": sum(var_share[f] for f in fs)})
    cl.sort(key=lambda c: -c["variance_share"])
    pairs = sorted(([scored[a], scored[b], float(P[a, b]), float(S[a, b]), int(N[a, b])] for a in range(k) for b in range(a + 1, k)), key=lambda r: -abs(r[3]))
    # sector dependence of the composite
    es = eta2([None if not np.isfinite(x) else float(x) for x in score], sector)
    sec_mean = defaultdict(list)
    for x, g in zip(score, sector):
        if np.isfinite(x) and g:
            sec_mean[g].append(float(x))
    return {"market": market, "strategy": strategy, "session": session, "model_version": snaps[0].get("model_version"), "n": n, "sector_known": sum(1 for g in sector if g),
            "factors": desc, "scored_varying": scored, "weights_sum_scored": wsum, "pearson": {"labels": scored, "matrix": np.round(P, 3).tolist()}, "spearman": {"labels": scored, "matrix": np.round(S, 3).tolist()},
            "top_pairs": pairs[:25], "eigen_pearson": np.round(ev, 3).tolist(), "eigen_spearman": np.round(evr, 3).tolist(), "participation_ratio_pearson": pr, "participation_ratio_spearman": prr, "entropy_bets": ent,
            "eigen_weighted_share": np.round(evc / evc.sum(), 3).tolist(), "participation_ratio_weighted": prc, "variance_share": var_share, "own_variance_share": own_var, "sum_vs_score_spearman": sum_corr,
            "clusters": cl, "score_eta2_sector": es[0], "score_eta2_null": es[2] if len(es) > 2 else None,
            "score_by_sector": {g: {"n": len(v), "mean": float(np.mean(v)), "share_ge70": float(np.mean([x >= 70 for x in v]))} for g, v in sorted(sec_mean.items(), key=lambda kv: -np.mean(kv[1]))},
            "score_stats": {"mean": float(np.nanmean(score)), "sd": float(np.nanstd(score, ddof=1)), "ge70": int(np.nansum(score >= 70)), "n": int(np.isfinite(score).sum())}}


res = {}
for session in SESSIONS:
    for market in ("US", "KR"):
        for strategy in ("SWING", "LONG_TERM"):
            r = analyse(market, strategy, session)
            if r:
                res[f"{market}_{strategy}_{session}"] = r
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
for k, r in res.items():
    print("=" * 110); print(k, r["model_version"], "n", r["n"], "sector known", r["sector_known"])
    print(f"  scored varying factors {len(r['scored_varying'])} | PR pearson {r['participation_ratio_pearson']:.2f} spearman {r['participation_ratio_spearman']:.2f} entropy {r['entropy_bets']:.2f} | weighted PR {r['participation_ratio_weighted']:.2f} | sum~score rho {r['sum_vs_score_spearman']:.3f}")
    print("  eig weighted share", r["eigen_weighted_share"][:6])
    print(f"  score eta2 sector {r['score_eta2_sector']} (null {r['score_eta2_null']})  stats {r['score_stats']}")
    print(f"  {'factor':26s} {'dom':5s} {'w':>3s} {'n':>4s} {'mean':>5s} {'sd':>5s} {'s0':>5s} {'s1':>5s} {'mode':>5s} {'smode':>5s} {'dist':>4s} {'eta2':>5s} {'rho_sc':>6s} {'varsh':>6s}  status / raw None")
    for f, d in r["factors"].items():
        if not d.get("n"):
            print(f"  {f:26s} {d['domain'][:5]:5s} {d['weight']:>3} {0:>4}   -- {d['status']}"); continue
        vs = r["variance_share"].get(f)
        print(f"  {f:26s} {d['domain'][:5]:5s} {d['weight']:>3} {d['n']:>4} {d['mean']:5.2f} {d['sd']:5.2f} {d['share_0']:5.2f} {d['share_1']:5.2f} {d['mode']:5.2f} {d['share_mode']:5.2f} {d['distinct']:>4} "
              f"{(d['eta2_sector'] if d['eta2_sector'] is not None else float('nan')):5.2f} {(d['spearman_with_score'] if d['spearman_with_score'] is not None else float('nan')):6.2f} {(vs if vs is not None else float('nan')):6.2f}  "
              f"{ {k: v for k, v in d['status'].items() if k != 'REAL'} } { {k: round(v, 2) for k, v in d['raw_none_share'].items() if v > 0.02} }")
    print("  clusters:")
    for c in r["clusters"]:
        print(f"    w {c['weight']:>3} ({c['weight_share']:.0%})  var {c['variance_share']:.0%}  {c['factors']}")
    print("  top pairs (pearson, spearman, n):")
    for p in r["top_pairs"][:12]:
        print(f"    {p[0]:24s} {p[1]:24s} {p[2]:6.2f} {p[3]:6.2f} {p[4]}")
