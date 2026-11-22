"""Agent 7 cross review: counts from the dry-scan cards (today's code on stored inputs).  No return is computed."""
import json
from collections import Counter
BUY = ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE")
def st(c, n): return next((x.get("status") for x in c["factors"] if x["factor"] == n), None)
def nv(c, n): return next((x.get("normalized") for x in c["factors"] if x["factor"] == n), None)
for m in ("US", "KR"):
    d = json.load(open(f"big/cards_{m}.json"))
    lg = [c for c in d.values() if c["strategy"] == "LONG_TERM"]
    act = [c for c in lg if c["actionability"] == "ACTIONABLE"]
    vm = [c for c in act if st(c, "valuation") == "MISSING"]
    print(m, "long actionable", len(act), "| valuation MISSING:", [(c["ticker"], c.get("name"), round(c["score"], 1), c["band"], c["entry_status"], c["confidence"]) for c in vm])
    miss = [c for c in act if c["missing"]]
    now = [c for c in miss if c["entry_status"] == "ENTRY_NOW"]
    buy = [c for c in miss if c["band"] in BUY]
    print("  any scored factor missing:", len(miss), "of them ENTRY_NOW", len(now), "in buy band", len(buy), "strong buy", [(c["ticker"], round(c["score"], 1), round(c["conservative_score"], 1), c["confidence"], c["missing"]) for c in buy if c["band"] == "STRONG_BUY_CANDIDATE"])
    print("  missing factor names among ENTRY_NOW:", Counter(f for c in now for f in c["missing"]).most_common(6))
    gap = sorted(((round(c["score"] - c["conservative_score"], 1), c["ticker"], c["band"], c["entry_status"]) for c in miss if c.get("conservative_score") is not None), reverse=True)[:5]
    print("  largest score minus conservative:", gap)
    print("  buy band by confidence:", Counter(c["confidence"] for c in act if c["band"] in BUY), "| all actionable by confidence:", Counter(c["confidence"] for c in act))
    if m == "KR":
        for t in ("000880", "183300", "440110", "207940"):
            for s in ("SWING", "LONG_TERM"):
                c = d.get(f"{t}|{s}")
                if c:
                    ts = c["tech_small"]
                    print("  HALT", t, c.get("name"), s, round(c["score"], 1), c["band_label"], c["actionability"], c["confidence"], c["entry_status"], "atr_pct", None if ts.get("atr_pct") is None else round(ts["atr_pct"], 4), "gates", [g["code"] for g in c["gates"]], "| risk-side:", {k: (None if nv(c, k) is None else round(nv(c, k), 2)) for k in ("atr_risk", "drawdown_gap", "downside_drawdown", "volatility_structure") if st(c, k)})
