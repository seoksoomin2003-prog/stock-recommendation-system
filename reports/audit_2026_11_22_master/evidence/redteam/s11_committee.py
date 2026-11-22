from common import *
sys.path.insert(0, REPO + "/tests")
import committee_cases as cc
from terminal.committee import figures as fg, investors as iv, council, portfolios, record
CODE = {"STRONG_BUY": "S", "BUY": "B", "HOLD": "H", "WAIT": "W", "REDUCE": "R", "SELL": "X", "AVOID": "A", "INSUFFICIENT_DATA": "N", "CONDITIONAL_BUY": "C"}
fired = []
def check(name, cond, detail=""):
    print(f"[{'FIRES' if cond else 'holds'}] {name} {detail}")
    if cond: fired.append(name)
def run(held=None, ctx=None, **over):
    f = cc.figures(**over)
    ops = iv.evaluate(f, held, ctx)
    d = council.decide(f, ops, bool((held or {}).get("COMMITTEE")))
    return f, {o["investor"]: o for o in ops}, d
def line(tag, ops, d):
    print(f"   {tag}: [{''.join(CODE[ops[k]['recommendation']] for k in iv.ORDER)}] committee {d['decision']} conf {d['scores']['confidence']} attract {d['scores']['attractiveness']} data {d['scores']['data']} risks {[(r['level'][:4], r['name']) for r in d['material_risks']]}")

print("== base stock"); f, o, d = run(); line("BASE", o, d)

print("\n== T1 price a hair under/over the 200-day average (ma200=90)")
for p in (90.01, 89.99):
    f, o, d = run(price=p); line(f"price {p}", o, d); print("      Druckenmiller:", o["DRUCKENMILLER"]["recommendation"], o["DRUCKENMILLER"]["score"])
_, o1, d1 = run(price=90.01); _, o2, d2 = run(price=89.99)
check("T1 a 0.02% price change flips Druckenmiller between buy-side and AVOID", (o1["DRUCKENMILLER"]["recommendation"] in iv.BUY_SIDE) and o2["DRUCKENMILLER"]["recommendation"] == "AVOID", f"({o1['DRUCKENMILLER']['recommendation']} -> {o2['DRUCKENMILLER']['recommendation']}; committee {d1['decision']} -> {d2['decision']})")

print("\n== T2 debt/equity 2.99 vs 3.01 with interest cover 1.4 (material-risk veto)")
for de in (2.99, 3.01):
    f, o, d = run(debt_equity=de, interest_cover=1.4); line(f"D/E {de}", o, d)
_, _, a = run(debt_equity=2.99, interest_cover=1.4); _, _, b = run(debt_equity=3.01, interest_cover=1.4)
check("T2 D/E 2.99 -> 3.01 changes the committee decision", a["decision"] != b["decision"], f"({a['decision']} -> {b['decision']})")
for de in (2.99, 3.01):
    f, o, d = run(debt_equity=de, interest_cover=1.4, eps_cagr3=0.30, rev_growth=0.3, eps_growth=0.35, roe=0.6, op_margin=0.4, gross_margin=0.7, pe=14, pb=1.2, fcf_yield=0.08); line(f"strong business, D/E {de}", o, d)

print("\n== T3 PER 60 vs 60.1 (fast grower so that some views still buy)")
res = {}
for pe in (60.0, 60.1):
    f, o, d = run(pe=pe, trailing_pe=pe, forward_pe=40, eps_cagr3=0.45, rev_cagr3=0.4, rev_growth=0.4, eps_growth=0.5, roe=0.45, op_margin=0.35, gross_margin=0.7, sector="기술", market_cap=5e9, dividend_yield=0.0)
    line(f"PER {pe}", o, d); res[pe] = d
check("T3 PER 60 -> 60.1 changes the committee decision", res[60.0]["decision"] != res[60.1]["decision"], f"({res[60.0]['decision']} -> {res[60.1]['decision']})")

print("\n== T4 Lynch: a company that has lost money in every year on file, with sales growth and cash")
f, o, d = run(pe=-15.0, trailing_pe=None, forward_pe=None, eps_growth=None, eps_cagr3=None, profit_years=0.0, roe=-0.2, op_margin=-0.1, rev_growth=0.20, rev_cagr3=0.2, fcf_margin=0.09, debt_equity=0.2, cash_debt=1.5, current_ratio=2.5, ocf_to_ni=None)
line("perennial loss-maker", o, d); L = o["LYNCH"]
print("      Lynch:", L["recommendation"], L["score"], "confidence", L["confidence"], "kind", L.get("category"), "|", L["opinion"][:150])
check("T4 Lynch recommends buying a company with no profitable year and no earnings-growth figure as a 'turnaround'", L["recommendation"] in iv.BUY_SIDE)

print("\n== T5 Graham edge cases")
f, o, d = run(pe=1.0, pb=0.2, trailing_pe=1.0); G = o["GRAHAM"]
print("   PER 1.0, PBR 0.2:", G["recommendation"], "mos", G.get("margin_of_safety"), "expected_return", G["expected_return"]["value"])
check("T5a Graham reports an 'expected return' above +500% from a one-off PER", (G["expected_return"]["value"] or 0) > 5, f"(value {G['expected_return']['value']})")
f, o, d = run(pe=-40.0, pb=1.1, sector="부동산", trailing_pe=None); G = o["GRAHAM"]
print("   REIT with negative GAAP PER, PBR 1.1:", G["recommendation"], "|", G["opinion"][:70], "| method:", G.get("method"))
check("T5b a REIT with negative GAAP earnings is called a loss-maker (AVOID) although the engine's own REIT rule says earnings are distorted and reads PBR", G["recommendation"] == "AVOID" and G.get("method", "").startswith("적자"))
f, o, d = run(pe=10.0, pb=None, debt_equity=99.0, roe=None); G = o["GRAHAM"]
print("   negative equity (D/E mark 99), PER 10:", G["recommendation"], "| method:", G.get("method"), "| no_equity:", f["no_equity"])
check("T5c a negative-equity company is valued by the 'asset-light industry' method label", "자산이 가벼운" in (G.get("method") or ""))

print("\n== T6 one STRONG_BUY against four AVOID")
f, o, d = run(roe=0.07, op_margin=0.06, gross_margin=0.2, profit_years=0.75, fcf_margin=0.02, pe=30.0, pb=3.5, trailing_pe=30, forward_pe=22, eps_cagr3=0.02, rev_cagr3=0.01, rev_growth=0.16, eps_growth=0.30, fcf_yield=0.01,
              dividend_yield=0.0, returns_capital=False, current_ratio=1.1, rs=0.97, ret_12_1=0.6, rel_126=0.3, state=75.0, reward_risk=2.6, events_positive=2, max_drawdown=-0.12, hist_vol=0.2, debt_equity=1.1)
line("weak business, strong trend", o, d); print("     ", d["reasons"][0][:160])
check("T6 one view's STRONG_BUY outvotes three or four AVOID (compelling-lead rule is tested before the three-against rule)", d["decision"] == "CONDITIONAL_BUY" and len(d["against"]) >= 3, f"(buyers {d['buyers']}, against {d['against']})")

print("\n== T7 missing figures and the engines' scores (low figures made absent)")
low = dict(op_margin=0.05, fcf_margin=0.0, gross_margin=0.2, eps_cagr3=-0.05, rev_cagr3=-0.01, fcf_years=0.4, cash_debt=0.05, interest_cover=1.5, share_change=0.04, returns_capital=False, fcf_yield=0.01)
f, o, d = run(**low); line("low figures present", o, d); b1 = o["BUFFETT"]
f, o, d = run(**{k: None for k in low}); line("the same figures absent", o, d); b2 = o["BUFFETT"]
print(f"      Buffett score {b1['score']} ({b1['recommendation']}, confidence {b1['confidence']}, coverage {b1['coverage']}) -> {b2['score']} ({b2['recommendation']}, confidence {b2['confidence']}, coverage {b2['coverage']})")
check("T7 Buffett score rises and the recommendation improves when weak figures are absent", (b2["score"] or 0) > (b1["score"] or 0) and b2["recommendation"] in iv.BUY_SIDE and b1["recommendation"] not in iv.BUY_SIDE)

print("\n== T8 thin financial: a bank judged on ROE, PER, PBR and little else")
f, o, d = run(sector="금융", roe=0.17, pe=9.0, pb=1.0, trailing_pe=9, forward_pe=8.5, eps_cagr3=None, rev_cagr3=None, rev_growth=None, eps_growth=None, insider_pct=None, insider_buy=None, insider_sell=None, share_change=None,
              returns_capital=None, dividend_yield=None, market_cap=None, events_negative=None, events_positive=None, issues=())
line("thin bank", o, d)
for k in iv.ORDER:
    print(f"      {k:14s} {o[k]['recommendation']:18s} score {o[k]['score']} confidence {o[k]['confidence']} coverage {o[k]['coverage']} figures {len(o[k]['evidence'])}")

print("\n== T9 dividend yield 8.0 vs 8.01 (Yahoo per cent), a slow grower")
for dy in (8.0, 8.01):
    f, o, d = run(dividend_yield=dy, eps_cagr3=0.02, rev_cagr3=0.01, pe=11, trailing_pe=11, pb=1.6)
    print(f"   yield {dy}: read as {f['dividend_yield']} status {f['_status']['dividend_yield']} | Lynch {o['LYNCH']['recommendation']} ({o['LYNCH'].get('category')}) | Graham {o['GRAHAM']['recommendation']}")
print("   Lynch PEG check: PER 18, g 12%, yield 1.5% ->", iv.lynch(cc.figures())["peg"], "(18 / (12 + 1.5) = 1.33)")

print("\n== T10 risk-off notch: market state 35.0 vs 34.9")
for st in (35.0, 34.9):
    f, o, d = run(state=st); print(f"   state {st}: Druckenmiller {o['DRUCKENMILLER']['recommendation']} weight {o['DRUCKENMILLER']['suggested_weight']} | committee {d['decision']}")

print("\n== T11 portfolio construction")
def book_of(n, sector, **over):
    b = {}
    for i in range(n):
        f = cc.figures(ticker=f"S{i:02d}", sector=sector, hist_vol=0.2 + 0.01 * i, **over)
        ops = iv.evaluate(f, None, None)
        b[f["ticker"]] = {"ticker": f["ticker"], "name": f["ticker"], "sector": f["sector"], "as_of": f["as_of"], "figures": f, "opinions": {x["investor"]: x for x in ops}, "committee": council.decide(f, ops)}
    return b
bk = book_of(20, "산업재"); print("   committee decision of the base stock:", bk["S00"]["committee"]["decision"])
p1 = portfolios.committee_portfolio(bk, None, 60.0); p2 = portfolios.committee_portfolio(book_of(20, None), None, 60.0)
print(f"   20 identical buy candidates in ONE named sector: holdings {p1['count']}, invested {p1['invested']}, sectors {p1['sectors']}")
print(f"   the same 20 with sector = None:                 holdings {p2['count']}, invested {p2['invested']}, sectors {p2['sectors']}")
check("T11a with no sector label the per-sector count (3) and weight (30%) limits do not apply", p2["count"] > p1["count"] and p2["invested"] > 0.3 + 1e-9)
for k in ("BUFFETT", "LYNCH"):
    a, b_ = portfolios.investor_portfolio(k, bk), portfolios.investor_portfolio(k, book_of(20, None))
    print(f"   {k}: one sector -> {a['count']} holdings; sector None -> {b_['count']} holdings invested {b_['invested']}")
w = portfolios._fit({f"T{i}": 0.0874 for i in range(12)}, 0.12, 1.0)
print("   _fit 12 x 0.0874 (sum 1.0488) under total 1.0 ->", round(sum(w.values()), 4), "each", w["T0"])
check("T11b _fit can return weights that add to more than the total (rounding each weight to 4 places)", sum(w.values()) > 1.0)
# crash: worst market state, every engine but Druckenmiller
for st in (0.0, 34.0, 49.0, 50.0, None):
    out = portfolios.build(bk, None, st, None)
    print(f"   market state {st}: invested " + ", ".join(f"{k[:4]} {p['invested']:.2f}" for k, p in out.items()))

print("\n== T12 paper performance: record.performance")
def rows_for(weights_by_day):
    return [{"session": d, "portfolios": {"X": {"cash": 1 - sum(w.values()), "holdings": w}}} for d, w in weights_by_day]
days = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"]
px = {"AAA": dict(zip(days, [100, 100, 100, 45, 45, 45])), "BBB": dict(zip(days, [50, 50, 50, 50, 50, 50]))}
perf = record.performance(rows_for([(d, {"AAA": 0.5, "BBB": 0.5}) for d in days]), lambda t, s: px[t].get(s), lambda s: 100.0, 0.0)
st = perf["portfolios"]["X"]
print("   AAA (50% weight) falls 100 -> 45 in one day and stays there: total_return", st["total_return"], "price_breaks", st["price_breaks"])
check("T12a a real one-day fall of 55% in a 50% position is left out of the paper return (true loss -27.5%)", abs(st["total_return"]) < 1e-9)
px2 = {"AAA": dict(zip(days[:3], [100, 100, 100])), "BBB": dict(zip(days, [50] * 6))}       # AAA stops trading (delisted): no price afterwards
perf = record.performance(rows_for([(d, {"AAA": 0.5, "BBB": 0.5}) for d in days]), lambda t, s: px2[t].get(s), lambda s: 100.0, 0.0)
st = perf["portfolios"]["X"]
print("   AAA has no price after day 3 (halted / delisted): total_return", st["total_return"], "unpriced", st["unpriced"])
check("T12b a holding whose price disappears earns exactly 0 from then on (no loss booked)", abs(st["total_return"]) < 1e-9 and st["unpriced"] == ["AAA"])
# the lag: weights of row i must earn sessions[i+1] -> sessions[i+2]
px3 = {"AAA": dict(zip(days, [100, 110, 121, 121, 121, 121]))}
perf = record.performance(rows_for([(days[0], {"AAA": 1.0})] + [(d, {}) for d in days[1:]]), lambda t, s: px3[t].get(s), lambda s: 100.0, 0.0, keep_daily=True)
print("   held only in the record of day 1; AAA +10% on day 2 and +10% on day 3 -> daily", perf["portfolios"]["X"]["daily"])
check("T12c the lag is not as documented (row i should earn day i+1 -> i+2 only)", [round(x, 4) for x in perf["portfolios"]["X"]["daily"]] != [0.1, 0.0, 0.0, 0.0])
print("\nFIRED:", len(fired)); [print("  -", x) for x in fired]
