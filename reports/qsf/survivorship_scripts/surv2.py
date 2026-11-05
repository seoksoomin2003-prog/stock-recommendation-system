import io,json,re,zipfile,time,csv
from pathlib import Path
import requests,pandas as pd
from utils import runtime_config; runtime_config.load_local_env()
from terminal import sources
S=Path('data/qsf/research/survivorship')
probe=json.load(open(S/'yahoo_probe.json'))
none=[t for t,x in probe.items() if x['cov']<.95]
# Tiingo public list (no key)
r=requests.get('https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip',timeout=120,headers={'User-Agent':sources.GENERIC_UA})
print('tiingo zip',r.status_code,len(r.content))
z=zipfile.ZipFile(io.BytesIO(r.content)); name=z.namelist()[0]; df=pd.read_csv(z.open(name),keep_default_na=False,dtype=str); print(name,df.shape,df.columns.tolist())
us=df[df.exchange.isin(['NYSE','NASDAQ','AMEX','NYSE ARCA','NYSE MKT','PINK','OTC','ARCX','BATS'])|(df.priceCurrency=='USD')]
us=us[us.assetType.isin(['Stock',''])] if 'assetType' in us else us
us=us.assign(T=us.ticker.str.upper().str.replace('.','-',regex=False))
got={}
for t in none:
    m=us[us['T']==t]
    if len(m):
        a=probe[t]['member_first'];b=probe[t]['member_last']
        ok=m[(m.startDate!='')&(m.startDate<=a)&(m.endDate!='')&(m.endDate>=b)]
        got[t]={'rows':len(m),'covers':bool(len(ok)),'start':m.startDate.tolist()[:3],'end':m.endDate.tolist()[:3],'ex':m.exchange.tolist()[:3]}
cov=[t for t,v in got.items() if v['covers']]
print('missing in Yahoo',len(none),'in tiingo list',len(got),'covers member window',len(cov)); 
print('not covered',[t for t in none if t not in cov][:70])
json.dump(got,open(S/'tiingo_list_probe.json','w'))
# SEC: ticker -> CIK resolution
cm=requests.get('https://www.sec.gov/files/company_tickers.json',headers={'User-Agent':sources.sec_user_agent()},timeout=30).json()
cur={v['ticker'].upper().replace('.','-'):str(v['cik_str']) for v in cm.values()}
hdr={'User-Agent':sources.sec_user_agent()}
res={}
for n,(t,x) in enumerate(probe.items()):
    cik=cur.get(t); via='current'
    if not cik:
        u=f'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={t}&type=10-K&count=1&output=atom'
        time.sleep(.15)
        rr=None
        for k in range(3):
            try:
                rr=requests.get(u,headers=hdr,timeout=20); break
            except Exception: time.sleep(2+3*k)
        if rr is None:
            res[t]={'cik':None,'via':None,'err':'timeout'}; continue
        m=re.search(r'<cik>0*(\d+)</cik>',rr.text); cik=m.group(1) if m else None; via='browse'
    res[t]={'cik':cik,'via':via if cik else None}
    if n%50==0: print('cik',n,flush=True)
print('cik resolved',sum(1 for v in res.values() if v['cik']),'of',len(res),'current',sum(v['via']=='current' for v in res.values()),'browse',sum(v['via']=='browse' for v in res.values()))
print('unresolved',[t for t,v in res.items() if not v['cik']][:70])
# classify by filings metadata
for n,(t,v) in enumerate(res.items()):
    if not v['cik']: continue
    try:
        time.sleep(.12); s=sources.sec_submissions(v['cik'])
    except Exception as e:
        v['err']=type(e).__name__; continue
    rec=s['filings']['recent']
    forms,dates,items=rec.get('form',[]),rec.get('filingDate',[]),rec.get('items',[])
    v.update(name=s.get('name'),tickers=s.get('tickers'),exch=s.get('exchanges'),sic=s.get('sic'),former=[f.get('name') for f in s.get('formerNames',[])][:3],last_filing=dates[0] if dates else None,
             last_10k=next((d for f,d in zip(forms,dates) if f in('10-K','10-K405')),None),
             b103=[d for f,d,i in zip(forms,dates,items) if f.startswith('8-K') and '1.03' in (i or '')][:2], m201=[d for f,d,i in zip(forms,dates,items) if f.startswith('8-K') and '2.01' in (i or '')][:2],
             d301=[d for f,d,i in zip(forms,dates,items) if f.startswith('8-K') and '3.01' in (i or '')][:2], f15=[d for f,d in zip(forms,dates) if f.startswith('15-')][:1], f25=[d for f,d in zip(forms,dates) if f.startswith('25')][:1])
json.dump(res,open(S/'sec_probe.json','w'),ensure_ascii=False,indent=0)
print('done')
