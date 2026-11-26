# Order-plan arithmetic on recorded 2026-11-25 candidates with MADE-UP capital (not the user's).  No returns computed.
import collections
from pathlib import Path
from terminal.qsf.ledger import Ledger
from terminal.qsf import config, engine, order_plan as op, stance
from terminal import portfolio as pf
led = Ledger(Path(".").resolve())
S = "2026-11-25"
def run(market, equity, state, label, settings=None, cands=None):
    snaps = op.session_snaps(led, market, S)
    cands = cands if cands is not None else op.candidates(snaps, S, None, settings)
    plan = op.build(cands, {"equity": equity, "cash": equity, "positions": {}}, market, settings, state)
    o = plan["orders"]
    print(f"\n[{market}] {label}: made-up equity {equity:,.0f}; candidates {plan['candidates']}; orders {len(o)}; new exposure {plan['new_exposure_pct']:.1f}%; cash left {plan['cash_after']/equity*100:.1f}%; skipped {plan['skipped_counts']}")
    print("   by style:", dict(collections.Counter(x['style'] for x in o)), "binding:", dict(collections.Counter(x['binding'] for x in o)))
    tot_risk = tot_risk_lim = 0
    for x in o:
        risk_lim = x["shares"] * (x["limit"] - x["stop"]) / equity * 100          # the same shares filled at the plan's own cap
        tot_risk += x["risk_pct"]; tot_risk_lim += risk_lim
        lim = pf.limits_for(x["style"], settings or pf.DEFAULT_SETTINGS, market)
        f = float((state or {}).get("size_factor") or 1.0)
        assert x["weight_pct"] <= lim["max_position_pct"] * f + 1e-6, x
        assert x["risk_pct"] <= lim["risk_per_trade_pct"] * f + 1e-6, x
        print(f"   {x['ticker']:7s} {x['style']:5s} score {x['score']:5.1f} w {x['weight_pct']:5.2f}% stopdist {100*(x['ref_close']-x['stop'])/x['ref_close']:5.2f}% risk@close {x['risk_pct']:.3f}% risk@limit {risk_lim:.3f}% bind {x['binding']:8s} part {x['participation_pct']:.3f}% rt_cost {x['est_round_trip_pct']:.2f}% limit {x['limit']:.4f} -> order price {op.order_price(market, x['limit'])}")
    print(f"   sum of stop risk: at close {tot_risk:.2f}% of equity; if every order fills at its cap {tot_risk_lim:.2f}%;  names {len(o)}; largest weight {max((x['weight_pct'] for x in o), default=0):.1f}%")
    return plan
for market, eq in (("US", 100_000.0), ("KR", 100_000_000.0)):
    snaps = op.session_snaps(led, market, S)
    st_rec = op.state_for_plan(snaps, market, S)
    fav = {**st_rec, "state": "FAVOURABLE", "size_factor": 1.0, "new_exposure_cap": None}
    run(market, eq, st_rec, f"recorded state {st_rec['state']} {st_rec['score_100']:.1f} (factor {st_rec['size_factor']}, cap {st_rec['new_exposure_cap']})")
    run(market, eq, fav, "same candidates, as if the day were FAVOURABLE")
    for lv in ("DEFENSIVE", "AGGRESSIVE"):
        c = op.candidates(snaps, S, None, None)
        kept, used, shown = stance.for_plan(c, st_rec, stance.marks(snaps, lv), lv, op.STRATEGY_OF)
        run(market, eq, used, f"stance {lv} (size_factor_total {shown['size_factor_total']}, cap {used['new_exposure_cap']}, left out {shown['left_out']})", cands=kept)
# small account: the 1% minimum and whole shares
run("US", 3_000.0, None, "small made-up account, no state")
# tick checks
for p in (1999.4, 2003, 19999, 20004, 49999, 50049, 199950, 200099, 499999, 500499, 1234567):
    q = op.order_price("KR", p); t = op.tick_size("KR", q)
    assert q <= p and abs(q / t - round(q / t)) < 1e-9, (p, q, t)
print("\nKR tick rounding: all on grid and <= cap;  US:", op.order_price("US", 123.4567), op.order_price("US", 0.98765))
print("round trip cost", {m: round(config.round_trip_cost(m)*100, 4) for m in ("US","KR")}, "fees only", {m: round(config.fees_only(m)*100, 4) for m in ("US","KR")})
# the swing reward/risk bound with no resistance: (3ATR - c)/(2ATR + c) < 1.5 for every c >= 0
for atrp in (0.01, 0.02, 0.05):
    for m in ("US", "KR"):
        c = config.round_trip_cost(m)
        print(f"   no-resistance RR  market {m} ATR {atrp:.0%}: {(3*atrp - c)/(2*atrp + c):.3f}  (entry rule needs {config.SWING['min_reward_risk']})")
