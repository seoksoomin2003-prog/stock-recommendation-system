import re,time,json,requests
from pathlib import Path
from utils import runtime_config; runtime_config.load_local_env()
from terminal import sources
from terminal.qsf import validate
hdr={'User-Agent':sources.sec_user_agent()}
Q={'AKS':'AK Steel Holding','ANF':'Abercrombie & Fitch','APOL':'Apollo Education Group','BIG':'Big Lots','DF':'Dean Foods','FHN':'First Horizon','FII':'Federated','ITT':'ITT Corp','JCP':'Penney J C','JNS':'Janus Capital Group','LXK':'Lexmark International','MDP':'Meredith Corp','MIL':'Millipore','MWW':'Monster Worldwide','NYT':'New York Times Co','ODP':'Office Depot','QLGC':'QLogic','RRD':'Donnelley R R','S':'Sprint Corp','SHLD':'Sears Holdings','STR':'Questar Corp','SVU':'Supervalu'}
for t,q in Q.items():
    time.sleep(.2)
    r=requests.get('https://www.sec.gov/cgi-bin/browse-edgar',params={'company':q,'type':'10-K','owner':'include','count':'10','action':'getcompany','output':'atom'},headers=hdr,timeout=30)
    names=re.findall(r'<title>([^<]*)</title>',r.text)[1:6]; cik=re.findall(r'<cik>0*(\d+)</cik>',r.text)[:5]; one=re.search(r'<conformed-name>([^<]*)',r.text)
    print(t,q,'|',one.group(1) if one else '',cik,'|',[n[:40] for n in names][:4])
u=validate._universe(Path('.'))
print('collide with cached',[t for t in ['AKS','ANF','APOL','BIG','CHK','DF','DOW','FHN','FII','FOXA','IR','ITT','JCP','JNS','LXK','MDP','MIL','MWW','NYT','ODP','QLGC','RRD','S','SHLD','SNDK','STR','SVU','SUN'] if t in u['tickers']])
