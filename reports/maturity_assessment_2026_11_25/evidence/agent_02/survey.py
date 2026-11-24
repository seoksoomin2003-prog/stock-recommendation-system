"""Agent 02 (2026-11-25): survey of stored fundamental inputs and readings on the newest ledger session of one market.
Read only.  No provider, no returns, no IC.  Counts only."""
import sys, json
from collections import Counter
from pathlib import Path
repo = Path.home() / "Developer" / "quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger

m = sys.argv[1]
led = Ledger(repo)
row = [r for r in led._live_rows() if r["market"] == m][-1]
snaps = led._load(row)
print("session", row["session"], row["model_version"], "cards", len(snaps))
per = {}
for s in snaps:
    d = per.setdefault(s["ticker"], {"raw": {}, "norm": {}, "status": {}})
    st = s["strategy"]
    d[st] = {k: s.get(k) for k in ("score", "band", "entry_status", "confidence", "action", "actionability", "band_held_back", "deal_pin")}
    for f in s["factors"]:
        d["status"][(st, f["factor"])] = f.get("status")
        if f.get("normalized") is not None:
            d["norm"][(st, f["factor"])] = f["normalized"]
        if isinstance(f.get("raw"), dict):
            for k, v in f["raw"].items():
                if not isinstance(v, (dict, list)):
                    d["raw"].setdefault(k, v)
    d["fin"] = d["status"].get(("LONG_TERM", "leverage")) == "NOT_APPLICABLE" or "equity_assets" in d["raw"]
tick = sorted(per)
n = len(tick)
print("stocks", n, "financial", sum(per[t]["fin"] for t in tick))
keys = ["roe", "op_margin", "gross_margin", "rev_growth", "eps_growth", "rev_cagr3", "eps_cagr3", "ocf_to_ni", "fcf_margin", "fcf_yield", "pe", "pb",
        "debt_equity", "current_ratio", "interest_cover", "cash_debt", "share_change", "returns_capital", "equity_assets", "roe_years_positive", "fcf_years_positive"]
print("blank counts (of stocks):", {k: sum(per[t]["raw"].get(k) is None for t in tick) for k in keys})
L = [t for t in tick if "LONG_TERM" in per[t]]
bq = [t for t in L if per[t]["norm"].get(("LONG_TERM", "business_quality"), 0) >= 0.7]
print("long cards", len(L), "business_quality>=0.7:", len(bq))
print("long entry_status:", Counter(per[t]["LONG_TERM"]["entry_status"] for t in L))
print("long band:", Counter(per[t]["LONG_TERM"]["band"] for t in L))
print("long action:", Counter(per[t]["LONG_TERM"]["action"] for t in L))
# OCF / NI explosion
big = sorted([(round(per[t]["raw"]["ocf_to_ni"], 2), t) for t in tick if (per[t]["raw"].get("ocf_to_ni") or 0) > 3], reverse=True)
print("ocf_to_ni > 3:", len(big), big[:12])
# near-zero debt, non-financial
nz = [(t, round(per[t]["raw"]["debt_equity"], 4), per[t]["raw"].get("interest_cover")) for t in tick if not per[t]["fin"] and per[t]["raw"].get("debt_equity") is not None and 0 <= per[t]["raw"]["debt_equity"] < 0.02]
print("debt_equity < 0.02 non-financial:", len(nz), nz[:15])
# loss now with a valuation factor reading well
loss = [t for t in tick if (per[t]["raw"].get("pe") is not None and per[t]["raw"]["pe"] <= 0)]
lv = [(t, round(per[t]["norm"].get(("LONG_TERM", "valuation"), -1), 2), per[t]["LONG_TERM"]["entry_status"]) for t in loss if per[t]["norm"].get(("LONG_TERM", "valuation"), 0) >= 0.65]
print("loss-makers:", len(loss), "with valuation>=0.65:", lv)
# value-trap shape: cheap + falling sales and earnings + buy band or ENTRY_NOW
trap = []
for t in L:
    r = per[t]["raw"]
    if per[t]["norm"].get(("LONG_TERM", "valuation"), 0) >= 0.8 and (r.get("rev_growth") or 0) < 0 and (r.get("eps_growth") is not None and r["eps_growth"] < 0):
        trap.append((t, round(per[t]["LONG_TERM"]["score"], 1), per[t]["LONG_TERM"]["band"], per[t]["LONG_TERM"]["entry_status"], round(r["rev_growth"], 3), round(r["eps_growth"], 3)))
print("cheap + sales and EPS falling:", len(trap), "of which buy band:", sum(x[2] in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE") for x in trap), "ENTRY_NOW:", sum(x[3] == "ENTRY_NOW" for x in trap))
for x in sorted(trap, key=lambda x: -x[1])[:12]:
    print("   ", x)
# multi-year decline + ENTRY_NOW
dec = [(t, round(per[t]["LONG_TERM"]["score"], 1), per[t]["LONG_TERM"]["band"], round(per[t]["raw"]["rev_cagr3"], 3)) for t in L
       if (per[t]["raw"].get("rev_cagr3") is not None and per[t]["raw"]["rev_cagr3"] < 0 and (per[t]["raw"].get("rev_growth") or 0) < 0) and per[t]["LONG_TERM"]["entry_status"] == "ENTRY_NOW"]
print("3y sales falling and last year falling, ENTRY_NOW:", len(dec), dec[:12])
# growth sentence check: earnings_revenue_quality reads well (>=0.65) while EPS or sales fell
gs = [t for t in tick if per[t]["norm"].get(("SWING", "earnings_revenue_quality"), 0) >= 0.65 and ((per[t]["raw"].get("eps_growth") is not None and per[t]["raw"]["eps_growth"] < 0) or (per[t]["raw"].get("rev_growth") is not None and per[t]["raw"]["rev_growth"] < 0))]
g_all = sum(per[t]["norm"].get(("SWING", "earnings_revenue_quality"), 0) >= 0.65 for t in tick)
print("swing growth factor reads 'sales and earnings rising' (>=0.65) though one fell:", len(gs), "of", g_all, gs[:10])
gq = [t for t in tick if per[t]["norm"].get(("LONG_TERM", "growth_quality"), 0) >= 0.65 and per[t]["raw"].get("eps_cagr3") is not None and per[t]["raw"]["eps_cagr3"] < 0]
print("long growth reads 'steady growth' though 3y EPS CAGR < 0:", len(gq), "of", sum(per[t]["norm"].get(("LONG_TERM", "growth_quality"), 0) >= 0.65 for t in tick), gq[:10])
# deal pins
print("deal pins:", [(t, per[t]["LONG_TERM"]["deal_pin"]) for t in L if per[t]["LONG_TERM"].get("deal_pin")][:5])
json.dump({t: {"raw": per[t]["raw"], "long": per[t].get("LONG_TERM"), "swing": per[t].get("SWING"), "fin": per[t]["fin"],
               "norm": {f"{a}:{b}": v for (a, b), v in per[t]["norm"].items()}} for t in tick},
          open(Path(__file__).parent / "big" / f"survey_{m}.json", "w"), ensure_ascii=False, default=str)
