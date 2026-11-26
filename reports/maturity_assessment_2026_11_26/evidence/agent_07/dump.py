import json,sys,re
BAD=re.compile(r"capital|amount|budget|shares|qty|equity|notional|cash|won|krw|usd_value",re.I)
def walk(o,pre="",skip=()):
    if isinstance(o,dict):
        for k,v in o.items():
            if BAD.search(k) or k in skip: continue
            walk(v,pre+"."+k,skip)
    elif isinstance(o,list):
        for i,v in enumerate(o[:8]): walk(v,pre+f"[{i}]",skip)
    else:
        s=json.dumps(o,ensure_ascii=False)
        print(pre.lstrip("."),"=",s[:700])
t=sys.argv[1]; which=sys.argv[2]
d=json.load(open(f"eval_{t}.json"))
if which=="card":
    for st in ("SWING","LONG_TERM"):
        c=d["cards"][st]; print("#####",st)
        walk(c,skip=("factors","tech","domains","provenance","levels","market_state","fund_period"))
elif which=="comm":
    walk(d["committee"],skip=("evidence","components","scores","score_labels","conditions"))
elif which=="rest":
    walk({k:v for k,v in d.items() if k not in("cards","committee")})
    for st in ("SWING","LONG_TERM"):
        c=d["cards"][st]; walk({k:c[k] for k in ("levels","market_state","provenance","fund_period")},st)
        for f in c["factors"][:3]: print(json.dumps(f,ensure_ascii=False)[:500])
else:
    walk(json.load(open(which)))
