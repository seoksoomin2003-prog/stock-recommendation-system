from common import *
from datetime import date
from terminal.qsf import order_plan
from terminal import portfolio as pf
b = bars(n=520, drift=0.0009, vol=0.011, seed=7, volume=5e7)
def src(v, **kw):
    return {"status": "REAL", "value": v, "source": "synthetic", "date": "2026-11-20", **kw}
WORST_US = {"vix": src(80.0, percentile=1.0), "vix_term": src(1.30), "hy_spread": src(11.0, percentile=1.0, n=1250),
            "index": {"status": "REAL", "symbol": "SPY", "close": 300.0, "ma50": 380.0, "ma200": 420.0, "source": "synthetic", "date": "2026-11-20"}, "breadth": src(0.05, n=500)}
BEST_US = {"vix": src(11.0, percentile=0.02), "vix_term": src(0.80), "hy_spread": src(2.8, percentile=0.0, n=1250),
           "index": {"status": "REAL", "symbol": "SPY", "close": 500.0, "ma50": 480.0, "ma200": 450.0, "source": "synthetic", "date": "2026-11-20"}, "breadth": src(0.85, n=500)}
print("== 9a. regime weight in the score (config) ==")
for pid, p in config.PROFILES.items():
    print(f"   {pid}: counted REGIME weight {sum(p['domains']['REGIME'].values())}, reference REGIME weight {sum(p['reference'].get('REGIME', {}).values())}")
print("\n== 9b. the same stock scored under the best and the worst market state ==")
for strat in ("SWING", "LONG_TERM"):
    rb, rw = engine.score(ctx("US", b, regime=BEST_US), strat), engine.score(ctx("US", b, regime=WORST_US), strat)
    print(f"   {strat}: best state {rb['market_state']['score_100']:.1f} -> score {rb['score']:.2f} {rb['action']} conf {rb['confidence']} | worst state {rw['market_state']['score_100']:.1f} ({rw['market_state']['state']}, size factor {rw['market_state']['size_factor']}) -> score {rw['score']:.2f} {rw['action']} conf {rw['confidence']} entry {holding.entry_status(rw, ctx('US', b, regime=WORST_US))['status']}")
    print(f"      former formula (regime counted again): best {engine.prior_formula_score(rb['factors']):.2f} | worst {engine.prior_formula_score(rw['factors']):.2f}")
rk = engine.score(ctx("KR", b, regime={"index": {"status": "REAL", "symbol": "^KS11", "close": 1.0, "ma50": 2.0, "ma200": 3.0, "source": "s", "date": "2026-11-20"}, "breadth": src(0.05, n=300),
                                       "usdkrw": {"status": "REAL", "value": 1600.0, "change_63": 0.12, "source": "s", "date": "2026-11-20"}, "kr_credit": {"status": "REAL", "normalized": 0.0, "value": 2.0, "percentile": 1.0, "n": 2500, "text": "", "source": "s", "date": "2026-11-20"}}), "LONG_TERM")
print(f"   KR worst: market state {rk['market_state']['score_100']} {rk['market_state']['state']} size factor {rk['market_state']['size_factor']} | long score {rk['score']:.2f}")
rm = engine.score(ctx("US", b, regime={}), "SWING")
print(f"   US with NO regime data at all: state {rm['market_state']['state']} label {rm['market_state']['label']} size factor {rm['market_state']['size_factor']} | coverage {rm['coverage']:.2f} conf {rm['confidence']}")
rp = engine.score(ctx("US", b, regime={"vix": src(11.0, percentile=0.02)}), "SWING")
print(f"   US with only a calm VIX on file (credit, term, index, breadth all missing): state value {rp['market_state']['score_100']} {rp['market_state']['state']} coverage {rp['market_state']['coverage']}")

print("\n== 9c. held swing position at the worst possible market state: does the REGIME_SEVERE exit condition fire? ==")
pos = {"avg_cost": 100.0, "opened": "2026-11-10", "stop": 1.0, "target": 1e9}
for tag, reg in (("all four regime factors at 0 (state 0.0)", WORST_US), ("nearly worst (VIX 34)", {**WORST_US, "vix": src(34.0, percentile=0.99)})):
    c = ctx("US", b, regime=reg); r = engine.score(c, "SWING", held=True)
    ex = holding.evaluate_exit(r, c, pos, date(2026, 11, 21))
    print(f"   {tag}: REGIME domain score_100 = {r['domains']['REGIME']['score_100']!r} -> exit conditions {[h['code'] for h in ex['conditions']]} action {ex['action']}")

print("\n== 9d. order plan under a favourable and an adverse US day, and Korea ==")
def cands(n, market):
    px = 100.0 if market == "US" else 50000.0
    return [{"ticker": f"C{i:02d}", "name": None, "sector": f"sec{i % 6}", "style": "SWING" if i % 2 else "LONG", "score": 90.0 - i, "close": px, "atr": px * 0.02, "stop": px * (0.96 if i % 2 else 0.90),
             "target": px * 1.1, "adv_value": 5e9 if market == "US" else 5e11, "session": "2026-11-20"} for i in range(n)]
for market in ("US", "KR"):
    eq = 100_000.0 if market == "US" else 100_000_000.0
    acct = {"equity": eq, "cash": eq, "positions": {}}
    for tag, st in (("favourable", {"state": "FAVOURABLE", "score_100": 80.0, "size_factor": 1.0}), ("adverse (state 0)", engine.market_state(engine.score(ctx(market, b, regime=WORST_US if market == "US" else {}), "SWING")["factors"], market) if market == "US" else {"state": "ADVERSE", "score_100": 0.0, "size_factor": config.ADVERSE_SIZE_FACTOR.get("KR", 1.0)})):
        plan = order_plan.build(cands(40, market), acct, market, None, st)
        inv = sum(o["notional"] for o in plan["orders"])
        w = [round(o["weight_pct"], 1) for o in plan["orders"]]
        print(f"   {market} {tag:18s}: size factor {plan['size_factor']} orders {len(plan['orders'])} invested {inv / eq * 100:.1f}% of equity cash left {plan['cash_after'] / eq * 100:.1f}% | first weights {w[:4]} | skipped {plan['skipped_counts']}")
