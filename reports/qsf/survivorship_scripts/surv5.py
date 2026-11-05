import json,re,time,csv,collections
from pathlib import Path
import numpy as np
from terminal import sources
S=Path('data/qsf/research/survivorship')
probe=json.load(open(S/'yahoo_probe.json')); wiki=json.load(open(S/'wiki_cik.json')); old=json.load(open(S/'sec_probe.json')); tii=json.load(open(S/'tiingo_list_probe.json'))
syms=[str(s) for s in np.load('data/qsf/research/prices15y.npz',allow_pickle=False)['symbols']]
facts_dir=Path('data/qsf/research/facts')
cur_cik={}
for t in syms:
    c=sources.sec_cik(t)
    if c: cur_cik[str(int(c))]=t
out={}
for n,(t,x) in enumerate(probe.items()):
    w=wiki.get(t); cik=None; via=None
    if w and len(w['cik'])<=7+3 and int(w['cik'])<3000000: cik,via=w['cik'],'wiki'
    elif old.get(t,{}).get('cik'): cik,via=str(int(old[t]['cik'])),'current_ticker'
    rec=dict(ticker=t,member_first=x['member_first'],member_last=x['member_last'],yahoo_cov=x['cov'],yahoo_last=x['last'],cik=cik,cik_via=via,wiki_name=(w or {}).get('name'),
             tiingo=bool(tii.get(t,{}).get('covers')),tiingo_listed=t in tii,in_cache_as=cur_cik.get(cik) if cik else None)
    cur_for_ticker=old.get(t,{}).get('cik') if old.get(t,{}).get('via')=='current' else None
    rec['ticker_recycled']=bool(cik and cur_for_ticker and str(int(cur_for_ticker))!=cik)
    if cik:
        try:
            s=sources.sec_submissions(cik); r=s['filings']['recent']
            forms,dates,items=r.get('form',[]),r.get('filingDate',[]),r.get('items',[])
            rec.update(sec_name=s.get('name'),now_tickers=s.get('tickers'),now_exch=s.get('exchanges'),sic=s.get('sic'),last_filing=dates[0] if dates else None,
              b103=next((d for f,d,i in zip(forms,dates,items) if f.startswith('8-K') and '1.03' in (i or '')),None),
              m201=next((d for f,d,i in zip(forms,dates,items) if f.startswith('8-K') and '2.01' in (i or '')),None),
              f15=next((d for f,d in zip(forms,dates) if f.startswith('15')),None), f25=next((d for f,d in zip(forms,dates) if f.startswith('25')),None))
        except Exception as e: rec['sub_err']=type(e).__name__
        if not rec['in_cache_as']:
            try:
                f=sources.sec_companyfacts(cik); g=(f.get('facts') or {}).get('us-gaap') or {}
                filed=set(); tags=collections.Counter()
                for tag,v in g.items():
                    for u,rows in (v.get('units') or {}).items():
                        for q in rows:
                            if q.get('form') in('10-K','10-K/A','10-Q') and x['member_first']<=q.get('filed','')<=x['member_last']: filed.add(q['filed'][:4]); tags[tag]+=1
                rec.update(facts=True,fact_years=len(filed),span_years=int(x['member_last'][:4])-int(x['member_first'][:4])+1,
                  has_rev=any(tags.get(k) for k in ('RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','RevenueFromContractWithCustomerIncludingAssessedTax','RevenuesNetOfInterestExpense','SalesRevenueGoodsNet','SalesRevenueServicesNet','RealEstateRevenueNet','InterestAndDividendIncomeOperating')),
                  has_ni=bool(tags.get('NetIncomeLoss') or tags.get('ProfitLoss')),has_eq=bool(tags.get('StockholdersEquity') or tags.get('StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest')))
            except Exception as e: rec.update(facts=False,facts_err=type(e).__name__)
    def cls(q):
        if q['in_cache_as']: return 'renamed_in_cache'
        if not q['cik']: return 'no_cik'
        if q.get('b103'): return 'bankruptcy_8k'
        if q.get('now_tickers'): return 'still_public'
        if q.get('m201'): return 'acquired_8k'
        if q.get('f15') or q.get('f25'): return 'deregistered'
        return 'unknown'
    rec['class']=cls(rec); out[t]=rec
    if n%40==0: print(n,flush=True)
json.dump(out,open(S/'classified.json','w'),ensure_ascii=False,indent=0)
