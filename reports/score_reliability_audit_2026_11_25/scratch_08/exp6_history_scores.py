"""Agent 8: stored scores of the current formula on the historical dates (scores only; no price or return is read).
Sector make-up of the top fifth over time, how many stocks stand at 70+ by year, turnover of the top fifth between evaluation days."""
import gzip, json, sys
import numpy as np
from collections import defaultdict
d = json.load(gzip.open('data/qsf/research/scores_current_us.json.gz', 'rt'))
print(type(d).__name__, (list(d.keys()) if isinstance(d, dict) else (len(d), d[0])))
recs = d if isinstance(d, list) else d.get('records') or d.get('scores')
days = defaultdict(list)
for r in recs: days[r['i']].append(r)
keys = sorted(days)
print("evaluation days", len(keys), "rows", len(recs))
dates = None
if isinstance(d, dict):
    for k in d:
        if k not in ('records', 'scores'): print(k, str(d[k])[:200])
for strat in ('SWING', 'LONG_TERM'):
    lift = defaultdict(list); n70 = []; turn = []; prev = None; share_top = defaultdict(list)
    for k in keys:
        rows = [r for r in days[k] if r.get(strat) is not None]
        if len(rows) < 100: continue
        sc = np.array([r[strat] for r in rows]); kk = len(rows) // 5
        order = np.argsort(-sc); top = [rows[i] for i in order[:kk]]
        n70.append((k, float((sc >= 70).mean()), float(np.median(sc))))
        secs = defaultdict(int); tsec = defaultdict(int)
        for r in rows: secs[r.get('sector')] += 1
        for r in top: tsec[r.get('sector')] += 1
        for s in secs:
            lift[s].append((tsec[s] / kk) / (secs[s] / len(rows))); share_top[s].append(tsec[s] / kk)
        cur = {r['t'] for r in top}
        if prev is not None: turn.append(len(cur - prev) / len(cur))
        prev = cur
    print(f"\n=== US {strat}: evaluation days used {len(n70)}")
    print(" mean share of top fifth replaced between evaluation days (21 sessions apart):", round(float(np.mean(turn)) * 100, 1), "%")
    sh = np.array([x[1] for x in n70]); md = np.array([x[2] for x in n70])
    print(f" share of scored stocks at 70+: mean {sh.mean()*100:.1f}%, min {sh.min()*100:.1f}%, max {sh.max()*100:.1f}%;  days with under 2%: {(sh<0.02).sum()}, over 25%: {(sh>0.25).sum()};  median score: min {md.min():.1f} max {md.max():.1f}")
    # by sixths of the period
    for part in np.array_split(np.arange(len(n70)), 6):
        print(f"   days {part[0]:3d}-{part[-1]:3d}: 70+ share {sh[part].mean()*100:5.1f}%  median score {md[part].mean():.1f}")
    print(" sector: mean lift in top fifth (1 = universe share) | mean share of top fifth | share of days with lift > 1")
    for s in sorted(lift, key=lambda x: -np.mean(lift[x])):
        if len(lift[s]) > 50: print(f"   {str(s):26s} x{np.mean(lift[s]):.2f}   {np.mean(share_top[s])*100:5.1f}%   {np.mean(np.array(lift[s])>1)*100:4.0f}%")
