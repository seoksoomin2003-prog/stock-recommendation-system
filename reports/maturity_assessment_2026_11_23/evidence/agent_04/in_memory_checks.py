"""Read only, in memory, synthetic rows and a synthetic account of 100,000 units (not the user's).  No provider, no write."""
import sys, json
from pathlib import Path
repo = Path(sys.argv[1]); sys.path.insert(0, str(repo))
from terminal.qsf import engine, config, stance, order_plan as op
from terminal.committee import portfolios
from terminal import assistant

def rows(market, vals, status="REAL"):
    return [{"factor": f, "domain": "REGIME", "status": (status if v is not None else "MISSING"), "normalized": v} for f, v in vals.items()]

out = {}
us = lambda **k: rows("US", k)
# 1. hysteresis: just under and just over the middle
for v in (0.499, 0.501):
    s = engine.market_state(us(vix_regime=v, vix_term=v, credit_spread=v, index_trend_breadth=v), "US")
    out[f"US all factors {v}"] = {k: s[k] for k in ("score_100", "state", "size_factor", "new_exposure_cap", "coverage")}
# 2. every input STALE: still read?
s = engine.market_state(rows("US", dict(vix_regime=0.8, vix_term=0.8, credit_spread=0.8, index_trend_breadth=0.8), status="STALE"), "US")
out["US all STALE 0.8"] = {k: s[k] for k in ("score_100", "state", "size_factor", "new_exposure_cap", "coverage")}
# 3. unknown (one factor of four), and no factors at all
s1 = engine.market_state(us(vix_regime=1.0, vix_term=None, credit_spread=None, index_trend_breadth=None), "US")
s0 = engine.market_state([], "US")
k0 = engine.market_state([], "KR")
out["US one factor"] = {k: s1[k] for k in ("score_100", "state", "size_factor", "new_exposure_cap", "coverage")}
out["US none"] = {k: s0[k] for k in ("score_100", "state", "size_factor", "new_exposure_cap", "coverage")}
out["KR none"] = {k: k0[k] for k in ("score_100", "state", "size_factor", "new_exposure_cap", "coverage")}
out["assistant US one factor"] = [i["text"] for i in assistant.market_items(s1, "US")]
out["assistant US none"] = [i["text"] for i in assistant.market_items(s0, "US")]
out["assistant KR none"] = [i["text"] for i in assistant.market_items(k0, "KR")]
# 4. the newest recorded factor values (2026-11-20) with the high-yield factor at the middle, and the 2026-11-16 ones
hist = json.loads((Path(__file__).parent / "state_history.json").read_text())
for day in ("2026-11-16", "2026-11-17", "2026-11-05", "2026-11-06"):
    f = dict(hist["US"][day]["factors"])
    base = engine.market_state(rows("US", f), "US")
    f2 = dict(f, credit_spread=0.5)
    mid = engine.market_state(rows("US", f2), "US")
    f3 = dict(f); f3.pop("credit_spread")
    wo = engine.market_state(rows("US", f3), "US")
    out[f"US {day} live / credit at 0.5 / credit absent"] = [round(base["score_100"], 1), base["state"], round(mid["score_100"], 1), mid["state"], round(wo["score_100"], 1), wo["state"]]
# 5. stance x market state: the factors and caps the plan is built with
adverse = engine.market_state(rows("US", hist["US"]["2026-11-20"]["factors"]), "US")
fav = engine.market_state(us(vix_regime=0.8, vix_term=0.8, credit_spread=0.8, index_trend_breadth=0.8), "US")
kr = engine.market_state(rows("KR", hist["KR"]["2026-11-20"]["factors"]), "KR")
for name, st in (("US adverse", adverse), ("US favourable", fav), ("KR adverse", kr)):
    for lv in stance.LEVELS:
        _, used, shown = stance.for_plan([], st, {}, lv, op.STRATEGY_OF)
        out[f"stance {lv} x {name}"] = {"size_factor": used["size_factor"], "new_exposure_cap": used["new_exposure_cap"]}
# 6. what the plan does with it: synthetic account, 30 synthetic candidates (random-free: fixed numbers)
cands = [{"ticker": f"T{i:02d}", "name": None, "sector": f"S{i % 6}", "style": "LONG" if i % 2 else "SWING", "score": 80 - i * 0.5, "band": "BUY_CANDIDATE", "close": 100.0, "atr": 2.0,
          "stop": 96.0 if i % 2 == 0 else 90.0, "target": 110.0, "adv_value": 5e8, "session": "X"} for i in range(30)]
acct = {"equity": 100000.0, "cash": 100000.0, "positions": {}}
for mk, name, st in (("US", "US adverse", adverse), ("US", "US favourable", fav), ("KR", "KR adverse", kr)):
    for lv in stance.LEVELS:
        _, used, _ = stance.for_plan(cands, st, {}, lv, op.STRATEGY_OF)
        p = op.build(cands, acct, mk, None, used)
        out[f"plan {lv} x {name}"] = {"orders": len(p["orders"]), "new_exposure_pct": round(p["new_exposure_pct"], 1), "max_weight_pct": round(max(o["weight_pct"] for o in p["orders"]), 1) if p["orders"] else None,
                                     "max_risk_pct": round(max(o["risk_pct"] for o in p["orders"]), 2) if p["orders"] else None, "skipped": p["skipped_counts"]}
# 7. the paper portfolios' exposure steps
for v in (None, 15.4, 25.4, 34.9, 35.0, 49.9, 50.0):
    out[f"exposure state={v}"] = {"druckenmiller": portfolios.exposure(v, portfolios.D_EXPOSURE), "committee": portfolios.exposure(v, portfolios.C_EXPOSURE)}
print(json.dumps(out, ensure_ascii=False, indent=1))
(Path(__file__).parent / "in_memory_checks.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
