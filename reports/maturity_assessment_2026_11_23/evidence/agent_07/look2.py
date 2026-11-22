import json, sys, collections
for m in ("us", "kr"):
    d = json.load(open(f"big/latest_{m}.json"))
    rows = d["rows"]
    print(m, "stance", json.dumps(d["stance"], ensure_ascii=False)[:600])
    print("row keys", list(rows[0].keys()))
    print(json.dumps(rows[0], ensure_ascii=False)[:1800])
    for strat in ("SWING", "LONG_TERM"):
        rs = [r for r in rows if r.get("strategy") == strat]
        c = collections.Counter((r.get("band"), ) for r in rs)
        print(m, strat, len(rs), "bands", dict(collections.Counter(r.get("band") for r in rs)))
        print("  actionability", dict(collections.Counter(r.get("actionability") for r in rs)))
        for k in ("entry_status", "entry", "confidence", "merger", "candidate"):
            if k in rs[0]:
                print("  ", k, dict(collections.Counter(str(r.get(k)) if not isinstance(r.get(k), dict) else str(r[k].get("status")) for r in rs)))
