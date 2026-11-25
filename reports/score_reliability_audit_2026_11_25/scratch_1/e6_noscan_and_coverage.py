"""Agent 1, E6 (no return): (1) what the relative-strength fallback would do to the 2026-11-24 scores, approximated with the
recorded rel_126 alone (rel_63 is not in the record); (2) coverage and input-coverage ceilings per profile."""
import sys, json; sys.path.insert(0, '.')
from pathlib import Path
import numpy as np
from terminal.qsf.ledger import Ledger
led = Ledger(Path('.')); rows = led._live_rows()
def ramp(x, lo, hi): return max(0.0, min(1.0, (x - lo) / (hi - lo)))
out = {}
for m in ('US', 'KR'):
    snaps = []
    for r in rows:
        if r['market'] == m and r['session'] == '2026-11-24': snaps += led._load(r)
    for st in ('SWING', 'LONG_TERM'):
        d = []; cross = 0; n = 0
        for s in snaps:
            if s['strategy'] != st or s.get('score') is None: continue
            w = c = 0.0; rs = None
            for f in s['factors']:
                if f.get('scored') is False or f.get('normalized') is None: continue
                w += f['weight']; c += f['weight'] * f['normalized']
                if f['factor'] == 'relative_strength': rs = f
            if rs is None or (rs['raw'] or {}).get('rel_126') is None: continue
            alt = ramp(rs['raw']['rel_126'], -0.15, 0.20)
            new = 100 * (c - rs['weight'] * rs['normalized'] + rs['weight'] * alt) / w
            d.append(new - s['score']); n += 1
            cross += (new >= 70) != (s['score'] >= 70)
        if d:
            d = np.array(d)
            out[f'{m}_{st}'] = {'n': n, 'mean_abs': float(np.abs(d).mean()), 'p95_abs': float(np.percentile(np.abs(d), 95)), 'max_abs': float(np.abs(d).max()), 'mean': float(d.mean()), 'cross_70': int(cross)}
        ic = [s.get('input_coverage') for s in snaps if s['strategy'] == st and s.get('input_coverage') is not None]
        cv = [s.get('coverage') for s in snaps if s['strategy'] == st and s.get('coverage') is not None]
        out[f'{m}_{st}_cov'] = {'max_input_coverage': max(ic) if ic else None, 'median_input_coverage': float(np.median(ic)) if ic else None, 'max_coverage': max(cv), 'median_coverage': float(np.median(cv))}
Path('reports/score_reliability_audit_2026_11_25/scratch_1/e6_noscan_and_coverage.json').write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
