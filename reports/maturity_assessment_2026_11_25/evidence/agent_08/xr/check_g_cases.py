"""System Test G (read-only): five kinds of card from the 2026-11-23 ledger and what the screen would say about each.
Scan-row labels come from the saved /api/qsf/latest replies; plain text from terminal.plain.card_plain on the stored card
(no provider call).  Nothing computed about returns."""
import sys, json
from pathlib import Path
repo = Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal import plain
ev = repo / "reports/maturity_assessment_2026_11_25/evidence/agent_08"
led = Ledger(repo)
FIN = ("Financial Services", "Financials")
def snaps(mk):
    rows = [r for r in led._live_rows() if r["market"] == mk and str(r.get("session", "")).startswith("2026-11-23")]
    return led._load(rows[-1])
latest = {mk: json.load(open(ev / f"big/_api_qsf_latest_market_{mk}.json")) for mk in ("US", "KR")}
rowmap = {(mk, r["ticker"], r["strategy"]): r for mk in latest for r in latest[mk]["rows"]}
S = {"US": snaps("US"), "KR": snaps("KR")}
def stale(s):
    pv = s.get("provenance") or {}
    return pv.get("stale") or []
def pick(mk, cond):
    for s in sorted(S[mk], key=lambda x: -(x.get("score") or 0)):
        r = rowmap.get((mk, s["ticker"], s["strategy"]), {})
        if cond(s, r):
            return s, r
    return None, None
fp = lambda s: ((s.get("fund_period") or {}).get("trailing") or {}).get("score")
cases = {
 "1 strong": pick("US", lambda s, r: s["strategy"] == "LONG_TERM" and s.get("confidence") == "HIGH" and s.get("band") in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE")
                  and s.get("entry_status") == "ENTRY_NOW" and not s.get("gates") and r.get("sector") not in FIN and not r.get("deal") and not s.get("band_held_back")
                  and fp(s) is not None and abs(fp(s) - s["score"]) < 5 and not stale(s)),
 "2 insufficient": pick("KR", lambda s, r: s.get("confidence") == "LOW" and s.get("band") in ("BUY_CANDIDATE",) and s.get("band_held_back")),
 "4 stale": pick("US", lambda s, r: bool(stale(s)) and s.get("band") in ("BUY_CANDIDATE", "HOLD_WATCH")) if any(stale(s) for s in S["US"]) else pick("KR", lambda s, r: bool(stale(s))),
 "5 valuation": pick("US", lambda s, r: s["strategy"] == "LONG_TERM" and s.get("band") == "BUY_CANDIDATE" and s.get("entry_status") == "OVERVALUED_AT_CURRENT_PRICE"),
}
print("stale cards US", sum(1 for s in S["US"] if stale(s)), "KR", sum(1 for s in S["KR"] if stale(s)),
      "stale_fund_days>0 US", sum(1 for s in S["US"] if s.get("stale_fund_days")), "KR", sum(1 for s in S["KR"] if s.get("stale_fund_days")))
for k, (s, r) in cases.items():
    if not s:
        print("==", k, "none found"); continue
    print("==", k, s["ticker"], r.get("name"), s["strategy"], "score", round(s["score"], 1), "| row band_label:", r.get("band_label"), "| action:", r.get("action_label"),
          "| conf", s.get("confidence"), "cov", round(s.get("coverage") or 0, 2), "| entry", s.get("entry_status"), "| missing", s.get("missing"),
          "| trailing", fp(s) and round(fp(s), 1), "| stale", [(x.get("what"), x.get("age_days")) for x in stale(s)], "stale_fund_days", s.get("stale_fund_days"))
    try:
        p = plain.card_plain({**s, **{k2: r.get(k2) for k2 in ("band_label", "action_label") if r.get(k2)}})
        for part in p["parts"]:
            if part["h"] in ("한 줄로", "걱정되는 점", "말하지 않은 것", "지금 사도 되나", "먼저 알아 둘 사건"):
                print("   [%s]" % part["h"], " / ".join(part["lines"])[:420])
    except Exception as e:
        print("   plain failed:", type(e).__name__, e)
