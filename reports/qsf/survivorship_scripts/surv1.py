import csv,json,time,logging,warnings
from pathlib import Path
import numpy as np,pandas as pd,yfinance as yf
warnings.filterwarnings('ignore'); logging.getLogger('yfinance').setLevel(logging.CRITICAL)
S=Path('data/qsf/research/survivorship')
rows=list(csv.reader(open(S/'hist_updated.csv')))[1:]
hist=[(r[0],set(t.strip().upper().replace('.','-') for t in r[1].split(','))) for r in rows if r[0]>='2014-01-01']
cur={t.upper().replace('.','-') for t in json.load(open('data/sp500_universe_cache.json'))['tickers']}
gone=sorted(set().union(*[s for d,s in hist])-cur)
print(len(gone))
# membership windows: first/last snapshot within 2014+
win={t:[d for d,s in hist if t in s] for t in gone}
spy=yf.download(['SPY'],period='15y',auto_adjust=False,progress=False,threads=False)
sess=[d.strftime('%Y-%m-%d') for d in spy.index]; 
out={}
t0=time.time()
for k in range(0,len(gone),40):
    ch=gone[k:k+40]
    f=yf.download(ch,period='max',interval='1d',auto_adjust=False,actions=True,progress=False,group_by='column',threads=False)
    for t in ch:
        try: c=f['Close'][t].dropna()
        except Exception: c=pd.Series(dtype=float)
        ds=set(x.strftime('%Y-%m-%d') for x in c.index)
        a,b=win[t][0],win[t][-1]
        need=[d for d in sess if a<=d<=b and any(True for _ in [0])]
        cov=sum(d in ds for d in need)/len(need) if need else 0
        # also pre-history available for 320 bars before start?
        out[t]={'member_first':a,'member_last':b,'bars':len(c),'first':min(ds) if ds else None,'last':max(ds) if ds else None,'cov':round(cov,3),
                'close_at_last':float(c[c.index<=b].iloc[-1]) if len(c[c.index<=b]) else None,'last_close':float(c.iloc[-1]) if len(c) else None}
    print(k,round(time.time()-t0),flush=True)
json.dump(out,open(S/'yahoo_probe.json','w'),indent=0)
v=list(out.values())
print('total',len(v),'cov>=.95',sum(x['cov']>=.95 for x in v),'.5-.95',sum(.5<=x['cov']<.95 for x in v),'0-.5',sum(0<x['cov']<.5 for x in v),'none',sum(x['cov']==0 for x in v))
print('live now',sum(1 for x in v if x['last'] and x['last']>='2026-10-01'))
print('NONE',[t for t,x in out.items() if x['cov']==0][:80])
print('LOWCOV',[(t,x['cov'],x['first'],x['last'],x['member_first'],x['member_last']) for t,x in out.items() if 0<x['cov']<.95][:40])
print('sample ok',[(t,x['member_last'],x['last']) for t,x in out.items() if x['cov']>=.95][:40])
