import json,re,time,csv,gzip,bisect
from pathlib import Path
import requests
from utils import runtime_config; runtime_config.load_local_env()
from terminal import sources
from terminal.qsf import open_prices as op, validate_pit as vp, validate_open as vo, validate as V
R=Path('data/qsf/research'); S=R/'survivorship'
old="CHK ANF FRX DOW LIFE LSI ANDV BEAM SWY BHGE VIAV AABA AGN SNDK CFN FOXA TGNA ARNC BTUUQ MOLX WYND NYX DELL JCP S BMC DF APOL FHN CVH HNZ BIG IR SUN RRD ATGE TIE GR FII LXK SHLD COV NVLS SVU PGN CEG HSH MHS EP CPWR TLAB MI NSM MWW CEPH ITT AKS SUNEQ JNS AYE Q MFE RSHCQ MEE NOVL MDP GENZ QLGC ANRZQ PETM EKDKQ KG SII NYT PTV MIL ODP MMI CBE STR RX BNI JAVA PBG BDK XTO BJS ACS".split()
files=op.read_archives(R/'open/pystock/repo.tar.gz',old)
ser={t:op.build_series([b[t] for b in files if t in b]) for t in old if any(t in b for b in files)}
print('in pystock',len(ser))
H={'User-Agent':sources.GENERIC_UA}; api='https://en.wikipedia.org/w/api.php'
m=json.load(open(S/'wiki_cik.json'))
for ts in ['2009-07-01','2010-01-01','2010-07-01','2011-01-01','2011-07-01','2012-01-01','2012-07-01','2013-01-01']:
    for k in range(4):
        time.sleep(4+6*k); r=requests.get(api,params={'action':'query','prop':'revisions','titles':'List of S&P 500 companies','rvlimit':1,'rvdir':'older','rvstart':ts+'T00:00:00Z','rvprop':'content|timestamp','rvslots':'main','format':'json','formatversion':2},headers=H,timeout=40)
        if r.status_code==200 and r.text[:1]=='{': break
    else: print(ts,'fail'); continue
    txt=r.json()['query']['pages'][0]['revisions'][0]['slots']['main']['content']; n=0
    for row in re.split(r'\n\|-',txt):
        t=vp.row_ticker(row) or (re.search(r'(?:nyse\.com/quote/[A-Z]+:|nasdaq\.com/[a-z/\-]*/|quote/)([A-Z.\-]{1,6})\b',row) or [None,None])[1]
        c=re.search(r'(?<![\d])(\d{10})(?![\d])',row) or re.search(r'CIK=(\d{4,10})',row)
        if t and c:
            T=t.upper().replace('.','-'); name=re.search(r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]',row)
            m.setdefault(T,{'cik':str(int(c.group(1))),'name':name.group(1) if name else None,'first':ts}); n+=1
    print(ts,n,flush=True)
json.dump(m,open(S/'wiki_cik_old.json','w'),ensure_ascii=False)
keys,snaps=vp.load_history(list(csv.reader(open(S/'hist_updated.csv'))))
out={}
for t,s in sorted(ser.items()):
    if not s['rows']: continue
    a,b=s['rows'][0]['date'],s['rows'][-1]['date']
    n=sum(1 for k,sn in zip(keys,snaps) if '2010-01-01'<=k<='2013-12-31' and t in sn and a<=k<=b)
    w=m.get(t); nm=None
    if w:
        try: nm=sources.sec_submissions(w['cik']).get('name')
        except Exception as e: nm='ERR '+type(e).__name__
    print(t,'|',(w or {}).get('name','-')[:24] if w else '-','|',(nm or '-')[:26],'|',(w or {}).get('cik'),'|',a[:7],b[:7],n,s['gaps'],s['stopped'])
    out[t]=dict(cik=(w or {}).get('cik'),wiki=(w or {}).get('name'),sec=nm,first=a,last=b,snaps=n)
json.dump(out,open('/tmp/oos_old.json','w'),indent=0)
print('no pystock',[t for t in old if t not in ser])
