import json,csv,gzip,collections,time
from pathlib import Path
import numpy as np
from terminal.qsf import validate,validate_pit as vp,validate_open as vo
base=Path('.'); R=base/'data/qsf/research'
u=validate._universe(base); names=vo.load_universe(base)
syms=sorted(set(u['tickers'])|set(vp.RECOVERED)|{'SPY'})
def dl(chunk):
    import yfinance as yf
    return yf.download(chunk,start='2008-06-01',interval='1d',auto_adjust=False,actions=True,progress=False,group_by='column',threads=False)
t0=time.time()
p=validate.download_prices(syms,R/'prices_2008.npz',download=dl,progress=lambda a,b:print(a,b,int(time.time()-t0),flush=True))
print('dates',p['dates'],'failed',p['failed'][:10])
z=np.load(R/'prices_2008.npz',allow_pickle=False); dates=[str(d) for d in z['dates']]; col={str(s):j for j,s in enumerate(z['symbols'])}; close=z['close']
keys,snaps=vp.load_history(list(csv.reader(open(R/'survivorship/hist_updated.csv'))))
import bisect
c=json.load(open(R/'survivorship/classified.json'))
ren={v['ticker']:v['in_cache_as'] for v in c.values() if v.get('in_cache_as')}
ser=json.load(gzip.open(R/'open/pystock/series.json.gz','rt'))
added=json.load(open('data/lab/membership.json'))['added']; added={k.replace('.','-'):v for k,v in added.items()}
print('date members priced_in_groups pending_unknown')
unk=collections.Counter()
for d in ['2010-01-04','2010-07-01','2011-01-03','2011-07-01','2012-01-03','2012-07-02','2013-01-02','2013-07-01','2013-12-02']:
    i=bisect.bisect_left(dates,d); s=snaps[bisect.bisect_right(keys,dates[i])-1]
    have=0;fund=0;miss=[]
    for t in s:
        k=ren.get(t,t)
        if k in col and np.isfinite(close[i,col[k]]): have+=1
        elif t in names and t in ser and ser[t]['rows'] and ser[t]['rows'][0]['date']<=dates[i]: have+=1
        else: miss.append(t); unk[t]+=1
    print(d,len(s),have,round(have/len(s),3),len(miss))
print('never covered',len(unk),' '.join(sorted(unk,key=lambda x:-unk[x]))[:900])
