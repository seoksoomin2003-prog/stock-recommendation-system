import json,csv,collections,re
from pathlib import Path
import numpy as np
S=Path('data/qsf/research/survivorship')
c=json.load(open(S/'classified.json'))
print('cik_via',collections.Counter(v['cik_via'] for v in c.values()))
print('via current, no wiki check',[(v['ticker'],(v.get('sec_name') or '')[:22],v['member_first'][:4],v['member_last'][:4],v['yahoo_cov']) for v in c.values() if v['cik_via']=='current_ticker'])
def toks(s): return set(w for w in re.findall(r'[a-z]+',(s or '').lower()) if w not in('inc','corp','co','the','company','corporation','ltd','plc','group','holdings','of','and','de','new','limited'))
print('\nname mismatch wiki vs sec',[(v['ticker'],v['wiki_name'],(v.get('sec_name') or '')[:28],v['class']) for v in c.values() if v['cik_via']=='wiki' and v.get('sec_name') and not toks(v['wiki_name'])&toks(v['sec_name'])])
print('\nbankrupt detail',[(v['ticker'],v['b103'],v['yahoo_cov'],v['tiingo'],v.get('facts'),v.get('fact_years'),v.get('span_years')) for v in c.values() if v['class']=='bankruptcy_8k'])
print('facts err',[v['ticker'] for v in c.values() if v.get('facts_err')])
# non-member share of the cache at each year-end
z=np.load('data/qsf/research/prices15y.npz',allow_pickle=False); dates=[str(d) for d in z['dates']]; syms=[str(s) for s in z['symbols']]; close=z['close'] if 'close' in z else z[z.files[2]]
rows=list(csv.reader(open(S/'hist_updated.csv')))[1:]
last={}
for d,*rest in rows:
    if d>='2014-01-01': last[d[:4]]=(d,set(x.strip().replace('.','-') for x in ','.join(rest).strip('"').split(',') if x.strip()))
ren={v['ticker']:v['in_cache_as'] for v in c.values() if v.get('in_cache_as')}
print('\nyear cache_with_price members cache_nonmember_share')
for y,(d,mem) in sorted(last.items()):
    i=max(k for k,x in enumerate(dates) if x<=d)
    have=set(s for j,s in enumerate(syms) if np.isfinite(close[i,j]))
    m2=set(ren.get(t,t) for t in mem)
    print(y,d,len(have),len(mem),f'{len(have-m2)/len(have):.3f}')
