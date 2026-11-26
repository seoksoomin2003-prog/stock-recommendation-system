import json,collections
from pathlib import Path
from terminal.qsf.ledger import Ledger
led=Ledger(Path('.'))
rows=led._live_rows()
def F(s,name): return next((f for f in s['factors'] if f['factor']==name),None)
r=[x for x in rows if x['market']=='US' and x['session']=='2026-11-25'][0]
snaps=led._load(r)
print('input_coverage dist',collections.Counter(round(s.get('input_coverage') or -1,1) for s in snaps))
print('confidence',collections.Counter((s['strategy'],s['confidence']) for s in snaps))
print('held back',collections.Counter((s['strategy'],s.get('band_held_back')) for s in snaps))
for s in snaps:
    for fn in ('balance_sheet','leverage'):
        f=F(s,fn)
        if f and f['status']=='REAL' and isinstance(f['raw'],dict) and f['raw'].get('debt_equity')==0:
            print('DE0',s['ticker'],s['strategy'],fn,json.dumps(f,ensure_ascii=False,default=str)[:330])
    f=F(s,'relative_strength')
    if f and isinstance(f.get('raw'),dict) and f['raw'].get('rel_126')==0: print('REL0',s['ticker'],s['strategy'],json.dumps(f,ensure_ascii=False,default=str)[:300])
    for fn in ('balance_dilution',):
        f=F(s,fn)
        if f and f['status']=='REAL' and f['raw'].get('share_change')==0: print('SC0',s['ticker'],json.dumps(f['raw'],default=str)[:200])
    if any(f['status']=='STALE' for f in s['factors']):
        f=next(f for f in s['factors'] if f['status']=='STALE')
        print('STALE',s['ticker'],s['strategy'],s['score'],s['band'],s['confidence'],s['actionability'],json.dumps({k:f[k] for k in('factor','as_of','normalized','contribution','reason')},ensure_ascii=False))
    if s['strategy']=='SWING' and any(f['status']=='MISSING' and f['domain']=='TECHNICAL' for f in s['factors']):
        print('TECHMISS',s['ticker'],s['score'],s['band'],s['confidence'],s['coverage'],s.get('input_coverage'),[ (f['factor'],f['reason']) for f in s['factors'] if f['status']=='MISSING'])
# 11-18 US data_date != session
r=[x for x in rows if x['market']=='US' and x['session']=='2026-11-18'][0]
for s in led._load(r):
    if s['data_date']!='2026-11-18':
        print('OLDBAR',s['ticker'],s['strategy'],s['data_date'],s['score'],s['band'],s['action'],s['actionability'],s['confidence'],s['recorded_at'],s['entry_session'],s['gates'],s['provenance'].get('price_date'), [ (f['factor'],f['status'],f['as_of']) for f in s['factors'][:3]])
# KR 11-10 partial shard
for x in rows:
    if x['market']=='KR' and x['session']=='2026-11-10':
        ss=led._load(x); print('KR1110',x['file'],len(ss),sorted({s['ticker'] for s in ss})[:6],ss[0]['recorded_at'])
