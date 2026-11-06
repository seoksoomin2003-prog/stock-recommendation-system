import json,gzip,csv
from pathlib import Path
R=Path('data/qsf/research')
c=json.load(open(R/'survivorship/classified.json')); ser=json.load(gzip.open(R/'open/pystock/series.json.gz','rt'))
from terminal.qsf.validate_pit import RECOVERED, load_history
keys,snaps=load_history(list(csv.reader(open(R/'survivorship/hist_updated.csv'))))
win=[(k,s) for k,s in zip(keys,snaps) if '2014-01-01'<=k<='2017-03-31']
print(len(win))
L=[]
for t,s in sorted(ser.items()):
    if t not in c or c[t]['class']=='renamed_in_cache' or t in RECOVERED or not s['rows']: continue
    a,b=s['rows'][0]['date'],s['rows'][-1]['date']
    n=sum(1 for k,sn in win if t in sn and a<=k<=b)
    if not n: L.append((t,'NO')); continue
    v=c[t]; print(t,'|',(v.get('wiki_name') or '-')[:24],'|',(v.get('sec_name') or '-')[:24],'|',v.get('cik'),v.get('cik_via') and v['cik_via'][:1],'|',a[:7],b[:7],n,'|',v['class'][:5],'F' if v.get('facts') else '-',v.get('fact_years'),'R' if v.get('ticker_recycled') else '')
print('no window',[t for t,_ in L])
