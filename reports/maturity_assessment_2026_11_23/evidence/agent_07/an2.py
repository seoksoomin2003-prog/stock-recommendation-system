import json, sys
m = sys.argv[1]; keys = sys.argv[2:]
d = json.load(open(f"big/cards_{m}.json"))
def show(k):
    c = d[k]
    print("=" * 30, k, c.get("name"))
    print(" score", None if c["score"] is None else round(c["score"], 1), "cons", c.get("conservative_score") and round(c["conservative_score"], 1), "|", c["band_label"], "| action", c["action"], c["action_label"], "|", c["actionability"], "| conf", c["confidence"], "cov", round(c["coverage"], 2), "in_cov", round(c.get("input_coverage") or 0, 2))
    print(" domains", {k2: (None if v.get("score_100") is None else round(v["score_100"])) for k2, v in c["domains"].items()})
    print(" entry", c["entry_status"], "|", c["entry"].get("reason"), "| zone", c["entry"].get("zone"))
    print(" WHY:", c["why_summary"])
    print(" SURFACE:", c.get("surface_note"))
    print(" CHANGE:", c["what_would_change"])
    print(" POS:", [x["text"] for x in c["top_positive"]]); print(" NEG:", [x["text"] for x in c["top_negative"]])
    print(" missing", c["missing"], "stale", c["stale"], "partial", c["partial"], "gates", [g["text"] for g in c["gates"]])
    h = c["holding"]
    if c["strategy"] == "SWING":
        print(" HOLD: exp", h.get("expected_sessions"), "range", h.get("range_sessions"), "stop", h.get("stop"), "target", h.get("target"), "rr", h.get("reward_risk"), "| inval", h.get("invalidation"), "| why", h.get("why"), "| target_method", h.get("target_method"), "| stop_method", h.get("stop_method"))
    else:
        print(" HOLD: months", h.get("range_months"), "| milestones", h.get("milestones"), "| scen", json.dumps(h.get("scenarios"), ensure_ascii=False)[:420], "| why", h.get("why"))
    print(" tech", c["tech_small"]); print(" fund", c["fund_small"], "earn", c.get("earnings"))
    print(" factors:", [(f["factor"], f["status"], None if f.get("normalized") is None else round(f["normalized"], 2), f["weight"], f.get("scored")) for f in c["factors"]])
    print(" PLAIN:", json.dumps(c.get("plain"), ensure_ascii=False)[:1800])
for k in keys: show(k)
