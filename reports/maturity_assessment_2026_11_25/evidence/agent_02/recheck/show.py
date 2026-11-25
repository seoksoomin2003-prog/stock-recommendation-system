"""Agent 02 recheck: decision-facing text of one saved /api/qsf/evaluate reply (no account amounts)."""
import json, sys
d = json.load(open(sys.argv[1]))
print("==", d.get("ticker"), d.get("name"), d.get("status"))
print("committee_note:", d.get("committee_note"))
for st in ("LONG_TERM", "SWING"):
    c = (d.get("cards") or {}).get(st) or {}
    if "score" not in c:
        continue
    print(f"\n--- {st}: {c.get('model_version')} score {round(c['score'], 2)} band {c.get('band_label')} action {c.get('action')} conf {c.get('confidence')} entry {c.get('entry_status')} held_back {c.get('band_held_back')} capex_unread {c.get('capex_unread')}")
    print("  entry reason:", (c.get("entry") or {}).get("reason"))
    print("  why_summary:", c.get("why_summary"))
    print("  fund_checks:", json.dumps(c.get("fund_checks"), ensure_ascii=False))
    print("  fund_period:", json.dumps(c.get("fund_period"), ensure_ascii=False)[:400])
    print("  fuller_inputs:", json.dumps(c.get("fuller_inputs"), ensure_ascii=False)[:600])
    if st == "LONG_TERM":
        for f in c.get("factors") or []:
            if f.get("domain") == "FUNDAMENTAL" or f["factor"] in ("financial_resilience", "leverage", "capital_allocation"):
                print(f"   {f['factor']:24s} {f['status']:14s} n={None if f.get('normalized') is None else round(f['normalized'], 2)} | {f.get('explanation') or f.get('reason')}")
        h = c.get("holding") or {}
        print("  milestones:", h.get("milestones"))
    for part in (c.get("plain") or {}).get("parts") or []:
        print("  [plain]", part["h"], "::", " / ".join(part["lines"])[:700])
com = d.get("committee") or {}
for o in com.get("investors") or []:
    print(f"\n  [{o.get('name')}] {o.get('recommendation_ko')} {o.get('score')} :: {o.get('opinion')}")
