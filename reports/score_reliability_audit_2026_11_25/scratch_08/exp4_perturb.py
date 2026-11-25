"""Agent 8, Q10/Q13: (a) jitter the weights and the normalized inputs on the recorded day 2026-11-24 (random numbers, seed 8;
weights x U(0.8,1.2) [+-20%] or x U(0.5,1.5) [+-50%]; inputs + N(0, 0.05) clipped to 0..1), 500 draws each;
(b) day-to-day movement of the recorded scores over the 15 recorded sessions.  No returns."""
import sys, json
import numpy as np
sys.path.insert(0, '.'); sys.path.insert(0, 'reports/score_reliability_audit_2026_11_25/scratch_08')
from load import sessions, snaps
from rk import spearmanr
rng = np.random.default_rng(8)
led, ss = sessions()
SESSION = '2026-11-24'
def matrix(rows):
    fids = []
    for s in rows:
        for f in s['factors']:
            if f.get('weight') and f['factor'] not in fids: fids.append(f['factor'])
    N = np.full((len(rows), len(fids)), np.nan); w = np.zeros(len(fids))
    for i, s in enumerate(rows):
        for f in s['factors']:
            if f.get('weight') and f.get('normalized') is not None and f.get('status') in ('REAL', 'STALE'):
                j = fids.index(f['factor']); N[i, j] = f['normalized']; w[j] = f['weight']
    return fids, N, w
def comp(N, w):
    a = ~np.isnan(N)
    return 100 * (np.where(a, N, 0) * w).sum(1) / (a * w).sum(1)
print("(a) perturbation on", SESSION)
for market in ('US', 'KR'):
    sn = snaps(led, market, SESSION)
    for strat in ('SWING', 'LONG_TERM'):
        rows = [s for s in sn if s['strategy'] == strat and s.get('score') is not None and s.get('confidence') != 'INSUFFICIENT']
        fids, N, w = matrix(rows); base = comp(N, w); n = len(rows); k = n // 5
        top = set(np.argsort(-base)[:k]); top10 = set(np.argsort(-base)[:10]); b70 = set(np.where(base >= 70)[0]); b55 = set(np.where((base >= 55))[0])
        res = {}
        for name, fn in {"weights +-20%": lambda: comp(N, w * rng.uniform(0.8, 1.2, len(w))),
                         "weights +-50%": lambda: comp(N, w * rng.uniform(0.5, 1.5, len(w))),
                         "equal weights": None,
                         "inputs sd 0.05": lambda: comp(np.clip(N + rng.normal(0, 0.05, N.shape), 0, 1), w),
                         "inputs sd 0.10": lambda: comp(np.clip(N + rng.normal(0, 0.10, N.shape), 0, 1), w)}.items():
            draws = [comp(N, (w > 0) * 1.0)] if fn is None else [fn() for _ in range(500)]
            rho = np.mean([spearmanr(base, d)[0] for d in draws[:100]])
            ov = np.mean([len(top & set(np.argsort(-d)[:k])) / k for d in draws])
            ov10 = np.mean([len(top10 & set(np.argsort(-d)[:10])) / 10 for d in draws])
            j70 = np.mean([len(b70 & set(np.where(d >= 70)[0])) / max(1, len(b70 | set(np.where(d >= 70)[0]))) for d in draws])
            n70 = (np.mean([(d >= 70).sum() for d in draws]), np.min([(d >= 70).sum() for d in draws]), np.max([(d >= 70).sum() for d in draws]))
            sd = np.mean([np.std(d - base) for d in draws])
            res[name] = (rho, ov, ov10, j70, n70, sd)
        print(f"\n=== {market} {strat} n={n}; >=70 on record: {len(b70)}")
        for name, (rho, ov, ov10, j70, n70, sd) in res.items():
            print(f"  {name:16s} spearman {rho:.3f}  top-fifth kept {ov*100:5.1f}%  top-10 kept {ov10*100:5.1f}%  '>=70' set overlap(Jaccard) {j70*100:5.1f}%  count>=70 mean {n70[0]:.0f} [{n70[1]}..{n70[2]}]  sd of score change {sd:.2f}")
        # how many stocks lie within 1, 2, 3 points of a line
        for line in (55, 70, 80):
            print(f"   within +-1 of {line}: {(np.abs(base-line)<1).sum()}, +-2: {(np.abs(base-line)<2).sum()}, +-3: {(np.abs(base-line)<3).sum()}")
print("\n(b) recorded day-to-day movement, 15 sessions")
for market in ('US', 'KR'):
    days = ss[market]
    data = {}
    for d in days:
        for s in snaps(led, market, d):
            if s.get('score') is not None and s.get('confidence') != 'INSUFFICIENT' and s.get('data_date') == d:
                data.setdefault(s['strategy'], {}).setdefault(d, {})[s['ticker']] = (s['score'], s.get('band'), s.get('model_version'), s.get('entry_status'))
    for strat in ('SWING', 'LONG_TERM'):
        dd = data[strat]; print(f"\n=== {market} {strat}; versions by day:", sorted({(d, next(iter(v.values()))[2]) for d, v in dd.items()})[0::1][:0] or sorted({v2[2] for v in dd.values() for v2 in v.values()}))
        diffs, turn, flips, rhos, same_ver = [], [], [], [], []
        for a, b in zip(days[:-1], days[1:]):
            if a not in dd or b not in dd: continue
            common = [t for t in dd[a] if t in dd[b]]
            x = np.array([dd[a][t][0] for t in common]); y = np.array([dd[b][t][0] for t in common])
            va = {dd[a][t][2] for t in common}; vb = {dd[b][t][2] for t in common}
            k = len(common) // 5
            ta = set(np.array(common)[np.argsort(-x)[:k]]); tb = set(np.array(common)[np.argsort(-y)[:k]])
            fl = sum(1 for t in common if (dd[a][t][0] >= 70) != (dd[b][t][0] >= 70)); n70 = sum(1 for t in common if dd[a][t][0] >= 70)
            ea = {t for t in common if dd[a][t][3] == 'ENTRY_NOW'}; eb = {t for t in common if dd[b][t][3] == 'ENTRY_NOW'}
            print(f"  {a}->{b} ver {','.join(sorted(va))}->{','.join(sorted(vb))}: sd(dscore) {np.std(y-x):.2f}  mean |d| {np.mean(np.abs(y-x)):.2f}  spearman {spearmanr(x,y)[0]:.3f}  top-fifth replaced {len(ta-tb)/k*100:4.1f}%  crossed 70: {fl} (>=70 before: {n70})  ENTRY_NOW {len(ea)}->{len(eb)}, kept {len(ea&eb)}")
            if va == vb:
                diffs.append(np.std(y - x)); turn.append(len(ta - tb) / k); rhos.append(spearmanr(x, y)[0])
        if diffs: print(f"  same-version pairs: median sd of one-day score change {np.median(diffs):.2f}, median one-day top-fifth replacement {np.median(turn)*100:.1f}%")
        # first vs last recorded day
        a, b = days[0], days[-1]
        common = [t for t in dd[a] if t in dd[b]]; x = np.array([dd[a][t][0] for t in common]); y = np.array([dd[b][t][0] for t in common]); k = len(common)//5
        ta = set(np.array(common)[np.argsort(-x)[:k]]); tb = set(np.array(common)[np.argsort(-y)[:k]])
        print(f"  {a} vs {b} (14 sessions, versions differ): spearman {spearmanr(x,y)[0]:.3f}, top-fifth replaced {len(ta-tb)/k*100:.0f}%, sd(dscore) {np.std(y-x):.2f}")
