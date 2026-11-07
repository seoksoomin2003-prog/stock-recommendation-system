# Korean long score with capital spending and KRX share change added. Touches no record: context and score only.
import gzip, json, sys, time, math
from pathlib import Path
import numpy as np
sys.path.insert(0,'.')
from utils import runtime_config
runtime_config.load_local_env()
from terminal.qsf.service import QSF
from terminal.qsf import engine, fundamentals, config, research_kr as kr
from markets.kr.dart import _amount
base=Path('.')
live=json.load(open('data/qsf/latest_KR.json'))
print('published version',live.get('model_version'),'current',config.MODEL_VERSION)
pub={(r['ticker'],r['strategy']):r for r in live['rows']}
bars=json.load(gzip.open('data/qsf/bars_KR.json.gz','rt'))
px=kr._load(base); pos={s:i for i,s in enumerate(px.symbols)}
i=len(px.dates)-1; print('price day',px.dates[i],'vs',px.dates[i-252])
cap,adj=px.data['cap'],px.data['adj_close']
def share_change(c):
    j=pos.get(c)
    if j is None: return None
    a,b,p,q=cap[i,j],cap[i-252,j],adj[i,j],adj[i-252,j]
    if not all(np.isfinite(x) and x>0 for x in (a,b,p,q)): return None
    return float((a/b)/(p/q)-1)
q=QSF(base)
bench=q._history(["^KS11","^KQ11"])["data"] or {}
PRE=q._prefetch([c for c in bars],{**bars,**bench},"^KS11",live["session"])
stats=dict(capex_years=0,no_capex_years=0,negative=0,multi=0,basis_mismatch=0,zero=0)
def with_capex(data,c):
    p=Path(f'research_data/kr_capex/{c}.json')
    if not p.exists(): return data,None
    raw=json.loads(p.read_text()); rows=[]
    ocf={r['end'][:4]:r for r in data.get('ocf') or []}
    for y,v in raw.items():
        if y=='error' or not isinstance(v,dict): continue
        vals=[_amount(x) for x in v.get('capex_raw') or []]
        vals=[x for x in vals if x==x]
        if not vals: stats['no_capex_years']+=1; continue
        stats['capex_years']+=1
        if len(vals)>1: stats['multi']+=1
        if vals[0]<0: stats['negative']+=1
        if vals[0]==0: stats['zero']+=1
        o=ocf.get(y)
        if not o: continue
        if v.get('fs') and o.get('basis') and {'CFS':'CONSOLIDATED','OFS':'SEPARATE'}.get(v['fs'])!=o['basis']: stats['basis_mismatch']+=1; continue
        rows.append({'end':o['end'],'val':abs(vals[0]),'filed':o['filed'],'basis':o['basis']})
    o=data.get('ocf') or []
    if rows and o and max(r['end'] for r in rows)!=max(r['end'] for r in o):
        stats['year_mismatch_dropped']=stats.get('year_mismatch_dropped',0)+1; rows=[]
    return {**data,'capex':rows},rows
out=[];cards={k:[] for k in ('base_L','capex_L','share_L','both_L')};swing=[]
codes=sorted({t for t,_ in pub}); t0=time.time(); same=total=0; sc=[]
for n,c in enumerate(codes):
    if c not in bars: continue
    ident=q._kr_identity(c)
    pre={**PRE[c],"bench":bench.get("^KQ11" if ident.get("market")=="KOSDAQ" else "^KS11") or []}
    ctx=q.context(c,"KR",pre)
    if ctx.get("error"): continue
    fund=ctx["fund"]; krfund=q.cache.read(f"krfund:{c}")
    info=q.cache.read(f"info:{ident.get('yahoo_symbol')}") or {"data":{}}
    if not krfund or fund.get("status")=="UNAVAILABLE": continue
    close=bars[c][-1]["close"]; klass=ident.get("industry_class") or "NON_FINANCIAL"
    shares=q._krx_shares(live['session']).get(c) or info['data'].get('sharesOutstanding')
    data2,_=with_capex(krfund['data'],c)
    def M(d): return fundamentals.metrics(d,close,ctx["expected_session"],is_financial=klass!="NON_FINANCIAL",shares=shares,source=fund.get("source"),insider_pct=info["data"].get("heldPercentInsiders"))
    fc=M(data2); ch=share_change(c); sc.append((c,ctx.get('name'),ch))
    fs={**fund,'share_change':ch}; fb={**fc,'share_change':ch}
    rec={"t":c,"name":ctx.get("name"),"share_change":ch,"fcf":fc.get('fcf'),"fcf_yield":fc.get('fcf_yield'),"fcf_margin":fc.get('fcf_margin'),"fin":klass!="NON_FINANCIAL","mcap":fc.get('market_cap')}
    for st in ("LONG_TERM","SWING"):
        a=engine.score(ctx,st,held=False); p=pub.get((c,st)); total+=1; same+= bool(p) and abs(a["score"]-p["score"])<0.01
        for tag,f in (('capex',fc),('share',fs),('both',fb)):
            b=engine.score({**ctx,"fund":f},st,held=False)
            rec.setdefault(st,{})[tag]={'score':b['score'],'band':b.get('band'),'cov':b.get('coverage')}
            if st=='LONG_TERM': cards[tag+'_L'].append(b)
        rec[st]['base']={'score':a['score'],'band':a.get('band'),'cov':a.get('coverage')}
        if st=='LONG_TERM': cards['base_L'].append(a)
    out.append(rec)
    if n%50==0: print(n,round(time.time()-t0),flush=True)
json.dump(out,open(sys.argv[1],'w'),ensure_ascii=False)
print('stats',stats); print('reproduced published',same,'of',total)
print('fcf_yield present',sum(r['fcf_yield'] is not None for r in out),'share_change present',sum(r['share_change'] is not None for r in out),'of',len(out))
fy=np.array([r['fcf_yield'] for r in out if r['fcf_yield'] is not None]); print('fcf_yield pct',np.percentile(fy,[5,25,50,75,95]).round(3),'neg share',(fy<0).mean().round(2))
s=sorted([x for x in sc if x[2] is not None],key=lambda x:x[2]); print('share change low',[(a,b,round(c,3)) for a,b,c in s[:6]]); print('high',[(a,b,round(c,3)) for a,b,c in s[-10:]])
v=np.array([x[2] for x in s]); print('share change pct',np.percentile(v,[5,25,50,75,95]).round(3),'>10%',(v>.1).sum(),'>5%',(v>.05).sum(),'abs<1%',(abs(v)<.01).mean().round(2))
for st in ('LONG_TERM','SWING'):
  for tag in ('capex','share','both'):
    d=[abs(r[st][tag]['score']-r[st]['base']['score']) for r in out]
    ch=[(r['t'],r['name'],r[st]['base']['band'][:4],r[st][tag]['band'][:4],round(r[st]['base']['score'],1),round(r[st][tag]['score'],1)) for r in out if r[st]['base']['band']!=r[st][tag]['band']]
    b0=sum('BUY' in r[st]['base']['band'] for r in out); b1=sum('BUY' in r[st][tag]['band'] for r in out)
    print(st,tag,'n',len(d),'>=1',sum(x>=1 for x in d),'>=3',sum(x>=3 for x in d),'>=5',sum(x>=5 for x in d),'max',round(max(d),1),'median',round(float(np.median(d)),2),'buy',b0,'->',b1,'bands',len(ch)); 
    if tag=='both': print('  changes',ch[:60])
    if tag=='both': print('  cov',round(np.mean([r[st]['base']['cov'] for r in out]),3),'->',round(np.mean([r[st]['both']['cov'] for r in out]),3))
def bets(cl):
    names=sorted({x['factor'] for c in cl for x in c['factors']}); C=np.zeros((len(cl),len(names)))
    for i,c in enumerate(cl):
        for x in c['factors']:
            if x.get('contribution') is not None: C[i,names.index(x['factor'])]=x['contribution']
    ev=np.clip(np.linalg.eigvalsh(np.cov(C.T)),0,None); return round(float(ev.sum()**2/(ev**2).sum()),2)
print('bets long',{k:bets(v) for k,v in cards.items()})
def rho(cl,a,b):
    x=[];
    for c in cl:
        d={f['factor']:f.get('normalized') for f in c['factors']}
        if d.get(a) is not None and d.get(b) is not None: x.append((d[a],d[b]))
    A=np.array(x); 
    r=lambda v: np.unique(v,return_inverse=True)[1].astype(float)
    return round(float(np.corrcoef(r(A[:,0]),r(A[:,1]))[0,1]),2),len(x)
for a,b in (('balance_dilution','leverage'),('free_cash_flow','business_quality'),('free_cash_flow','valuation'),('free_cash_flow','financial_resilience')):
    try: print(a,b,'base',rho(cards['base_L'],a,b) if a!='free_cash_flow' else None,'both',rho(cards['both_L'],a,b))
    except Exception as e: print(a,b,type(e).__name__)
