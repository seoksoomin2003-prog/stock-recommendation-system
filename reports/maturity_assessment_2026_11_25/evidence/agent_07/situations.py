"""Read-only: classify the last recorded session's cards into the six situations and run the '사도 돼?' rule (pure function)
on every card under the stored stance.  No provider call, no write, no return or IC figure."""
import sys, json, collections
sys.path.insert(0, '.')
from pathlib import Path
from terminal.qsf.ledger import Ledger
from terminal import assistant as A
from terminal.qsf import stance as qs

market = sys.argv[1]
repo = Path('.').resolve()
led = Ledger(repo)
row = [r for r in led._live_rows() if r["market"] == market][-1]
snaps = led._load(row)
ev = Path('reports/maturity_assessment_2026_11_25/evidence/agent_07')
state = json.load(open(ev / 'big' / f'mstate_{market.lower()}.json'))
level = qs.level(repo, market)
print(market, row['session'], row['model_version'], 'stance', level)

def nz(s, f):
    return next((x.get('normalized') for x in s['factors'] if x['factor'] == f), None)

lt = [s for s in snaps if s['strategy'] == 'LONG_TERM' and s.get('actionability') == 'ACTIONABLE']
sw = [s for s in snaps if s['strategy'] == 'SWING' and s.get('actionability') == 'ACTIONABLE']
print('long actionable', len(lt), 'swing actionable', len(sw))
print('long entry', collections.Counter(s['entry_status'] for s in lt))
print('long band x entry', collections.Counter((s['band'], s['entry_status']) for s in lt))

def show(name, xs):
    print(f'-- {name}: n={len(xs)}', collections.Counter((s['band'], s['entry_status']) for s in xs))
    for s in sorted(xs, key=lambda s: -s['score'])[:6]:
        print('   ', s['ticker'], round(s['score'], 1), s['band'], s['entry_status'],
              'val', nz(s, 'valuation'), 'q', nz(s, 'business_quality'), 'g', nz(s, 'growth_quality'))

r = lambda v: None if v is None else round(v, 2)
show('quality>=0.7 & valuation<0.25 (good but expensive)', [s for s in lt if (nz(s, 'business_quality') or 0) >= 0.7 and nz(s, 'valuation') is not None and nz(s, 'valuation') < 0.25])
show('valuation>=0.7 & growth<=0.3 (cheap, deteriorating shape)', [s for s in lt if (nz(s, 'valuation') or 0) >= 0.7 and nz(s, 'growth_quality') is not None and nz(s, 'growth_quality') <= 0.3])
show('growth>=0.7 & quality>=0.6 & valuation 0.4-0.8 (GARP shape)', [s for s in lt if (nz(s, 'growth_quality') or 0) >= 0.7 and (nz(s, 'business_quality') or 0) >= 0.6 and 0.4 <= (nz(s, 'valuation') or -1) <= 0.8])

# fund-period gaps among buy-band ENTRY_NOW long cards
gap = []
for s in lt:
    fp = s.get('fund_period') or {}
    a, t = (fp.get('annual') or {}).get('score'), (fp.get('trailing') or {}).get('score')
    if a is not None and t is not None and abs(t - a) >= 10 and s['band'] in ('BUY_CANDIDATE', 'STRONG_BUY_CANDIDATE') and s['entry_status'] == 'ENTRY_NOW':
        gap.append((s['ticker'], round(a, 1), round(t, 1)))
print('buy-band ENTRY_NOW long cards whose trailing-4Q score differs by >=10:', len(gap), gap[:10])

# '사도 돼?' rule on every actionable card (marks: none passed; gates from the card; earnings: none)
cnt = collections.Counter()
ok_bands = collections.Counter()
for s in snaps:
    if s.get('score') is None:
        continue
    gates = [g.get('text') or g.get('code') for g in s.get('gates') or []]
    v = A.buy_verdict(s, s['strategy'], market, gates=gates, marks=[], earnings={}, soon=False, level=level, wide=set(), state=state, held=False)
    cnt[(s['strategy'], v['label'])] += 1
    if v['key'] == 'OK':
        ok_bands[(s['strategy'], s['band'])] += 1
print('verdicts', sorted(cnt.items()))
print('OK by band', sorted(ok_bands.items()))
