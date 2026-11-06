import sys,json,gzip,pickle
from pathlib import Path
import numpy as np
from terminal.qsf import open_prices as op
base=Path('.'); R=base/'data/qsf/research'
c=json.load(open(R/'survivorship/classified.json'))
from terminal.qsf.validate_pit import RECOVERED
miss=[t for t,v in c.items() if v['class']!='renamed_in_cache' and t not in RECOVERED]
check="AAL AAP GME KSS M VFC MMM JNJ KO XOM AAPL MSFT JPM WMT PG HD CVX PFE T VZ IBM GE NKE V GOOGL".split()
files=op.read_archives(R/'open/pystock/repo.tar.gz',set(miss)|set(check))
print('archives',len(files))
ser={}
for t in set(miss)|set(check):
    f=[{d:r for d,r in b[t].items()} for b in files if t in b]
    if f: ser[t]=op.build_series(f)
json.dump(ser,gzip.open(R/'open/pystock/series.json.gz','wt'))
z=np.load(R/'prices15y_pit.npz',allow_pickle=False); dates=[str(d) for d in z['dates']]; pos={d:i for i,d in enumerate(dates)}; col={str(s):j for j,s in enumerate(z['symbols'])}
split_y=json.load(open(R/'prices15y.splits.json')); split_y.update(json.load(open(R/'prices_recovered.splits.json')))
print('tkr n gaps stop | close ratio spread | daily-ret MAE bp, p99 | adj 3y ret ours/yahoo | vol ratio med | splits ours vs yahoo')
for t in check:
    s=ser.get(t)
    if not s or t not in col: print(t,'none');continue
    j=col[t]; rows=[r for r in s['rows'] if r['date'] in pos and r['date']>='2013-01-01']
    idx=[pos[r['date']] for r in rows]; 
    ours=np.array([r['adj_close'] for r in rows]); y=z['adj_close'][idx,j]; c0=np.array([r['close'] for r in rows]); cy=z['close'][idx,j]; v0=np.array([r['volume'] or np.nan for r in rows]); vy=z['volume'][idx,j]
    ro,ry=np.diff(np.log(ours)),np.diff(np.log(y)); e=np.abs(ro-ry)
    rat=c0/cy
    print(t,len(s['rows']),s['gaps'],s['stopped'],'|',f'{np.nanmin(rat):.4f}-{np.nanmax(rat):.4f}','|',f'{np.nanmean(e)*1e4:.1f} {np.nanpercentile(e,99)*1e4:.0f}','|',f'{ours[-1]/ours[0]:.3f}/{y[-1]/y[0]:.3f}','|',f'{np.nanmedian(v0/vy):.2f} {np.nanmin(v0/vy):.2f}','|',[x for x in s['splits'] if x[0]>='2013'],[x for x in split_y.get(t,[]) if '2013'<=x[0]<'2017-04'])
L=[(t,s) for t,s in ser.items() if t in miss]
print('\nmiss built',len(L),'empty',[t for t,s in L if not s['rows']],'stopped',[(t,s['stopped']) for t,s in L if s['stopped']],'gaps tot',sum(s['gaps'] for _,s in L))
ends=[(s['rows'][-1]['date'],t) for t,s in L if s['rows']]
ex=sorted(x for x in ends if x[0]<'2017-03-25'); print('exited before source end',len(ex)); print([(t,d[:7],c[t]['class'][:6]) for d,t in ex])
print('splits detected',{t:s['splits'] for t,s in L if s['splits']})
