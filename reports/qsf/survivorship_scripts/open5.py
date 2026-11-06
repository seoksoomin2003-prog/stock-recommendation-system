import json
from utils import runtime_config; runtime_config.load_local_env()
from terminal import sources
U=json.load(open('/tmp/open_u.json'))
s=sources.sec_submissions('353944'); print(s.get('name'),[f['name'] for f in s.get('formerNames',[])][:2])
ok='INTERNATIONAL GAME' in (s.get('name') or '').upper()
if ok: U['IGT'].update(cik='353944',name=s['name'])
else: U.pop('IGT')
out={t:{'cik':str(int(v['cik'])),'sec_name':v['name'],'exited_before_source_end':v['exited']} for t,v in sorted(U.items())}
json.dump(out,open('reports/qsf/QSF_OPEN_UNIVERSE.json','w'),ensure_ascii=False,indent=0)
print(len(out),sum(v['exited_before_source_end'] for v in out.values()))
print(sorted(t for t,v in out.items() if v['exited_before_source_end']))
