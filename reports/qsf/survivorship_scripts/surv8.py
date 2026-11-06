import gzip,json,csv,collections
from pathlib import Path
S=Path('data/qsf/research/survivorship')
d=json.load(gzip.open('data/qsf/research/scores.json.gz','rt'))
dates=d['dates']; by=collections.defaultdict(set)
for r in d['records']: by[r['i']].add(r['t'])
c=json.load(open(S/'classified.json'))
ren={v['ticker']:v['in_cache_as'] for v in c.values() if v.get('in_cache_as')}
hist=[]
for row in list(csv.reader(open(S/'hist_updated.csv')))[1:]:
    hist.append((row[0],set(x.strip().replace('.','-') for x in ','.join(row[1:]).strip('"').split(',') if x.strip())))
hist.sort(key=lambda x:x[0])
import bisect
keys=[h[0] for h in hist]
agg=collections.defaultdict(lambda:[0,0,0,0])
for i,names in sorted(by.items()):
    day=dates[i]; mem=hist[bisect.bisect_right(keys,day)-1][1]
    m2=set(ren.get(t,t) for t in mem)
    a=agg[day[:4]]; a[0]+=1; a[1]+=len(names); a[2]+=len(names-m2); a[3]+=len(mem)
print('year dates scored_avg scored_nonmember_share scored/members')
T=[0,0,0,0]
for y,a in sorted(agg.items()):
    T=[p+q for p,q in zip(T,a)]
    print(y,a[0],round(a[1]/a[0]),f'{a[2]/a[1]:.3f}',f'{(a[1]-a[2])/a[3]:.3f}')
print('all',T[0],T[1],f'{T[2]/T[1]:.3f}',f'{(T[1]-T[2])/T[3]:.3f}')
