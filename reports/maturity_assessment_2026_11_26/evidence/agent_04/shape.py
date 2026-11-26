import json,sys
from pathlib import Path
from terminal.qsf.ledger import Ledger
led=Ledger(Path('.'))
print(led.verify())
idx=led.read_index()
for r in idx['rows']:
    print({k:v for k,v in r.items() if k not in('hash','prev_hash','sha256')})
rows=[r for r in led._live_rows() if r['market']=='US']
s=led._load(rows[-1])
x=s[0]
x2=dict(x); x2['factors']=x['factors'][:4]
print(json.dumps(x2,ensure_ascii=False,indent=1,default=str)[:6000])
