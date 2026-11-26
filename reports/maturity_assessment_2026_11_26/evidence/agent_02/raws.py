from pathlib import Path
from terminal.qsf.ledger import Ledger
led = Ledger(Path(".")); rows = led._live_rows()
for m in ("US", "KR"):
    snaps = led._load([r for r in rows if r["market"] == m][-1])
    cs = [c for c in snaps if c["strategy"] == "LONG_TERM"]
    def none(f, k):
        have = [x for c in cs for x in c["factors"] if x["factor"] == f and x.get("status") in ("REAL", "STALE")]
        return sum(1 for x in have if (x.get("raw") or {}).get(k) is None), len(have)
    for f, k in (("business_quality", "gross_margin"), ("business_quality", "roe_years_positive"), ("financial_resilience", "interest_cover"), ("balance_dilution", "share_change"),
                 ("capital_allocation", "returns_capital"), ("valuation", "fcf_yield"), ("valuation", "pe"), ("growth_quality", "eps_cagr3"), ("insider_ownership", "insider_pct")):
        a, b = none(f, k); print(m, f, k, f"None in {a} of {b}")
    sw = [c for c in snaps if c["strategy"] == "SWING"]
    ins = [x for c in sw for x in c["factors"] if x["factor"] == "insider_activity" and x.get("normalized") is not None]
    print(m, "insider_activity: n", len(ins), "sell-only zero", sum(1 for x in ins if x["normalized"] == 0), "no trades 0.5", sum(1 for x in ins if x["normalized"] == 0.5))
    rr = [x for c in sw for x in c["factors"] if x["factor"] == "risk_reward" and x.get("normalized") is not None]
    print(m, "risk_reward zero share among score>=65:", sum(1 for c in sw if (c["score"] or 0) >= 65 and next(x for x in c["factors"] if x["factor"] == "risk_reward").get("normalized") == 0), "of", sum(1 for c in sw if (c["score"] or 0) >= 65))
