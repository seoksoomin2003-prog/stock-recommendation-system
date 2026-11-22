"""Newest session: which snapshots the order plan takes as candidates, by the score's own action word.  Session closes only; no forward price."""
from common import *
from pathlib import Path
from collections import Counter
from terminal.qsf.ledger import Ledger
from terminal.qsf import order_plan
led = Ledger(Path(REPO)); rows = led._live_rows()
for market in ("US", "KR"):
    last = max(r["session"] for r in rows if r["market"] == market)
    snaps = [s for r in rows if r["market"] == market and r["session"] == last for s in led._load(r)]
    cands = order_plan.candidates(snaps, last)
    act = {(s["ticker"], order_plan.STYLE_OF[s["strategy"]]): s for s in snaps if s.get("data_date") == last}
    tab = Counter((c["style"], act[(c["ticker"], c["style"])]["action"], act[(c["ticker"], c["style"])]["confidence"]) for c in cands)
    print(f"{market} {last}: order-plan candidates {len(cands)} -> (style, score's action word, confidence): {dict(tab)}")
    print("   count_by:", order_plan.count_by(cands), "| lowest candidate score:", min((c["score"] for c in cands), default=None))
    eq = 100_000.0 if market == "US" else 100_000_000.0
    st = order_plan.market_state(snaps, market, last)
    plan = order_plan.build(cands, {"equity": eq, "cash": eq, "positions": {}}, market, None, st)
    orders = plan["orders"]
    print(f"   synthetic account (all cash): market state {st['score_100']:.1f} {st['state']} size factor {plan['size_factor']} -> orders {len(orders)}, invested {sum(o['notional'] for o in orders) / eq * 100:.1f}% of equity;"
          f" orders whose score is under the buy line 70: {sum(1 for o in orders if o['score'] < 70)}; scores {[o['score'] for o in orders][:14]}")
