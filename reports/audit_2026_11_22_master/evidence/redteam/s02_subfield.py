from common import *
up = bars(drift=0.0016, vol=0.011, seed=3, volume=5e7)       # strong, steady up-trend
print("bars: n", len(up), "first", round(up[0]["close"], 1), "last", round(up[-1]["close"], 1))

BAD = dict(GOOD_FUND, roe=0.03, roe_prev=0.12, op_margin=0.02, gross_margin=0.18, net_margin=0.01, rev_growth=-0.12, eps_growth=-0.45, rev_cagr3=-0.06, eps_cagr3=-0.20,
           ocf_to_ni=0.3, fcf=-1.0, fcf_margin=-0.06, fcf_years_positive=0.25, roe_years_positive=0.75, debt_equity=2.8, current_ratio=0.9, interest_cover=1.3, cash_debt=0.04,
           equity_assets=0.2, share_change=0.06, returns_capital=False, pe=35.0, pb=1.2, fcf_yield=-0.04, eps=1.0, insider_pct=0.001)
print("\n=== 3a. deteriorating fundamentals + strong momentum (all data present) ===")
for strat in ("SWING", "LONG_TERM"):
    r = engine.score(ctx("US", up, fund=dict(BAD), rs_rank=0.92), strat)
    e = holding.entry_status(r, ctx("US", up, fund=dict(BAD), rs_rank=0.92))
    print(strat, brief(r), "| entry:", e["status"])
    print("   domains:", {d: (None if v["score_100"] is None else round(v["score_100"], 1)) for d, v in r["domains"].items()})
    print("   factors:", {x["factor"]: (None if x["normalized"] is None else round(x["normalized"], 2)) for x in r["factors"] if x.get("scored", True) is not False})

print("\n=== 1b/2. the same deteriorating company with the BAD sub-fields simply absent (None) ===")
# keep only one good-looking sub-field per factor; drop the bad ones
THIN = dict(status="REAL", source="synthetic", filed="2026-02-15", is_financial=False,
            gross_margin=0.55,              # business_quality: only gross margin (roe, op_margin, years positive absent)
            pb=1.2,                          # valuation: only PBR (PER, FCF yield absent)
            rev_cagr3=0.16,                  # growth_quality: only an old 3y CAGR (latest growth absent)
            fcf_years_positive=1.0,          # free_cash_flow: only the years-positive share
            share_change=-0.02,              # balance_dilution + capital_allocation
            current_ratio=2.1,               # financial_resilience + balance_sheet
            debt_equity=0.3, returns_capital=True, insider_pct=0.12, op_margin=0.25, rev_growth=None)
n_fields = sum(1 for k, v in THIN.items() if k not in ("status", "source", "filed", "is_financial") and v is not None)
for strat in ("LONG_TERM", "SWING"):
    c = ctx("US", up, fund=dict(THIN), rs_rank=0.92)
    r = engine.score(c, strat)
    e = holding.entry_status(r, c)
    print(strat, brief(r), "| entry:", e["status"])
    print("   factors:", {x["factor"]: (None if x["normalized"] is None else round(x["normalized"], 2)) for x in r["factors"] if x["domain"] in ("FUNDAMENTAL", "RISK", "EVENTS") and x.get("scored", True) is not False})
# how many of the sub-fields the fundamental/risk/event factors READ were actually there?
READ = {"valuation": ("pe", "pb", "fcf_yield"), "business_quality": ("roe", "op_margin", "gross_margin", "roe_years_positive"), "growth_quality": ("rev_cagr3", "eps_cagr3", "rev_growth"),
        "free_cash_flow": ("fcf_margin", "fcf_years_positive"), "balance_dilution": ("debt_equity", "share_change"), "financial_resilience": ("current_ratio", "interest_cover", "cash_debt"),
        "leverage": ("debt_equity",), "capital_allocation": ("share_change", "returns_capital")}
w = config.profile_for("US", "LONG_TERM")["domains"]
tot = have = 0.0
for f, keys in READ.items():
    weight = next(ws[f] for ws in w.values() if f in ws)
    tot += weight; have += weight * sum(THIN.get(k) is not None for k in keys) / len(keys)
print(f"   distinct fundamental figures supplied: {n_fields}; weight-averaged share of fundamental sub-fields present: {have / tot:.2f}; engine coverage reported above")

print("\n=== 3b. excellent company at PER 80 ===")
DEAR = dict(GOOD_FUND, roe=0.35, op_margin=0.35, gross_margin=0.70, rev_growth=0.25, eps_growth=0.30, rev_cagr3=0.22, eps_cagr3=0.25, pe=80.0, pb=25.0, fcf_yield=0.011, fcf_margin=0.28)
for strat in ("LONG_TERM", "SWING"):
    c = ctx("US", up, fund=dict(DEAR), rs_rank=0.92)
    r = engine.score(c, strat); e = holding.entry_status(r, c)
    print(strat, brief(r), "| entry:", e["status"], "|", e["reason"])
    print("   valuation factor:", next(round(x["normalized"], 3) for x in r["factors"] if x["factor"] == "valuation") if strat == "LONG_TERM" else "(not in swing)")
# P/E 80 but PBR and FCF yield not available (e.g. negative equity -> pb None; capex tag stopped -> fcf None)
DEAR2 = dict(DEAR, pb=None, fcf_yield=None)
c = ctx("US", up, fund=DEAR2, rs_rank=0.92); r = engine.score(c, "LONG_TERM")
print("PER 80, pb/fcf_yield None:", brief(r), "| entry:", holding.entry_status(r, c)["status"])
# PER absent (COUNT_UNKNOWN / other currency), PBR 25, FCF yield 1.1%
DEAR3 = dict(DEAR, pe=None)
c = ctx("US", up, fund=DEAR3, rs_rank=0.92); r = engine.score(c, "LONG_TERM")
print("PER None, pb 25, fcf 1.1%:", brief(r), "| valuation", next(round(x["normalized"], 3) for x in r["factors"] if x["factor"] == "valuation"), "| entry:", holding.entry_status(r, c)["status"])
