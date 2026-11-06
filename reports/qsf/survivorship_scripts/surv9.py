import json,csv,collections
from pathlib import Path
S=Path('data/qsf/research/survivorship')
c=json.load(open(S/'classified.json'))
hist=[]
for row in list(csv.reader(open(S/'hist_updated.csv')))[1:]:
    if row[0]>='2014-01-01': hist.append(set(x.strip().replace('.','-') for x in ','.join(row[1:]).strip('"').split(',')))
cnt=collections.Counter(t for h in hist for t in h)
L=[v for v in c.values() if v['class']!='renamed_in_cache' and v['yahoo_cov']>=.95 and not v['ticker_recycled']]
print(len(L),len(hist))
for v in sorted(L,key=lambda x:x['ticker']):
    print(v['ticker'],'|',(v['wiki_name'] or '-')[:26],'|',(v.get('sec_name') or '-')[:26],'|',v['member_first'][:7],v['member_last'][:7],cnt[v['ticker']],'|',v['cik_via'][:4],v['cik'],'|F' if v.get('facts') else '|-',v.get('fact_years'),v.get('span_years'))
print('renames:',{v['ticker']:v['in_cache_as'] for v in c.values() if v.get('in_cache_as')})
