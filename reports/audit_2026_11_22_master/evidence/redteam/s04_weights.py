from common import *
print("MODEL", config.MODEL_VERSION, "| BANDS", [(b[0], b[1]) for b in config.BANDS])
b = bars()
for pid, p in config.PROFILES.items():
    dom = {d: sum(w.values()) for d, w in p["domains"].items()}
    tot = sum(dom.values())
    big = max(((w, f, d) for d, ws in p["domains"].items() for f, w in ws.items()))
    print(f"\n{pid}: total weight {tot}; domain weights {dom}; REGIME counted weight = {dom['REGIME']}; reference = { {d: sum(w.values()) for d, w in p['reference'].items()} }")
    print(f"  largest domain: {max(dom, key=dom.get)} = {max(dom.values())/tot*100:.1f}% ; largest factor: {big[1]} ({big[2]}) = {big[0]}/{tot} = {big[0]/tot*100:.2f} pts of 100")
    market, strat = p["market"], p["strategy"]
    # flip each factor 0 -> 1 with the rest at 0.5
    rows = []
    for d, ws in p["domains"].items():
        for f in ws:
            o = stub_calc({"*": 0.5, f: 0.0}); lo = engine.score(ctx(market, b), strat)["score"]; restore_calc(o)
            o = stub_calc({"*": 0.5, f: 1.0}); hi = engine.score(ctx(market, b), strat)["score"]; restore_calc(o)
            rows.append((hi - lo, f, lo, hi))
    rows.sort(reverse=True)
    print("  flip 0->1 (rest 0.5):", ", ".join(f"{f} {lo:.2f}->{hi:.2f} (+{dlt:.2f})" for dlt, f, lo, hi in rows[:4]))
    # can one factor move a stock across 70 ?  rest at x
    dlt, f, _, _ = rows[0]
    for x in (0.60, 0.65, 0.68):
        o = stub_calc({"*": x, f: 0.0}); lo = engine.score(ctx(market, b), strat); restore_calc(o)
        o = stub_calc({"*": x, f: 1.0}); hi = engine.score(ctx(market, b), strat); restore_calc(o)
        print(f"  rest at {x}: {f}=0 -> score {lo['score']:.2f} {lo['action']}; {f}=1 -> score {hi['score']:.2f} {hi['action']}")
