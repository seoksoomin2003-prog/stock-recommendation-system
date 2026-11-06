import json
from utils import runtime_config; runtime_config.load_local_env()
from terminal import sources
C={'AKS':'918160','ANF':'1018840','APOL':'929887','BIG':'768835','CHK':'895126','DF':'931336','DOW~OLD':'29915','FHN':'36966','FII':'1056288','FOXA~OLD':'1308161','IR~OLD':'1466258','ITT':'216228','JCP':'1166126','JNS':'1065865','LXK':'1001288','MDP':'65011','MIL':'66479','MWW':'1020416','NYT':'71691','ODP':'800240','QLGC':'918386','RRD':'29669','S':'101830','SHLD':'1310067','SNDK~OLD':'1000180','STR':'751652','SVU':'95521'}
out={}
for a,c in C.items():
    s=sources.sec_submissions(c); nm=s.get('name'); print(a,c,nm,[f['name'] for f in s.get('formerNames',[])][:2])
    out[a]={'ticker':a.split('~')[0],'cik':c,'sec_name':nm}
json.dump(out,open('reports/qsf/QSF_OOS_UNIVERSE.json','w'),ensure_ascii=False,indent=0)
