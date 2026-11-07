"""Read-only overlap check of live QSF signals from one ledger day: spearman pairs, effective signals, variance shares.  No returns."""
import glob
import gzip,json,sys
import numpy as np
from collections import defaultdict
FILES={'US':'data/qsf/ledger/2026-11-06_US_000011.jsonl.gz','KR':'data/qsf/ledger/2026-11-06_KR_000012.jsonl.gz'}
def ranks(x):
    o=np.argsort(np.argsort(x,kind='mergesort'),kind='mergesort').astype(float)
    # average ties
    v,inv=np.unique(x,return_inverse=True); out=np.zeros(len(v)); 
    for i in range(len(v)): out[i]=o[inv==i].mean()
    return out[inv]
res={}
for mk,f in FILES.items():
    by=defaultdict(list)
    for l in gzip.open(f,'rt'):
        r=json.loads(l); by[r['strategy']].append(r)
    for st,rows in by.items():
        names=[]; W={}; D={}
        for r in rows:
            for x in r['factors']:
                if x['factor'] not in W: names.append(x['factor']); W[x['factor']]=x['weight']; D[x['factor']]=x['domain']
        A=np.full((len(rows),len(names)),np.nan); C=A.copy()
        for i,r in enumerate(rows):
            for x in r['factors']:
                j=names.index(x['factor'])
                if x.get('normalized') is not None: A[i,j]=x['normalized']
                if x.get('contribution') is not None: C[i,j]=x['contribution']
        score=np.array([r['score'] for r in rows])
        info={}
        print(f"\n===== {mk} {st} stocks {len(rows)} factors {len(names)} total weight {sum(W.values())}")
        var=[]
        for j,n in enumerate(names):
            v=A[:,j]; ok=~np.isnan(v)
            uniq=len(np.unique(v[ok])) if ok.any() else 0
            mode=(np.unique(v[ok],return_counts=True)[1].max()/ok.sum()) if ok.any() else 0
            c=np.nan_to_num(C[:,j]); sh=np.cov(c,score)[0,1]/score.var(ddof=1)
            var.append((n,D[n],W[n],ok.mean(),uniq,mode,float(np.nanstd(v)) if ok.any() else 0,sh))
        print('factor domain wt cover uniq top-val-share std var-share')
        for t in sorted(var,key=lambda t:-t[7]): print(f"{t[0]:26s}{t[1][:5]:6s}{t[2]:4.0f} {t[3]:5.2f} {t[4]:5d} {t[5]:5.2f} {t[6]:5.2f} {t[7]:+6.3f}")
        use=[j for j,t in enumerate(var) if t[6]>0 and t[4]>=2 and t[3]>=0.5]
        const=[var[j][0] for j in range(len(names)) if j not in use]
        print('constant/near-empty across stocks:',const,'weight',sum(W[n] for n in const))
        k=len(use); R=np.eye(k)
        for a in range(k):
            for b in range(a+1,k):
                m=~np.isnan(A[:,use[a]])&~np.isnan(A[:,use[b]])
                if m.sum()<30: continue
                x,y=ranks(A[m,use[a]]),ranks(A[m,use[b]])
                if x.std()==0 or y.std()==0: continue
                R[a,b]=R[b,a]=np.corrcoef(x,y)[0,1]
        ev=np.linalg.eigvalsh(R)[::-1]; ev=np.clip(ev,0,None)
        pr=ev.sum()**2/(ev**2).sum()
        cum=np.cumsum(ev)/ev.sum()
        print(f'used {k}; effective N (participation) {pr:.1f}; eig>1 {int((ev>1).sum())}; n for 80% var {int(np.searchsorted(cum,.8)+1)}; top3 eig share {cum[2]:.2f}')
        # weighted effective N: weights by points
        w=np.array([var[j][2] for j in use]); w=w/w.sum()
        print(f'weighted: avg pairwise |rho| {np.abs(R[np.triu_indices(k,1)]).mean():.2f}; concentration of weights {1/(w**2).sum():.1f}')
        pairs=sorted(((abs(R[a,b]),R[a,b],names[use[a]],names[use[b]]) for a in range(k) for b in range(a+1,k)),reverse=True)
        print('top pairs:',[(p[2],p[3],round(p[1],2)) for p in pairs[:10]])
        # greedy clusters at |rho|>=.5
        par=list(range(k))
        def fd(i):
            while par[i]!=i:i=par[i]
            return i
        for a in range(k):
            for b in range(a+1,k):
                if abs(R[a,b])>=.5: par[fd(a)]=fd(b)
        cl=defaultdict(list)
        for a in range(k): cl[fd(a)].append(names[use[a]])
        print('clusters |rho|>=.5:',len(cl),[c for c in cl.values() if len(c)>1])
        # domain var share
        ds=defaultdict(float)
        for t in var: ds[t[1]]+=t[7]
        print('domain var share',{a[:5]:round(b,2) for a,b in ds.items()})

# ---- effective bets by weight over three days
for mk in ('US','KR'):
  for day in ('2026-11-04','2026-11-05','2026-11-06'):
    f=sorted(glob.glob(f'data/qsf/ledger/{day}_{mk}_*'))[-1]
    by=defaultdict(list)
    for l in gzip.open(f,'rt'):
        r=json.loads(l); by[r['strategy']].append(r)
    for st,rows in sorted(by.items()):
        names=sorted({x['factor'] for r in rows for x in r['factors']})
        C=np.zeros((len(rows),len(names)))
        for i,r in enumerate(rows):
            for x in r['factors']:
                if x.get('contribution') is not None: C[i,names.index(x['factor'])]=x['contribution']
        ver=rows[0].get('model_version')
        ev=np.clip(np.linalg.eigvalsh(np.cov(C.T))[::-1],0,None)
        pr=ev.sum()**2/(ev**2).sum(); p=ev/ev.sum(); ent=np.exp(-(p[p>0]*np.log(p[p>0])).sum())
        u,s,vt=np.linalg.svd(C-C.mean(0),full_matrices=False)
        top=sorted(zip(names,vt[0]),key=lambda t:-abs(t[1]))[:5]
        score=np.array([r['score'] for r in rows]); pc=(C-C.mean(0))@vt[0]
        print(mk,st,day,ver,f'bets {pr:.1f} (entropy {ent:.1f}) pc1 {p[0]:.2f} pc1-3 {p[:3].sum():.2f} |corr(pc1,score)| {abs(np.corrcoef(pc,score)[0,1]):.2f}',[(a,round(float(b),2)) for a,b in top] if day=='2026-11-06' else '')
