"""Experiment 2: which factors and domains carry the score's cross-sectional variance on a recorded day.  No return involved.
Decomposition: a missing factor is read at the stock's own weighted mean (which leaves the engine's score unchanged exactly), so
score_i = 100/W * sum_f w_f n'_if and share_f = cov(100 w_f n'_f / W, score) / var(score); the shares add up to 1."""
import collections
from common import *

SESS = sys.argv[1] if len(sys.argv) > 1 else None
res = {}
for market in ("US", "KR"):
    session = SESS or sessions(market)[-1][0]
    for strat in ("SWING", "LONG_TERM"):
        snaps = load(market, session)[strat]
        tick, fids, w, dom, N, A = matrix(snaps)
        keep = ~np.isnan(N).all(axis=0)          # a factor no stock has is in neither sum for anyone: it is not part of the score
        dropped = [f for f, k in zip(fids, keep) if not k]
        fids, w, dom, N = [f for f, k in zip(fids, keep) if k], w[keep], [d for d, k in zip(dom, keep) if k], N[:, keep]
        rec = np.array([snaps[t]["score"] if snaps[t]["score"] is not None else np.nan for t in tick])
        S = composite(N, w)
        assert np.nanmax(np.abs(S - rec)) < 1e-9
        ok = ~np.isnan(S)
        Nf = np.where(np.isnan(N), (S / 100)[:, None], N)[ok]
        Sok = S[ok]
        C = 100 * Nf * w / w.sum()
        assert np.max(np.abs(C.sum(axis=1) - Sok)) < 1e-9
        var = Sok.var()
        rows = []
        for j, fid in enumerate(fids):
            col = N[ok, j]
            have = ~np.isnan(col)
            v = col[have]
            vals, cnt = np.unique(np.round(v, 3), return_counts=True) if len(v) else (np.array([]), np.array([0]))
            share = float(np.cov(C[:, j], Sok, bias=True)[0, 1] / var)
            rows.append({"factor": fid, "domain": dom[j], "weight": w[j], "weight_share": w[j] / w.sum(), "variance_share": share,
                         "have": int(have.sum()), "missing_share": float(1 - have.mean()), "mean": float(v.mean()) if len(v) else None, "std": float(v.std()) if len(v) else None,
                         "modal_value": float(vals[cnt.argmax()]) if len(v) else None, "modal_share": float(cnt.max() / len(v)) if len(v) else None,
                         "at_0": float((v <= 0).mean()) if len(v) else None, "at_1": float((v >= 1).mean()) if len(v) else None,
                         "distinct_3dp": int(len(vals)), "rho_with_score": spearman(col, Sok)})
        dshare = collections.defaultdict(float); dweight = collections.defaultdict(float)
        for r in rows:
            dshare[r["domain"]] += r["variance_share"]; dweight[r["domain"]] += r["weight_share"]
        shares = np.array([r["variance_share"] for r in rows])
        pos = np.clip(shares, 0, None); pos = pos / pos.sum()
        # principal components of the weighted factor matrix: how many independent directions
        X = C - C.mean(axis=0)
        ev = np.linalg.eigvalsh(np.cov(X.T, bias=True))[::-1]; ev = np.clip(ev, 0, None)
        p = ev / ev.sum()
        key = f"{market}_{strat}"
        res[key] = {"session": session, "factors_no_stock_has": dropped, "n": int(ok.sum()), "score_mean": float(Sok.mean()), "score_std": float(Sok.std()), "factors": rows,
                    "domain_variance_share": {k: float(v) for k, v in dshare.items()}, "domain_weight_share": {k: float(v) for k, v in dweight.items()},
                    "effective_factors_by_variance_share": float(1 / (pos ** 2).sum()), "effective_factors_by_weight": float(1 / ((w / w.sum()) ** 2).sum()),
                    "pc1_share": float(p[0]), "pc_top3_share": float(p[:3].sum()), "effective_dimensions(1/sum p^2)": float(1 / (p ** 2).sum()),
                    "near_constant(modal>=0.5)": [r["factor"] for r in rows if (r["modal_share"] or 0) >= 0.5],
                    "top3_variance_share": float(sorted(shares, reverse=True)[0] + sorted(shares, reverse=True)[1] + sorted(shares, reverse=True)[2])}
        print(f"\n=== {key} {session} n={ok.sum()} mean {Sok.mean():.1f} sd {Sok.std():.1f}  eff.factors(var) {res[key]['effective_factors_by_variance_share']:.1f} of {len(fids)} (by weight {res[key]['effective_factors_by_weight']:.1f}); PC1 {p[0]:.2f}, top3 {p[:3].sum():.2f}, eff.dim {res[key]['effective_dimensions(1/sum p^2)']:.1f}")
        print("  factors no stock has:", dropped)
        print("  domain var share:", {k: round(float(v), 3) for k, v in dshare.items()}, "| weight share:", {k: round(float(v), 3) for k, v in dweight.items()})
        for r in sorted(rows, key=lambda r: -r["variance_share"]):
            if r["mean"] is None:
                print(f"  {r['factor']:26s} {r['domain'][:5]} w {r['weight']:4.0f} ({r['weight_share']*100:4.1f}%) var {r['variance_share']*100:5.1f}%  NO DATA FOR ANY STOCK (miss 100%)")
                continue
            print(f"  {r['factor']:26s} {r['domain'][:5]} w {r['weight']:4.0f} ({r['weight_share']*100:4.1f}%) var {r['variance_share']*100:5.1f}%  mean {r['mean']:.2f} sd {r['std']:.2f}  modal {r['modal_value']:.2f}@{r['modal_share']*100:3.0f}%  at0 {r['at_0']*100:3.0f}% at1 {r['at_1']*100:3.0f}%  miss {r['missing_share']*100:4.1f}%  rho {r['rho_with_score']:+.2f}")
dump(f"s02_contribution{'_' + SESS if SESS else ''}.json", res)
