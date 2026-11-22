from common import *
import copy
from terminal.committee import figures as fg, investors as iv, council
from terminal import assistant
BAD = dict(GOOD_FUND, roe=0.03, roe_prev=0.12, op_margin=0.02, gross_margin=0.18, net_margin=0.01, rev_growth=-0.12, eps_growth=-0.45, rev_cagr3=-0.06, eps_cagr3=-0.20,
           ocf_to_ni=0.3, fcf=-1.0, fcf_margin=-0.06, fcf_years_positive=0.25, roe_years_positive=0.75, debt_equity=2.8, current_ratio=0.9, interest_cover=1.3, cash_debt=0.04,
           equity_assets=0.2, share_change=0.06, returns_capital=False, pe=35.0, pb=1.2, fcf_yield=-0.04, eps=1.0, insider_pct=0.001)
print("== 3. deteriorating fundamentals (sales -12%, EPS -45%, D/E 2.8, FCF negative): search price paths for a swing BUY ==")
hits = []
for seed in range(1, 80):
    b = bars(drift=0.0014, vol=0.010, seed=seed, volume=5e7)
    # a pull-back of a few per cent from the high so that a resistance level sits above the price
    c = ctx("US", b, fund=dict(BAD), rs_rank=0.95)
    r = engine.score(c, "SWING")
    if r["score"] >= 70 and r["action"] == "BUY":
        hits.append((float(r["score"]), seed, holding.entry_status(r, c)["status"]))
hits.sort(reverse=True)
print(f"   {len(hits)} of 79 random up-trend paths give swing BUY for this company; best: {[(round(s, 1), seed, e) for s, seed, e in hits[:5]]}")
print("   of them entry ENTRY_NOW:", [(round(s, 1), seed) for s, seed, e in hits if e == "ENTRY_NOW"][:5])
seed = (next((sd for s, sd, e in hits if e == "ENTRY_NOW"), None) or hits[0][1]) if hits else 3
b = bars(drift=0.0014, vol=0.010, seed=seed, volume=5e7)
c = ctx("US", b, fund=dict(BAD), rs_rank=0.95)
cards = {s: engine.score(c, s) for s in ("SWING", "LONG_TERM")}
for s, r in cards.items():
    print(f"   seed {seed} {s}: score {r['score']:.1f} band_label '{r['band_label']}' action_label '{r['action_label']}' conf {r['confidence']} entry {holding.entry_status(r, c)['status']} | FUNDAMENTAL domain {r['domains']['FUNDAMENTAL']['score_100']:.1f} TECHNICAL {r['domains']['TECHNICAL']['score_100']:.1f}")
print("\n== 10. the SAME cards read by the committee, as terminal/committee/service.py::stock does for a stock outside the scan ==")
snap = lambda r: {**r, "ticker": "SYN"}
f = fg.read(snap(cards["LONG_TERM"]), snap(cards["SWING"]), {"marketCap": 5e10, "trailingPE": 35.0, "forwardPE": 40.0, "dividendYield": 0.0, "industry": "Machinery"}, "산업재")
ops = iv.evaluate(f); d = council.decide(f, ops)
print("   five views:", {o["name"]: o["recommendation_ko"] for o in ops})
print("   committee:", d["decision_ko"], "| risks:", [(r["level"], r["name"]) for r in d["material_risks"]])
print(f"   => one screen: QSF swing '{cards['SWING']['action_label']}' ({cards['SWING']['score']:.0f}) beside committee '{d['decision_ko']}'")

print("\n== 6. the 99.0 'no equity' mark in the assistant's sector comparison (assistant.sector_lines) ==")
peers = {"status": "REAL", "peers": [{"ticker": t, "ratios": {"debt_equity": v}} for t, v in (("A", 0.3), ("B", 0.6), ("C", 0.9), ("D", 99.0), ("E", 99.0), ("F", 99.0))]}
for t in ("C", "D"):
    print(f"   {t}:", [x for x in assistant.sector_lines(peers, t) if "부채" in x])
