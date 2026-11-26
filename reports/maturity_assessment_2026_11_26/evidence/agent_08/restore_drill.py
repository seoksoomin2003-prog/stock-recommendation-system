import json,sys,time
sys.dont_write_bytecode=True
from terminal import automation
t=time.time(); r=automation.check_backup()
out={"status":r["status"],"latest":r["latest"],"seconds":round(time.time()-t,1),
     "checks":{k:{kk:vv for kk,vv in v.items() if kk in("status","sessions","shards","rows")} for k,v in r["checks"].items()}}
print(json.dumps(out,ensure_ascii=False,indent=0))
