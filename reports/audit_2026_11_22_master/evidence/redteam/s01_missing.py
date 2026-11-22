from common import *
import itertools
b = bars(volume=5e7)
print("=== A. factor-level missing (stubbed factor values; real engine.score aggregation) ===")
for market, strat in (("US", "LONG_TERM"), ("US", "SWING"), ("KR", "SWING"), ("KR", "LONG_TERM")):
    p = config.profile_for(market, strat)
    flat = [(f, w, d) for d, ws in p["domains"].items() for f, w in ws.items()]
    tot = sum(w for _, w, _ in flat)
    # search: which set of factors, when LOW (0.0) and then made MISSING, gives the largest rise while the card stays 'sufficient'
    best = None
    names = [f for f, _, _ in flat]
    for r in range(1, 7):
        for combo in itertools.combinations(flat, r):
            wsum = sum(w for _, w, _ in combo)
            if wsum / tot > 0.30 + 1e-9:
                continue
            vals = {"*": 0.9}
            vals.update({f: "MISSING" for f, _, _ in combo})
            o = stub_calc(vals); res = engine.score(ctx(market, b), strat); restore_calc(o)
            if res["actionability"] == "INSUFFICIENT_DATA":
                continue
            if best is None or wsum > best[0]:
                best = (wsum, [f for f, _, _ in combo], res)
    wsum, combo, after = best
    vals = {"*": 0.9}; vals.update({f: 0.0 for f in combo})
    o = stub_calc(vals); before = engine.score(ctx(market, b), strat); restore_calc(o)
    print(f"{p['id']}: low factors {combo} (weight {wsum}/{tot})")
    print(f"   all present, these at 0.0, rest 0.9 : score {before['score']:.2f} band {before['band']} action {before['action']} coverage {before['coverage']:.3f} conf {before['confidence']}")
    print(f"   same factors MISSING               : score {after['score']:.2f} band {after['band']} action {after['action']} coverage {after['coverage']:.3f} conf {after['confidence']} actionability {after['actionability']}")
    print(f"   rise = {after['score'] - before['score']:+.2f} points")

print("\n=== B. coverage thresholds (US LONG_TERM): drop factors one by one, everything else 0.9 ===")
p = config.profile_for("US", "LONG_TERM")
order = ["insider_ownership", "capital_allocation", "governance", "material_events", "momentum_persistence", "relative_strength", "long_trend", "liquidity", "leverage", "downside_drawdown", "balance_dilution", "free_cash_flow"]
vals = {"*": 0.9}
for f in [None] + order:
    if f:
        vals[f] = "MISSING"
    o = stub_calc(vals); r = engine.score(ctx("US", b), "LONG_TERM"); restore_calc(o)
    print(f"   missing+={str(f):22s} coverage {r['coverage']:.3f} conf {r['confidence']:12s} action {r['action']:18s} actionability {r['actionability']} short={r['short_domains']}")

print("\n=== C. NOT_APPLICABLE shrinks the denominator: a 'financial' with FCF and leverage N/A, plus missing events ===")
vals = {"*": 0.9, "free_cash_flow": "NA", "leverage": "NA"}
o = stub_calc(vals); r = engine.score(ctx("US", b), "LONG_TERM"); restore_calc(o)
print("   N/A only:", brief(r))
