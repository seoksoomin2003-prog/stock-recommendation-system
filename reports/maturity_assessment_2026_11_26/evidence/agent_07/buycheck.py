import json, sys
E=sys.argv[1]
from terminal import assistant as a
from terminal.qsf import stance as qs, config
print("PRESETS", qs.PRESETS)
print("VERDICT_KO", a.VERDICT_KO)
for t,m in (("INCY","US"),("HAS","US"),("005830","KR")):
    d=json.load(open(f"{E}/eval_{t}.json"))
    for st in ("SWING","LONG_TERM"):
        s=d["cards"][st]
        gates=[g.get("text") or g.get("code") for g in s.get("gates") or []]
        raw=next((f.get("raw") or {} for f in s.get("factors") or [] if f.get("factor")=="earnings_calendar" and isinstance(f.get("raw"),dict)),{})
        for level in ("AGGRESSIVE","NORMAL"):
            v=a.buy_verdict(s,st,m,gates=gates,marks=[],earnings=raw,soon=False,level=level,wide=set(),state=s.get("market_state") or {},held=False)
            print("==",t,st,level,round(s["score"],1),s["band_label"],s["entry_status"],s["confidence"])
            print(json.dumps({k:v[k] for k in ("label","why","change","also","notes")},ensure_ascii=False,indent=1))
        print("entry_ko:",a.entry_ko(s["entry_status"],st),"|",a.entry_meaning(s["entry_status"],st))
