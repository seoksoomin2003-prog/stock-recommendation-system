from common import *
import copy
b = bars(n=520, drift=0.0009, vol=0.011, seed=7, volume=5e7)
print("== score a hair under / on the lines (stubbed factor values, real aggregation) ==")
for x in (0.69999, 0.70, 0.54999, 0.55, 0.79999, 0.80):
    o = stub_calc({"*": x}); c = ctx("US", b); r = engine.score(c, "LONG_TERM"); rh = engine.score(c, "LONG_TERM", held=True); e = holding.entry_status(r, c); restore_calc(o)
    print(f"   all factors {x}: score {r['score']:.3f} band {r['band']:22s} action {r['action']:6s} color {r['color']} entry {e['status']:22s} | if held: {rh['action']}")

print("\n== close a hair under / over the 200-day and 50-day averages (real factors) ==")
flat = bars(n=520, drift=0.0, vol=0.004, seed=21, volume=5e7)
t0 = technicals.compute(flat)
for tag, target in (("ma200", t0["ma200"]), ("ma50", t0["ma50"])):
    for eps in (+0.0005, -0.0005):
        x = copy.deepcopy(flat); c_ = target * (1 + eps); x[-1].update(close=c_, adj_close=c_, high=max(x[-1]["high"], c_), low=min(x[-1]["low"], c_))
        t = technicals.compute(x); c = ctx("US", x); r = engine.score(c, "SWING")
        ts = next(f["normalized"] for f in r["factors"] if f["factor"] == "trend_structure")
        print(f"   close {eps * 100:+.2f}% from {tag} ({t[tag]:.3f}): trend_structure {ts:.3f} swing score {r['score']:.2f}")

print("\n== earnings date: sessions to the announcement ==")
for n, basis in ((3, None), (2, None), (6, "ESTIMATE"), (5, "ESTIMATE")):
    e = {"sessions": n, "date": "2026-11-25", **({"basis": basis, "from": "2025-11-25"} if basis else {})}
    c = ctx("US", b, earnings=e); r = engine.score(c, "SWING"); en = holding.entry_status(r, c)
    print(f"   {n} sessions ({basis or 'provider date'}): score {r['score']:.2f} action {r['action']} gates {[g['code'] for g in r['gates']]} entry {en['status']}")

print("\n== market state 50.0 vs 49.99: the US order-size factor ==")
def rows(v):
    return [{"factor": f, "domain": "REGIME", "status": "REAL", "normalized": v, "raw": {}} for f in config.MARKET_STATE_WEIGHTS["US"]]
for v in (0.5, 0.4999):
    m = engine.market_state(rows(v), "US"); print(f"   state {m['score_100']:.2f}: {m['state']} size factor {m['size_factor']}")

print("\n== reward/risk 1.5 line (swing entry) and liquidity gate ==")
print("   ATR projection target: reward/risk =", round((3 * 1 - config.round_trip_cost('US') * 50) / (2 * 1 + config.round_trip_cost('US') * 50), 3), "for a 2% ATR stock with no resistance above -> always under 1.5 -> never ENTRY_NOW")
for adv in (2.0001e7, 1.9999e7):
    x = copy.deepcopy(b)
    k = adv / technicals.compute(b)["adv_value"]
    for row in x: row["volume"] *= k
    r = engine.score(ctx("US", x), "LONG_TERM"); print(f"   20-day traded value {technicals.compute(x)['adv_value']:,.0f}: action {r['action']} gates {[g['code'] for g in r['gates']]} (score {r['score']:.2f})")
