import json,collections
from pathlib import Path
from terminal.qsf.ledger import Ledger
led=Ledger(Path('.'))
keys=collections.Counter(); st=0; regime=collections.Counter(); ff=collections.Counter()
for r in led._live_rows():
    if r['session']<'2026-11-20': continue
    for s in led._load(r):
        p=s.get('provenance') or {}
        keys.update(p.keys())
        if p.get('stale_inputs') or s.get('stale_inputs'): st+=1
        if s['strategy']=='SWING':
            for k,v in (p.get('regime') or {}).items(): regime[(r['market'],r['session'],k,v)]+=1
            f=p.get('fund_filed')
            if f and f>r['session']: ff['fund_filed_after_session']+=1
            for x in s['factors']:
                if x.get('as_of') and str(x['as_of'])[:10]>r['session']: ff['asof_after_session:'+x['factor']]+=1
print(keys); print('stale_inputs recs',st); print(ff)
for k,v in sorted(regime.items()):
    if k[3]!=k[1]: print(k,v)
