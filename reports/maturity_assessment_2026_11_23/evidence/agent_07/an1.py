import json, sys, collections
m = sys.argv[1]
d = json.load(open(f"big/cards_{m}.json"))
C = collections.Counter
for st in ("SWING", "LONG_TERM"):
    rs = [c for k, c in d.items() if c["strategy"] == st]
    n = len(rs)
    print(f"== {m} {st} n={n} model={rs[0]['model_version']}")
    print(" bands", dict(C(c["band"] for c in rs)))
    print(" action", dict(C(c["action"] for c in rs)), "actionability", dict(C(c["actionability"] for c in rs)))
    print(" entry", dict(C(c["entry_status"] for c in rs)))
    print(" confidence", dict(C(c["confidence"] for c in rs)))
    print(" held_back", [(c["ticker"], round(c["score"],1), round(c["conservative_score"],1), c["band_label"]) for c in rs if c.get("band_held_back")])
    act = [c for c in rs if c["actionability"] == "ACTIONABLE"]
    now = [c for c in act if c["entry_status"] == "ENTRY_NOW"]
    buy = [c for c in act if c["band"] in ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE")]
    print(f" ENTRY_NOW {len(now)} ({len(now)/n:.0%} of all); in buy band {len(buy)}; ENTRY_NOW&buy {sum(1 for c in now if c in buy)}; buy not now {sum(1 for c in buy if c['entry_status']!='ENTRY_NOW')}; now under buy {sum(1 for c in now if c not in buy)}")
    print(" buy-not-now entry statuses", dict(C(c["entry_status"] for c in buy if c["entry_status"] != "ENTRY_NOW")))
    print(" surface_note present", sum(1 for c in rs if c.get("surface_note")))
    print(" stale cards", sum(1 for c in rs if c.get("stale")), "partial", sum(1 for c in rs if c.get("partial")), "missing any", sum(1 for c in rs if c.get("missing")), "prov stale", sum(1 for c in rs if (c.get("provenance") or {}).get("stale")))
    if st == "SWING":
        lv = [c for c in act if (c.get("levels") or {}).get("status") == "REAL"]
        rr = [c["levels"]["reward_risk"] for c in lv if c["levels"].get("reward_risk") is not None]
        nores = [c for c in lv if not c["tech_small"].get("resistance")]
        print(" swing levels REAL", len(lv), "no resistance", len(nores), "rr>=1.5 among no-resistance", sum(1 for c in nores if (c["levels"].get("reward_risk") or 0) >= 1.5), "max rr no-res", max([c["levels"].get("reward_risk") or 0 for c in nores] or [0]))
        print(" swing rr>=1.5 overall", sum(1 for x in rr if x >= 1.5), "of", len(rr))
        print(" swing score max", max(c["score"] for c in act), "count>=75", sum(1 for c in act if c["score"]>=75), ">=70", sum(1 for c in act if c["score"]>=70), ">=67", sum(1 for c in act if c["score"]>=67))
    else:
        print(" long count>=75", sum(1 for c in act if c["score"]>=75), ">=70", sum(1 for c in act if c["score"]>=70), ">=67", sum(1 for c in act if c["score"]>=67))
        inv = C(json.dumps(c["holding"].get("invalidation"), ensure_ascii=False) for c in rs)
        print(" distinct long invalidation texts", len(inv))
        sc = C((c["holding"].get("scenarios") or {}).get("status") for c in rs)
        print(" scenarios", dict(sc))
        fin = [c for c in buy if c["fund_small"].get("is_financial")]
        print(" buy-band financials", len(fin), "of", len(buy), "; sectors", C(c["fund_small"].get("sector") for c in buy).most_common(6))
