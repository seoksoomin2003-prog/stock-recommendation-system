"""Agent 02 scratch: print the decision-facing text of one saved /api/qsf/evaluate reply (no amounts of the user's account)."""
import json, sys
d = json.load(open(sys.argv[1]))
print("==", d.get("ticker"), d.get("name"), d.get("status"))
print("committee_note:", d.get("committee_note"))
for st, c in (d.get("cards") or {}).items():
    if not isinstance(c, dict) or "score" not in c:
        continue
    print(f"\n--- {st}: version {c.get('model_version')} score {c.get('score') and round(c['score'], 1)} band {c.get('band_label')} action {c.get('action')} act {c.get('actionability')} conf {c.get('confidence')} "
          f"cov {round(c.get('coverage') or 0, 3)} in-cov {round(c.get('input_coverage') or 0, 3)} entry {c.get('entry_status')}")
    print("  why_summary:", c.get("why_summary"))
    print("  entry reason:", (c.get("entry") or {}).get("reason"))
    print("  partial:", c.get("partial"), "| missing:", c.get("missing"))
    for f in c.get("factors") or []:
        if f.get("domain") in ("FUNDAMENTAL",) or f["factor"] in ("financial_resilience", "leverage", "capital_allocation", "insider_ownership"):
            print(f"   {f['factor']:26s} {f['status']:15s} n={None if f.get('normalized') is None else round(f['normalized'], 2)} w={f.get('weight')} inputs={f.get('inputs')} | {f.get('explanation') or f.get('reason')}")
    p = c.get("plain") or {}
    for part in p.get("parts") or []:
        print("  [plain]", part["h"], "::", " / ".join(part["lines"])[:600])
    h = c.get("holding") or {}
    print("  milestones:", h.get("milestones"), "| scenarios:", (h.get("scenarios") or {}).get("status"), [(x["case"], round(x["price"])) for x in (h.get("scenarios") or {}).get("cases") or []])
    fund = c.get("fund") or c.get("fundamentals")
    if isinstance(fund, dict):
        print("  fund keys:", sorted(fund.keys())[:60])
com = d.get("committee") or {}
for o in com.get("investors") or []:
    print(f"\n  [{o.get('name')}] {o.get('recommendation_ko')} score {o.get('score')} conf {o.get('confidence')} :: {o.get('opinion')}")
    print("     valuation:", o.get("valuation"), "| +", o.get("positives"), "| -", o.get("negatives"), "| unchecked", o.get("unchecked"), "| missing", (o.get("missing") or [])[:6])
cc = com.get("committee") or {}
print("\n  committee:", cc.get("decision_ko") or cc.get("decision"), "::", str(cc.get("summary") or cc.get("reason") or cc.get("why"))[:500])
