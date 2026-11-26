import json,sys,collections,gc
from pathlib import Path
from datetime import date
from terminal.qsf.ledger import Ledger
led=Ledger(Path('.'))
rows=led._live_rows()
want=sys.argv[1:] or ['2026-11-25']
def age(a,s):
    try: return (date.fromisoformat(s)-date.fromisoformat(str(a)[:10])).days
    except Exception: return None
for r in rows:
    if r['session'] not in want: continue
    snaps=led._load(r)
    st=collections.Counter(); anomalies=collections.Counter(); ex={}
    ages=collections.defaultdict(list)
    zero_raw=collections.Counter()
    for s in snaps:
        if s.get('price') in (None,0): anomalies['price_none_or_0']+=1
        if s.get('score') is None: anomalies['score_none']+=1
        for f in s['factors']:
            k=(f['factor'],f['status']); st[k]+=1
            if f['status']!='REAL' and f['status']!='STALE' and (f.get('normalized') is not None or (f.get('contribution') not in (None,))):
                if f.get('contribution') not in (None,0,0.0) or f.get('normalized') is not None:
                    anomalies['nonreal_with_value:'+f['factor']+':'+str(f['status'])]+=1; ex.setdefault('nonreal_with_value:'+f['factor'],(s['ticker'],s['strategy'],f))
                elif f.get('contribution') in (0,0.0):
                    anomalies['nonreal_contrib_zero:'+f['factor']+':'+str(f['status'])]+=1; ex.setdefault('nonreal_zero:'+f['factor'],(s['ticker'],s['strategy'],f))
            if f['status']=='REAL':
                if f.get('normalized') is None: anomalies['real_without_norm:'+f['factor']]+=1
                a=age(f.get('as_of'),r['session'])
                if a is None: anomalies['real_no_asof:'+f['factor']]+=1
                else: ages[f['factor']].append(a)
                raw=f.get('raw')
                if isinstance(raw,dict):
                    for kk,v in raw.items():
                        if v==0 and not isinstance(v,bool): zero_raw[f['factor']+'.'+kk]+=1
                        if v is None: anomalies['real_raw_none:'+f['factor']+'.'+kk]+=1
    print('=====',r['market'],r['session'],len(snaps))
    byf=collections.defaultdict(dict)
    for (f,s_),n in st.items(): byf[f][s_]=n
    for f,d in byf.items():
        a=sorted(ages.get(f,[]))
        print(f'{f:28s}',d,'age(days) med/max/neg:',(a[len(a)//2],a[-1],sum(1 for x in a if x<0)) if a else None)
    print('ANOM',dict(anomalies))
    for k,v in ex.items(): print('EX',k,json.dumps(v,ensure_ascii=False,default=str)[:400])
    print('ZERO_RAW',dict(zero_raw))
    del snaps; gc.collect()
