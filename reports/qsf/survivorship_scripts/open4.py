import json,gzip,csv,collections
from pathlib import Path
from utils import runtime_config; runtime_config.load_local_env()
from terminal import sources
from terminal.qsf.validate_pit import RECOVERED, load_history
R=Path('data/qsf/research')
c=json.load(open(R/'survivorship/classified.json')); ser=json.load(gzip.open(R/'open/pystock/series.json.gz','rt'))
keys,snaps=load_history(list(csv.reader(open(R/'survivorship/hist_updated.csv'))))
win=[(k,s) for k,s in zip(keys,snaps) if '2014-01-01'<=k<='2017-03-31']
FIX={'AGN':'1578845','NAVI':'1593538','WBA':'1618921','WRK':'1636023','IGT':'49615','ENDP':'1593034','GGP':'1496048','WPX':'1518832','EVHC':'1678531'}
U={}
for t,s in sorted(ser.items()):
    if t not in c or c[t]['class']=='renamed_in_cache' or t in RECOVERED or not s['rows']: continue
    a,b=s['rows'][0]['date'],s['rows'][-1]['date']
    n=sum(1 for k,sn in win if t in sn and a<=k<=b)
    if not n: continue
    U[t]={'cik':FIX.get(t) or c[t].get('cik'),'first':a,'last':b,'snapshots':n,'exited':b<'2017-03-25'}
print(len(U),'no cik',[t for t,v in U.items() if not v['cik']])
for t in FIX:
    if t not in U: print('fix not in U',t); continue
    s=sources.sec_submissions(U[t]['cik']); print(t,U[t]['cik'],s.get('name'),[f['name'] for f in s.get('formerNames',[])][:2],s.get('tickers'))
for t,v in U.items():
    v['name']=None
    if v['cik']:
        try: v['name']=sources.sec_submissions(v['cik']).get('name')
        except Exception as e: v['name']='ERR '+type(e).__name__
print('errs',[t for t,v in U.items() if (v['name'] or '').startswith('ERR')])
u=json.load(open('data/sp500_universe_cache.json'))
cache={str(int(x)):k.replace('.','-') for k,x in u['ciks'].items()}
rec={str(int(c[t]['cik'])):t for t in RECOVERED if c[t].get('cik')}
print('same cik as cached',[(t,cache[str(int(v['cik']))]) for t,v in U.items() if v['cik'] and str(int(v['cik'])) in cache])
print('same cik as recovered',[(t,rec[str(int(v['cik']))]) for t,v in U.items() if v['cik'] and str(int(v['cik'])) in rec])
dup=collections.defaultdict(list)
for t,v in U.items():
    if v['cik']: dup[str(int(v['cik']))].append(t)
print('dups within',[x for x in dup.values() if len(x)>1])
json.dump(U,open('/tmp/open_u.json','w'),indent=0)
# coverage before any result: share of each snapshot we can price, by year
in_cache=set(u['tickers']); ren={v['ticker']:v['in_cache_as'] for v in c.values() if v.get('in_cache_as')}
agg=collections.defaultdict(lambda:[0,0,0])
for k,s in zip(keys,snaps):
    if not('2014-01-01'<=k<='2017-03-31'): continue
    y=k[:4]
    for t in s:
        a=agg[y]; a[0]+=1; old=ren.get(t,t).replace('.','-') in {x.replace('.','-') for x in in_cache} or t in RECOVERED
        new=t in U and U[t]['first']<=k<=U[t]['last']
        a[1]+=old; a[2]+=(old or new)
print({y:(round(a[1]/a[0],3),round(a[2]/a[0],3)) for y,a in sorted(agg.items())})
