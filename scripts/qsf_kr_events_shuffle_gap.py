"""After the one Korean filing-event run: 300 shuffles of the signal, where one-day limit breaks fall, and how many held names have no trade on the exit day.  Reads the report only; run from the project folder."""
import sys
from pathlib import Path
ROOT=Path.cwd(); sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"scripts"))
import numpy as np
from collections import Counter
from terminal.qsf import research_kr as kr, research_kr_events as ke, validate
import qsf_kr_events_checks as c
px,rows,_=ke._inputs(ROOT)
with np.load(ROOT/ke.FEATURES) as z: tensor=z["tensor"]
score=ke.score_of(tensor)
rng=np.random.default_rng(1)
for s,h in ke.HORIZONS.items():
    picks=kr.windows(px,rows,h)["test"]
    S,R=[],[]
    for n in picks:
        r,x=px.forward(rows[n],h),score[n].astype(float)
        ok=np.isfinite(r)&np.isfinite(x)
        a,b=validate.rank(x[ok]),validate.rank(r[ok])
        a=(a-a.mean())/a.std(); b=(b-b.mean())/b.std()
        S.append(a);R.append(b)
    real=np.mean([(a*b).mean() for a,b in zip(S,R)])
    means=[]
    for k in range(300):
        means.append(np.mean([(rng.permutation(a)*b).mean() for a,b in zip(S,R)]))
    means=np.array(means)
    print(s,"real",round(real,4),"perm mean",round(means.mean(),5),"sd",round(means.std(),5),"max",round(means.max(),4),"share>=0.0056",float((means>=0.0056).mean()))
clean,count=c.without_limit_breaks(px)
a=px.data["adj_close"].astype(float)
years=Counter(); test=Counter(); elig=0; picksi=set(rows)
for j in np.flatnonzero(count>0):
    have=np.flatnonzero(np.isfinite(a[:,j]))
    step=a[have[1:],j]/a[have[:-1],j]
    bad=(np.diff(have)==1)&(np.abs(step-1)>c.LIMIT)
    for k in have[1:][bad]:
        years[px.dates[k][:4]]+=1
print("break days by year",dict(sorted(years.items())))
big=[]
for j in np.flatnonzero(count>0):
    have=np.flatnonzero(np.isfinite(a[:,j]))
    step=a[have[1:],j]/a[have[:-1],j]
    bad=(np.diff(have)==1)&(np.abs(step-1)>c.LIMIT)
    for k,st in zip(have[1:][bad],step[bad]):
        if px.dates[k]>="2022": big.append((px.dates[k],px.symbols[j],round(float(st-1),3),bool(kr.eligible(px.data,k-1)[j])))
print("since 2022",len(big),"eligible day before",sum(x[3] for x in big)); print(big[:14])
clean,count=c.without_limit_breaks(px)
a=px.data["adj_close"].astype(float); b=clean.data["adj_close"].astype(float)
v=px.data["volume"].astype(float)
for s,h in ke.HORIZONS.items():
    picks=kr.windows(px,rows,h)["test"]
    hit=0; total=0; by={0:0,50:0,100:0}; held={0:0,50:0,100:0}; zero={0:0,50:0,100:0}
    for n in picks:
        i=rows[n]; sc=score[n]
        ok=np.isfinite(sc)
        ra=px.forward(i,h); rb=clean.forward(i,h)
        diff=np.abs(ra-rb)>1e-6
        vol=np.nan_to_num(v[i+1:i+h+1])
        dead=(vol[-1]==0)  # no trade on the exit day although a price is shown or the name is gone
        for t in by:
            m=ok&(sc==t)&np.isfinite(ra)
            held[t]+=m.sum(); by[t]+=(m&diff).sum(); zero[t]+=(m&dead).sum()
    print(s,"held",held,"changed by flatten",by,"no trade on exit day",zero,{t:round(zero[t]/max(1,held[t]),4) for t in zero})
