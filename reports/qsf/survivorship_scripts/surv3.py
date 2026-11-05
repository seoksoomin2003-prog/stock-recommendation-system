import json,re,time
from pathlib import Path
import requests
from terminal import sources
S=Path('data/qsf/research/survivorship')
res=json.load(open(S/'sec_probe.json')); probe=json.load(open(S/'yahoo_probe.json'))
H={'User-Agent':sources.GENERIC_UA}
api='https://en.wikipedia.org/w/api.php'
m={}
sn=0
for y in range(2013,2027):
  for mo in ('01','04','07','10'):
    ts=f'{y}-{mo}-01T00:00:00Z'
    try:
        r=requests.get(api,params={'action':'query','prop':'revisions','titles':'List of S&P 500 companies','rvlimit':1,'rvdir':'older','rvstart':ts,'rvprop':'content|timestamp','rvslots':'main','format':'json','formatversion':2},headers=H,timeout=40).json()
        rev=r['query']['pages'][0]['revisions'][0]; txt=rev['slots']['main']['content']
    except Exception as e:
        print(ts,type(e).__name__); continue
    sn+=1; n=0
    for row in re.split(r'\n\|-',txt):
        t=re.search(r'\{\{\s*(?:NYSE|NASDAQ|Nasdaq|NyseSymbol|NasdaqSymbol|BZX|Cboe)[^|}]*\|\s*(?:symbol\s*=\s*)?([A-Za-z.\-]+)\s*\}\}',row)
        if not t: 
            t=re.search(r'(?:nyse\.com/quote/[A-Z]+:|nasdaq\.com/[a-z/\-]*/|quote/)([A-Z.\-]{1,6})\b',row)
        c=re.search(r'(?<![\d])(\d{10})(?![\d])',row) or re.search(r'CIK=(\d{4,10})',row)
        if t and c:
            name=re.search(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]',row)
            T=t.group(1).upper().replace('.','-')
            m.setdefault(T,{'cik':str(int(c.group(1))),'name':name.group(1) if name else None,'first':ts[:10]}); m[T]['last']=ts[:10]; n+=1
    print(ts[:7],rev['timestamp'][:10],n,flush=True)
    time.sleep(.3)
json.dump(m,open(S/'wiki_cik.json','w'),ensure_ascii=False)
un=[t for t,v in res.items() if not v.get('cik')]
fixed={t:m[t] for t in un if t in m}
print('snapshots',sn,'tickers',len(m),'unresolved before',len(un),'resolved by wiki',len(fixed)); print('still',[t for t in un if t not in m])
