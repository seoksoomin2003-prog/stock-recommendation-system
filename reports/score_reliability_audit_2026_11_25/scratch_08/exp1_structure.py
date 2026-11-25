"""Agent 8, no-return experiments on the recorded session 2026-11-24 (factor values only).
Q1 variance shares, Q2 redundancy / effective bets, Q4 backward-looking weight, Q5 what the top fifth looks like."""
import sys, json, math
import numpy as np
from pathlib import Path
sys.path.insert(0, '.'); sys.path.insert(0, 'reports/score_reliability_audit_2026_11_25/scratch_08')
from load import sessions, snaps
from rk import spearmanr

SESSION = sys.argv[1] if len(sys.argv) > 1 else '2026-11-24'
led, ss = sessions()
out = {}
for market in ('US', 'KR'):
    sn = snaps(led, market, SESSION)
    for strat in ('SWING', 'LONG_TERM'):
        rows = [s for s in sn if s['strategy'] == strat and s.get('score') is not None and s.get('data_date') == SESSION]
        key = f'{market}_{strat}'
        fids = []
        for s in rows:
            for f in s['factors']:
                if f.get('weight') and f['factor'] not in fids:
                    fids.append(f['factor'])
        W = {}
        N = np.full((len(rows), len(fids)), np.nan)
        for i, s in enumerate(rows):
            for f in s['factors']:
                if f.get('weight') and f.get('normalized') is not None and f.get('status') in ('REAL', 'STALE'):
                    j = fids.index(f['factor']); N[i, j] = f['normalized']; W[f['factor']] = f['weight']
        keepc = [j for j, f in enumerate(fids) if f in W]
        fids = [fids[j] for j in keepc]; N = N[:, keepc]
        w = np.array([W.get(f, 0) for f in fids], float)
        score = np.array([s['score'] for s in rows])
        avail = ~np.isnan(N)
        den = (avail * w).sum(1)
        contrib = np.where(avail, N * w, 0) / den[:, None] * 100       # contribution of each factor to the composite
        recon = contrib.sum(1)
        assert np.allclose(recon, score, atol=1e-6), (key, np.abs(recon - score).max())
        var = score.var()
        share = [(fids[j], float(np.cov(contrib[:, j], score, bias=True)[0, 1] / var), float(w[j]), float(np.nanstd(N[:, j])),
                  float(spearmanr(np.nan_to_num(N[:, j], nan=np.nanmean(N[:, j])), score)[0]) if np.nanstd(N[:, j]) > 0 else None,
                  int(avail[:, j].sum())) for j in range(len(fids))]
        share.sort(key=lambda x: -x[1])
        # the baseline effect of a varying denominator is in the shares already (they sum to 1)
        # redundancy: Spearman between factors (pairwise complete)
        nf = len(fids)
        C = np.eye(nf)
        for a in range(nf):
            for b in range(a + 1, nf):
                m = avail[:, a] & avail[:, b]
                if m.sum() > 30 and np.std(N[m, a]) > 0 and np.std(N[m, b]) > 0:
                    C[a, b] = C[b, a] = spearmanr(N[m, a], N[m, b])[0]
                else:
                    C[a, b] = C[b, a] = 0
        pairs = sorted([(abs(C[a, b]), fids[a], fids[b], float(C[a, b])) for a in range(nf) for b in range(a + 1, nf)], reverse=True)
        # effective number of bets: participation ratio of eigenvalues of the weighted-contribution covariance
        Nf = np.where(avail, N, np.nanmean(N, 0)[None, :])
        Cw = np.cov((Nf * w).T)
        ev = np.clip(np.linalg.eigvalsh(Cw), 0, None)[::-1]
        enb = float(ev.sum() ** 2 / (ev ** 2).sum())
        ev_c = np.clip(np.linalg.eigvalsh(np.corrcoef(Nf.T[np.nanstd(Nf, 0) > 1e-9])), 0, None)[::-1]
        enb_unw = float(ev_c.sum() ** 2 / (ev_c ** 2).sum())
        out[key] = {"n": len(rows), "factors": nf, "weights_sum": float(w.sum()), "score_mean": float(score.mean()), "score_sd": float(score.std()),
                    "n70": int((score >= 70).sum()), "n80": int((score >= 80).sum()), "n55_70": int(((score >= 55) & (score < 70)).sum()),
                    "share": share, "top3_share": float(sum(x[1] for x in share[:3])), "top5_share": float(sum(x[1] for x in share[:5])),
                    "pairs_over_0.5": [(p[1], p[2], round(p[3], 2)) for p in pairs if p[0] >= 0.5],
                    "pairs_over_0.7": sum(1 for p in pairs if p[0] >= 0.7),
                    "pc1_share_weighted": float(ev[0] / ev.sum()), "pc3_share_weighted": float(ev[:3].sum() / ev.sum()),
                    "effective_bets_weighted": enb, "effective_bets_equal": enb_unw}
        print(f"\n=== {key} n={len(rows)} factors={nf} score mean {score.mean():.1f} sd {score.std():.1f}  >=70: {(score>=70).sum()}  >=80: {(score>=80).sum()}")
        print("factor | weight | variance share | sd(normalized) | spearman(factor, score) | n with data")
        for f, sh, wt, sd, rho, n in share:
            print(f"  {f:26s} {wt:4.0f} {sh*100:6.1f}%  sd {sd:.2f}  rho {rho if rho is None else round(rho,2)}  n {n}")
        print(f"top3 {out[key]['top3_share']*100:.0f}%  top5 {out[key]['top5_share']*100:.0f}%  PC1 {out[key]['pc1_share_weighted']*100:.0f}%  PC1-3 {out[key]['pc3_share_weighted']*100:.0f}%  eff.bets weighted {enb:.1f} / equal {enb_unw:.1f} of {nf}")
        print("pairs |rho|>=0.5:", out[key]["pairs_over_0.5"])
json.dump(out, open(f'reports/score_reliability_audit_2026_11_25/scratch_08/exp1_{SESSION}.json', 'w'), ensure_ascii=False, indent=1)
