import json,re,time
from pathlib import Path
import requests
from terminal import sources
S=Path('data/qsf/research/survivorship')
m=json.load(open(S/'wiki_cik.json'))
H={'User-Agent':sources.GENERIC_UA}
api='https://en.wikipedia.org/w/api.php'
for ts in ['2020-01-01','2020-07-01','2021-01-01','2021-07-01','2022-01-01','2022-07-01','2023-01-01','2023-07-01','2024-01-01','2024-07-01','2025-01-01','2025-07-01','2026-01-01','2026-08-01']:
    for k in range(4):
        time.sleep(4+6*k)
        r=requests.get(api,params={'action':'query','prop':'revisions','titles':'List of S&P 500 companies','rvlimit':1,'rvdir':'older','rvstart':ts+'T00:00:00Z','rvprop':'content|timestamp','rvslots':'main','format':'json','formatversion':2},headers=H,timeout=40)
        if r.status_code==200 and r.text[:1]=='{': break
    else:
        print(ts,'fail',r.status_code); continue
    rev=r.json()['query']['pages'][0]['revisions'][0]; txt=rev['slots']['main']['content']; n=0
    for row in re.split(r'\n\|-',txt):
        t=re.search(r'\{\{\s*(?:NYSE|NASDAQ|Nasdaq|NyseSymbol|NasdaqSymbol|BZX|Cboe)[^|}]*\|\s*(?:symbol\s*=\s*)?([A-Za-z.\-]+)\s*\}\}',row) or re.search(r'(?:nyse\.com/quote/[A-Z]+:|nasdaq\.com/[a-z/\-]*/|quote/)([A-Z.\-]{1,6})\b',row)
        c=re.search(r'(?<![\d])(\d{10})(?![\d])',row) or re.search(r'CIK=(\d{4,10})',row)
        if t and c:
            name=re.search(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]',row)
            T=t.group(1).upper().replace('.','-')
            m.setdefault(T,{'cik':str(int(c.group(1))),'name':name.group(1) if name else None,'first':ts}); m[T]['last']=ts; n+=1
    print(ts,rev['timestamp'][:10],n,flush=True)
json.dump(m,open(S/'wiki_cik.json','w'),ensure_ascii=False)
res=json.load(open(S/'sec_probe.json'))
print('tickers',len(m),'still',[t for t,v in res.items() if not v.get('cik') and t not in m])
print('cik mismatch current vs wiki',[(t,v['cik'],m[t]['cik'],m[t]['name']) for t,v in res.items() if v.get('cik') and t in m and str(int(v['cik']))!=m[t]['cik']])
