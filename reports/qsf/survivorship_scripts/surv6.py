import json,csv,collections
from pathlib import Path
import numpy as np
S=Path('data/qsf/research/survivorship')
c=json.load(open(S/'classified.json'))
print('total',len(c),collections.Counter(v['class'] for v in c.values()))
for k in ['renamed_in_cache','bankruptcy_8k','acquired_8k','deregistered','still_public','unknown','no_cik']:
    L=[v for v in c.values() if v['class']==k]
    print('\n',k,len(L),[ (v['ticker'],v.get('in_cache_as') or (v.get('sec_name') or '')[:18]) for v in L][:30])
print('\nrecycled',[ (v['ticker'],v['yahoo_cov'],v['tiingo']) for v in c.values() if v['ticker_recycled']])
# usable tiers, excl renamed
ex=[v for v in c.values() if v['class']!='renamed_in_cache']
def yahoo_ok(v): return v['yahoo_cov']>=.95 and not v['ticker_recycled']
def tiingo_ok(v): return v['tiingo'] and not v['ticker_recycled']
def fund_ok(v): return bool(v.get('facts') and v.get('has_rev') and v.get('has_ni') and v.get('has_eq') and v.get('fact_years',0)>=max(1,v.get('span_years',1)-1))
print('\nexcl renamed',len(ex),'yahoo ok',sum(map(yahoo_ok,ex)),'tiingo ok',sum(map(tiingo_ok,ex)),'either',sum(yahoo_ok(v) or tiingo_ok(v) for v in ex),'facts ok',sum(map(fund_ok,ex)),'facts any',sum(bool(v.get('facts')) for v in ex),'errs',collections.Counter(v.get('facts_err') for v in ex))
print('both y+f',sum(yahoo_ok(v) and fund_ok(v) for v in ex),'both any+f',sum((yahoo_ok(v) or tiingo_ok(v)) and fund_ok(v) for v in ex))
t=collections.defaultdict(lambda:[0,0,0,0])
for v in ex:
    r=t[v['class']]; r[0]+=1; r[1]+=yahoo_ok(v); r[2]+=(yahoo_ok(v) or tiingo_ok(v)); r[3]+=(yahoo_ok(v) or tiingo_ok(v)) and fund_ok(v)
print('class n yahoo y+t y+t+facts',dict(t))
# member-date shares, monthly
rows=list(csv.reader(open(S/'hist_updated.csv'))); hdr=rows[0]; rows=rows[1:]
syms=set(str(s) for s in np.load('data/qsf/research/prices15y.npz',allow_pickle=False)['symbols'])
last={}
for d,*rest in rows:
    if d>='2014-01-01': last[d[:7]]=(d,[x.strip().replace('.','-') for x in ','.join(rest).strip('"').split(',') if x.strip()])
agg=collections.defaultdict(lambda:[0,0,0,0,0])
for m,(d,tk) in last.items():
    a=agg[m[:4]]
    for x in tk:
        a[0]+=1; v=c.get(x)
        if v is None:
            a[1]+=1;a[2]+=1;a[3]+=1;a[4]+=1
        elif v['class']=='renamed_in_cache' :
            a[1]+=1;a[2]+=1;a[3]+=1;a[4]+=1
        else:
            y=yahoo_ok(v); e=y or tiingo_ok(v)
            a[2]+=y; a[3]+=e; a[4]+=e and fund_ok(v)
print('year memberMonths cache cache+yahoo +tiingo +tiingo&facts')
tot=[0]*5
for y in sorted(agg):
    a=agg[y]; tot=[p+q for p,q in zip(tot,a)]
    print(y,a[0],*[f'{z/a[0]:.3f}' for z in a[1:]])
print('all',tot[0],*[f'{z/tot[0]:.3f}' for z in tot[1:]])
print('\nodd',[(k,{q:c[k].get(q) for q in ('class','cik','in_cache_as','yahoo_cov','tiingo','sec_name','now_tickers')}) for k in ('BK','AVB','EA','EQR','MMC','FI') if k in c])
