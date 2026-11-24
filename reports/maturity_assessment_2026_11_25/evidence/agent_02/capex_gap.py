"""Agent 02: stocks whose operating cash flow is stored but whose free cash flow is not (capex not read), and how the
cash-flow factors read them.  Reads big/survey_<m>.json written by survey.py.  Counts only, no returns."""
import json, sys
from pathlib import Path
for m in ("US", "KR"):
    d = json.load(open(Path(__file__).parent / "big" / f"survey_{m}.json"))
    rows = [(t, round(v["raw"]["ocf_to_ni"], 2), v["norm"].get("SWING:cash_flow_quality"), v["norm"].get("LONG_TERM:free_cash_flow"),
             round(v["long"]["score"], 1), v["long"]["band"]) for t, v in d.items()
            if not v["fin"] and v["raw"].get("ocf_to_ni") is not None and v["raw"].get("fcf_margin") is None]
    print(m, "non-financial with OCF/NI but no FCF margin:", len(rows))
    for r in sorted(rows, key=lambda r: -r[4])[:15]:
        print("  ", r)
    # ROE with negative equity / tiny equity
    hi = [(t, round(v["raw"]["roe"], 2), round(v["long"]["score"], 1), v["long"]["band"]) for t, v in d.items() if (v["raw"].get("roe") or 0) > 0.6]
    print(m, "ROE > 60%:", len(hi), sorted(hi, key=lambda r: -r[1])[:12])
    nd = [(t, round(v["long"]["score"], 1), v["long"]["band"], v["long"]["entry_status"]) for t, v in d.items() if v["raw"].get("debt_equity") == 99]
    print(m, "no-equity mark (99):", len(nd), "buy band:", [x for x in nd if x[2] in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE")])
