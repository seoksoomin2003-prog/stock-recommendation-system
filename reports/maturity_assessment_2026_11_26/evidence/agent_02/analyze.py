"""Cross-sectional description of recorded factor VALUES of one ledger session (no returns, no prices over time)."""
import sys, json
from pathlib import Path
from collections import Counter
import numpy as np
from terminal.qsf.ledger import Ledger
from terminal.qsf import config

def rank(a):
    a = np.asarray(a, float); out = np.full(len(a), np.nan); ok = np.isfinite(a)
    v = a[ok]; order = v.argsort(kind="mergesort"); r = np.empty(len(v)); r[order] = np.arange(len(v))
    # average ties
    uniq, inv = np.unique(v, return_inverse=True)
    sums = np.bincount(inv, r); cnt = np.bincount(inv)
    out[ok] = (sums / cnt)[inv]; return out

def spear(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 30: return np.nan
    a, b = rank(x[ok]), rank(y[ok])
    if a.std() == 0 or b.std() == 0: return np.nan
    return float(np.corrcoef(a, b)[0, 1])

led = Ledger(Path("."))
rows = led._live_rows()
market = sys.argv[1]
rr = [r for r in rows if r["market"] == market]
snaps = led._load(rr[-1])
print("SESSION", rr[-1]["session"], rr[-1]["model_version"], "cards", len(snaps))
for strat in ("SWING", "LONG_TERM"):
    cards = [s for s in snaps if s["strategy"] == strat]
    prof = config.profile_for(market, strat)
    scored = [(d, f, w) for d, fs in prof["domains"].items() for f, w in fs.items()]
    fids = [f for _, f, _ in scored]; W = np.array([w for *_, w in scored], float)
    n = len(cards)
    X = np.full((n, len(fids)), np.nan)
    for i, c in enumerate(cards):
        fm = {r["factor"]: r for r in c["factors"]}
        for j, f in enumerate(fids):
            r = fm.get(f)
            if r and r.get("normalized") is not None and r.get("status") in ("REAL", "STALE"):
                X[i, j] = r["normalized"]
    sc = np.array([c["score"] if c["score"] is not None else np.nan for c in cards], float)
    print(f"\n===== {market} {strat} profile {prof['id']} n={n} scored weight total={W.sum():.0f}")
    q = np.nanpercentile(sc, [0, 5, 25, 50, 75, 90, 95, 99, 100])
    print("score pct 0/5/25/50/75/90/95/99/100:", np.round(q, 1), "mean", round(np.nanmean(sc), 1), "sd", round(np.nanstd(sc), 1))
    print("share >=70: %.3f (n=%d)  >=80: %.3f (n=%d)  <40: %.3f" % ((sc >= 70).mean(), (sc >= 70).sum(), (sc >= 80).mean(), (sc >= 80).sum(), (sc < 40).mean()))
    print("band:", dict(Counter(c["band"] for c in cards)))
    print("action:", dict(Counter(c["action"] for c in cards)), "actionability:", dict(Counter(c["actionability"] for c in cards)))
    print("confidence:", dict(Counter(c["confidence"] for c in cards)))
    print("entry_status all:", dict(Counter(str(c.get("entry_status")) for c in cards)))
    print("entry_status score>=70:", dict(Counter(str(c.get("entry_status")) for c in cards if (c["score"] or 0) >= 70)))
    print("held_back:", sum(bool(c.get("band_held_back")) for c in cards), "deal_held:", sum(bool(c.get("deal_held")) for c in cards))
    print("factor | w | avail | mean | sd | at0 | at1 | mode share | w*sd | rho(score)")
    eff = []
    for j, (d, f, w) in enumerate(scored):
        x = X[:, j]; ok = np.isfinite(x)
        if ok.sum() == 0:
            print(f"{f:26s} {w:3.0f} avail 0.00"); eff.append(0.0); continue
        v = x[ok]; mode = Counter(np.round(v, 3)).most_common(1)[0]
        eff.append(w * v.std())
        print(f"{f:26s} {w:3.0f} {ok.mean():.2f} {v.mean():.2f} {v.std():.2f} {(v<=0).mean():.2f} {(v>=1).mean():.2f} {mode[0]:.3f}:{mode[1]/len(v):.2f} {w*v.std():.2f} {spear(x, sc):+.2f}")
    eff = np.array(eff); print("share of sum(w*sd) by factor (top5):", sorted([(fids[j], round(eff[j] / eff.sum(), 3)) for j in range(len(fids))], key=lambda t: -t[1])[:6])
    # domain share of composite variance: cov(domain points / total avail weight, score)/var(score), approximated with mean-imputed X
    Xi = np.where(np.isfinite(X), X, np.nanmean(X, axis=0, keepdims=True)); Xi = np.where(np.isfinite(Xi), Xi, 0.5)
    comp = Xi @ W
    for d in config.DOMAINS:
        idx = [j for j, (dd, _, _) in enumerate(scored) if dd == d]
        if not idx: continue
        part = Xi[:, idx] @ W[idx]
        print(f"  domain {d:11s} nominal weight share {W[idx].sum()/W.sum():.2f}  variance share {np.cov(part, comp)[0,1]/comp.var(ddof=1):.2f}")
    # correlations among scored factors
    live = [j for j in range(len(fids)) if np.isfinite(X[:, j]).sum() >= 30 and np.nanstd(X[:, j]) > 0]
    C = np.eye(len(live))
    for a in range(len(live)):
        for b in range(a + 1, len(live)):
            C[a, b] = C[b, a] = np.nan_to_num(spear(X[:, live[a]], X[:, live[b]]))
    pairs = sorted([(abs(C[a, b]), fids[live[a]], fids[live[b]], C[a, b]) for a in range(len(live)) for b in range(a + 1, len(live))], reverse=True)
    print("pairs |rho|>=0.5:", [(p[1], p[2], round(p[3], 2)) for p in pairs if p[0] >= 0.5])
    print("most negative pairs:", [(p[1], p[2], round(p[3], 2)) for p in sorted(pairs, key=lambda p: p[3])[:5]])
    ev = np.clip(np.linalg.eigvalsh(C), 0, None)
    print("factors with variation:", len(live), " effective N (participation ratio, unweighted rank corr): %.1f" % (ev.sum() ** 2 / (ev ** 2).sum()),
          " top eigen shares:", np.round(ev[::-1][:5] / ev.sum(), 2))
    # weighted: covariance of contributions
    Z = Xi[:, live] * W[live]; S = np.cov(Z, rowvar=False); ev2 = np.clip(np.linalg.eigvalsh(S), 0, None)
    print("effective N of the weighted composite (participation ratio of contribution covariance): %.1f" % (ev2.sum() ** 2 / (ev2 ** 2).sum()),
          " top eigen shares:", np.round(ev2[::-1][:5] / ev2.sum(), 2))
    np.save(Path(sys.argv[2]) / f"X_{market}_{strat}.npy", X)
    json.dump({"fids": fids, "tickers": [c["ticker"] for c in cards], "score": [None if not np.isfinite(s) else float(s) for s in sc]}, open(Path(sys.argv[2]) / f"meta_{market}_{strat}.json", "w"))
