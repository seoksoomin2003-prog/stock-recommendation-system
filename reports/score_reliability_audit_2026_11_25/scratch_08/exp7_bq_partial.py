"""Agent 8, second pass on Agent 2's "no one-sided bias from partly missing figures" (US long).  No returns.
For stocks whose business_quality has all four figures on 2026-11-24, recompute the factor as it would be with the figure
patterns that actually occur (gross margin absent: 192 stocks; gross and operating margin absent: 104)."""
import sys, json
import numpy as np
sys.path.insert(0, '.'); sys.path.insert(0, 'reports/score_reliability_audit_2026_11_25/scratch_08')
from load import sessions, snaps
from terminal.qsf.factors import ramp
led, ss = sessions()
for market in ('US',):
    sn = [s for s in snaps(led, market, '2026-11-24') if s['strategy'] == 'LONG_TERM' and s.get('score') is not None and s.get('confidence') != 'INSUFFICIENT']
    full, part_g, part_go = [], [], []
    for s in sn:
        f = next((x for x in s['factors'] if x['factor'] == 'business_quality' and x.get('normalized') is not None), None)
        if not f: continue
        r = f['raw']; W = sum(x['weight'] for x in s['factors'] if x.get('weight') and x.get('normalized') is not None)
        vals = {"roe": ramp(r.get('roe'), 0.03, 0.25), "op": ramp(r.get('op_margin'), 0.0, 0.25), "gm": ramp(r.get('gross_margin'), 0.15, 0.60), "st": r.get('roe_years_positive')}
        have = [k for k, v in vals.items() if v is not None]
        if len(have) == 4:
            b4 = np.mean(list(vals.values()))
            assert abs(b4 - f['normalized']) < 1e-9, (s['ticker'], b4, f['normalized'])
            b3 = np.mean([vals['roe'], vals['op'], vals['st']]); b2 = np.mean([vals['roe'], vals['st']])
            full.append((s['ticker'], s['score'], b4, b3, b2, 15 * 100 / W, vals))
        elif set(have) == {"roe", "op", "st"}: part_g.append((s['score'], f['normalized']))
        elif set(have) == {"roe", "st"}: part_go.append((s['score'], f['normalized']))
    a = np.array([(x[2], x[3], x[4], x[5], x[1]) for x in full])
    print(f"{market} long: all four figures {len(full)}; gross margin absent {len(part_g)}; gross and operating margin absent {len(part_go)}")
    print(f" complete stocks: mean factor value  4 figures {a[:,0].mean():.3f} | as if gross absent {a[:,1].mean():.3f} | as if gross+op absent {a[:,2].mean():.3f}")
    d3 = (a[:, 1] - a[:, 0]) * a[:, 3]; d2 = (a[:, 2] - a[:, 0]) * a[:, 3]
    print(f" score change if the SAME stock lost gross margin: mean {d3.mean():+.2f} points, share rising {np.mean(d3>0)*100:.0f}%, 90th pct {np.percentile(d3,90):+.2f}")
    print(f" score change if the SAME stock lost gross and operating margin: mean {d2.mean():+.2f} points, share rising {np.mean(d2>0)*100:.0f}%, 90th pct {np.percentile(d2,90):+.2f}, max {d2.max():+.2f}")
    sc = a[:, 4]
    print(f" complete stocks at 70+: {int((sc>=70).sum())}; with gross+op removed: {int(((sc+d2)>=70).sum())};  with gross removed: {int(((sc+d3)>=70).sum())}")
    st = np.array([x[6]['st'] for x in full]); print(f" 'share of years with positive ROE' among complete stocks: mean {st.mean():.2f}, share at 1.0: {np.mean(st>=0.999)*100:.0f}%")
    for nm, grp in (("complete", [(x[1], x[2]) for x in full]), ("gross absent", part_g), ("gross+op absent", part_go)):
        g = np.array(grp)
        print(f" actual groups - {nm:16s}: n {len(g):3d}  mean business_quality {g[:,1].mean():.3f}  mean score {g[:,0].mean():.1f}  share at 70+ {np.mean(g[:,0]>=70)*100:.0f}%")
