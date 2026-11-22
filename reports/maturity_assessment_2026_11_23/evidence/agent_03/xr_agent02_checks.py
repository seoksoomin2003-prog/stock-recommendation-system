"""Agent 03 cross-review of Agent 02: counterfactual readings on the stored inputs (big/cards_151.json, 2026-11-20, today's code).
Scores and factor values only; no return, IC or performance figure."""
import json, sys
from pathlib import Path
import pandas as pd
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.resolve().parents[3]))
from terminal.qsf import factors
D = json.loads((HERE / "big" / "cards_151.json").read_text(encoding="utf-8"))
FUND = ("earnings_revenue_quality", "profitability", "balance_sheet", "cash_flow_quality", "valuation", "business_quality", "growth_quality", "free_cash_flow", "balance_dilution", "financial_resilience", "leverage", "capital_allocation")


def rescore(card, fund=None, override=None):
    w = c = 0.0
    for f in card["factors"]:
        if f.get("scored") is False:
            continue
        st, x = f["status"], f["normalized"]
        if fund is not None and f["factor"] in FUND:
            o = factors.CALC[f["factor"]]({"fund": fund})
            st, x = o["status"], o.get("normalized")
        if override and f["factor"] in override:
            st, x = ("REAL", override[f["factor"]]) if override[f["factor"]] is not None else ("MISSING", None)
        if st in ("REAL", "STALE") and x is not None:
            w, c = w + f["weight"], c + f["weight"] * x
    return 100 * c / w


out = {}
# (a) PHM: debt read as total liabilities (upper bound, stored figures: liabilities 5,063.0, equity 12,985.4, cash 1,980.9, USD million)
phm = D["US"]["cards"]["PHM|LONG_TERM"]
base = rescore(phm, phm["fund"])
ub = dict(phm["fund"], debt_equity=5063.0 / 12985.4, cash_debt=1980.9 / 5063.0)
mid = dict(phm["fund"], debt_equity=1600.0 / 12985.4, cash_debt=1980.9 / 1600.0)      # an ASSUMED 1.6 bn of notes (not in the stored data)
out["PHM"] = {"recorded": phm["score"], "recomputed": base, "debt_as_total_liabilities": rescore(phm, ub), "assumed_1_6bn_notes": rescore(phm, mid),
              "debt_factors_missing": rescore(phm, phm["fund"], {"leverage": None, "balance_dilution": None, "financial_resilience": None}),
              "debt_factors_at_0_5": rescore(phm, phm["fund"], {"leverage": 0.5, "balance_dilution": 0.5, "financial_resilience": 0.5})}
# (b) the nine US non-financial names with debt/equity < 0.02
rows = {}
for c in D["US"]["cards"].values():
    f = c["fund"]
    if c["strategy"] == "LONG_TERM" and not f.get("is_financial") and f.get("debt_equity") is not None and f["debt_equity"] < 0.02:
        ea = f.get("equity_assets")
        le = (1 / ea - 1) if ea else None
        rows[c["ticker"]] = {"score": round(c["score"], 1), "band": c["band"], "interest_cover": f.get("interest_cover"), "liab_over_equity": None if le is None else round(le, 2),
                             "score_debt_factors_at_0_5": round(rescore(c, f, {"leverage": 0.5, "balance_dilution": 0.5, "financial_resilience": 0.5}), 1),
                             "score_debt_factors_missing": round(rescore(c, f, {"leverage": None, "balance_dilution": None, "financial_resilience": None}), 1)}
out["low_debt_nine"] = rows
# (c) operating cash flow over net income: not computed when it is above 3 (a thin profit), instead of full credit
for market in ("US", "KR"):
    for strat in ("SWING", "LONG_TERM"):
        a, b, n_hit = {}, {}, 0
        for c in D[market]["cards"].values():
            if c["strategy"] != strat or c["score"] is None:
                continue
            f = c["fund"]
            a[c["ticker"]] = c["score"]
            if f.get("ocf_to_ni") is not None and f["ocf_to_ni"] > 3:
                n_hit += 1
                b[c["ticker"]] = rescore(c, dict(f, ocf_to_ni=None))
            else:
                b[c["ticker"]] = c["score"]
        s0, s1 = pd.Series(a), pd.Series(b)
        d = s1 - s0
        out[f"ocf_{market}_{strat}"] = {"cards_with_ratio_gt3": n_hit, "scores_changed": int((d.abs() > 1e-9).sum()), "max_down": round(float(d.min()), 2), "max_up": round(float(d.max()), 2),
                                        "median_change_of_changed": round(float(d[d.abs() > 1e-9].median()), 2) if (d.abs() > 1e-9).any() else None,
                                        "rho": round(float(pd.concat([s0, s1], axis=1).corr(method="spearman").iloc[0, 1]), 5), "cross_70": int(((s0 >= 70) != (s1 >= 70)).sum()), "cross_55": int(((s0 >= 55) != (s1 >= 55)).sum())}
# (d) long-term 'enter now' cards of companies that are shrinking, by a few plain definitions
for market in ("US", "KR"):
    L = [c for c in D[market]["cards"].values() if c["strategy"] == "LONG_TERM" and c["score"] is not None]
    en = [c for c in L if c["entry_status"] == "ENTRY_NOW" and c["actionability"] == "ACTIONABLE"]
    def neg(c, k):
        v = c["fund"].get(k)
        return v is not None and v < 0
    defs = {"loss_now": lambda c: bool(c["fund"].get("loss_now")), "rev_growth<0": lambda c: neg(c, "rev_growth"), "eps_growth<0": lambda c: neg(c, "eps_growth"),
            "rev_growth<0 and eps_growth<0": lambda c: neg(c, "rev_growth") and neg(c, "eps_growth"), "rev_cagr3<0 and rev_growth<0": lambda c: neg(c, "rev_cagr3") and neg(c, "rev_growth"),
            "rev_cagr3<0 and rev_growth<0 and (loss or eps_growth<0)": lambda c: neg(c, "rev_cagr3") and neg(c, "rev_growth") and (bool(c["fund"].get("loss_now")) or neg(c, "eps_growth"))}
    out[f"entry_{market}"] = {"long_cards": len(L), "enter_now": len(en), **{k: {"all": sum(1 for c in L if fn(c)), "enter_now": sum(1 for c in en if fn(c)), "enter_now_ge70": sum(1 for c in en if fn(c) and c["score"] >= 70)} for k, fn in defs.items()},
                              "growth_quality_mean_enter_now": round(sum(next(f["normalized"] or 0 for f in c["factors"] if f["factor"] == "growth_quality") for c in en) / len(en), 3)}
    # value 'cheap and shrinking' among the buy band: valuation >= 0.8 with eps_growth < 0
    def fv(c, n):
        return next((f["normalized"] for f in c["factors"] if f["factor"] == n and f.get("scored") is not False), None)
    buy = [c for c in L if c["score"] >= 70 and c["actionability"] == "ACTIONABLE"]
    out[f"cheap_shrinking_{market}"] = {"score_ge70": len(buy), "valuation_ge_0_8": sum(1 for c in buy if (fv(c, "valuation") or 0) >= 0.8), "of_which_eps_growth_lt0": sum(1 for c in buy if (fv(c, "valuation") or 0) >= 0.8 and neg(c, "eps_growth")),
                                        "of_which_eps_and_rev_lt0": [c["ticker"] for c in buy if (fv(c, "valuation") or 0) >= 0.8 and neg(c, "eps_growth") and neg(c, "rev_growth")]}
print(json.dumps(out, ensure_ascii=False, indent=1))
(HERE / "xr_agent02_checks.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
