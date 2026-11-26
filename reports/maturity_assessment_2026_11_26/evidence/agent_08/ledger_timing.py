import json,sys
from datetime import datetime,timedelta,timezone,date
KST=timezone(timedelta(hours=9))
rows=[json.loads(l) for l in open('data/qsf/ledger/index.jsonl') if l.strip()]
print('rows',len(rows),'keys',sorted(rows[0].keys()))
from collections import defaultdict
by=defaultdict(list)
for r in rows: by[(r.get('market'),r.get('session'))].append(r)
for (m,s),rs in sorted(by.items(),key=lambda x:(x[0][0] or '',x[0][1] or '')):
    ts=[r.get('recorded_at') or r.get('at') or r.get('created_at') for r in rs]
    k=[datetime.fromisoformat(t).astimezone(KST).strftime('%m-%d %a %H:%M') for t in ts if t]
    print(m,s,len(rs),k[:1],k[-1:] if len(k)>1 else '',[r.get('model_version') for r in rs][:1],[r.get('void') or r.get('status') for r in rs][:3])
