"""Agent 03 cross review: the stored long-term factor values and raw figures of agent 02's named cases (2026-11-23 record).
Also counts agent 02's 'value 0.8+ with revenue and EPS both falling' shape.  Factor values only."""
import sys, json
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
led = Ledger(REPO)
NAMES = {"US": ("PHM", "EOG", "GPN", "NVR", "MO", "DAL", "MU", "INCY", "APA"), "KR": ("011200", "000660", "051900")}
for m in ("US", "KR"):
    row = [r for r in led._live_rows() if r["market"] == m][-1]
    shape = []
    for s in led._load(row):
        if s["strategy"] != "LONG_TERM":
            continue
        fs = {f["factor"]: f for f in s["factors"]}
        g = lambda k: fs.get(k, {}).get("normalized")
        graw = (fs.get("growth_quality") or {}).get("raw") or {}
        eraw = None
        v = g("valuation")
        if v is not None and v >= 0.8 and (graw.get("rev_growth") or 0) < 0:
            # EPS growth lives in the swing factor; the long card keeps eps_cagr3 only
            shape.append((s["ticker"], round(s["score"], 1), s["band"], s.get("entry_status"), round(v, 2), graw.get("rev_growth"), graw.get("eps_cagr3")))
        if s["ticker"] in NAMES[m]:
            print(m, s["ticker"], round(s["score"], 2), s["band"], s.get("entry_status"), "cons", round(s.get("conservative_score") or 0, 2),
                  {k: (None if g(k) is None else round(g(k), 2)) for k in ("valuation", "business_quality", "growth_quality", "free_cash_flow", "financial_resilience", "balance_dilution")},
                  "val raw", (fs.get("valuation") or {}).get("raw"), "growth raw", graw, "bq raw", (fs.get("business_quality") or {}).get("raw"))
    print(m, "valuation>=0.8 and latest revenue growth < 0 (long cards):", len(shape))
    for x in sorted(shape, key=lambda x: -x[1])[:12]:
        print("    ", x)
