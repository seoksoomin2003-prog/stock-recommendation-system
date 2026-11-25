"""Agent 1, E7 (no return): rank correlation of each scored factor's normalised value with its profile's score, session 2026-11-24."""
import sys, json; sys.path.insert(0, '.')
from pathlib import Path
import numpy as np
from terminal.qsf.ledger import Ledger
def rank(a):
    order = np.argsort(a, kind='mergesort'); r = np.empty(len(a)); r[order] = np.arange(len(a))
    vals, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    s = np.zeros(len(vals)); np.add.at(s, inv, r); return (s / cnt)[inv]
def sp(a, b): return float(np.corrcoef(rank(a), rank(b))[0, 1])
led = Ledger(Path('.')); rows = led._live_rows(); out = {}
for m in ('US', 'KR'):
    snaps = []
    for r in rows:
        if r['market'] == m and r['session'] == '2026-11-24': snaps += led._load(r)
    for st in ('SWING', 'LONG_TERM'):
        cur = [s for s in snaps if s['strategy'] == st and s.get('score') is not None]
        sc = np.array([s['score'] for s in cur]); res = {}
        for fid in [f['factor'] for f in cur[0]['factors'] if f.get('scored') is not False]:
            v = np.array([next((f['normalized'] if f['normalized'] is not None else np.nan for f in s['factors'] if f['factor'] == fid), np.nan) for s in cur], dtype=float)
            ok = np.isfinite(v)
            if ok.sum() > 30 and np.nanstd(v[ok]) > 0:
                res[fid] = round(sp(v[ok], sc[ok]), 2)
        out[f'{m}_{st}'] = dict(sorted(res.items(), key=lambda x: -abs(x[1])))
Path('reports/score_reliability_audit_2026_11_25/scratch_1/e7_factor_score_rank_corr.json').write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
