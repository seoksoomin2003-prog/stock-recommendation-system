import json, sys, glob, os
def short(v, depth=0):
    if isinstance(v, dict):
        if depth >= 2: return "{%d keys}" % len(v)
        return {k: short(x, depth+1) for k, x in list(v.items())[:40]}
    if isinstance(v, list):
        return "[%d items]" % len(v) if len(v) > 6 or any(isinstance(x,(dict,list)) for x in v) else v
    if isinstance(v, str) and len(v) > 160: return v[:160] + "..."
    return v
for f in sorted(glob.glob("reports/qsf/*.json")):
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        print("##", f, "ERR", e); continue
    print("##", f, os.path.getsize(f))
    if isinstance(d, dict):
        print(json.dumps(short(d), ensure_ascii=False)[:2500])
    else:
        print(type(d), len(d))
