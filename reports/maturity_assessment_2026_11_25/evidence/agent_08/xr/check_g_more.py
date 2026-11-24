"""Follow-up of check_g_cases.py: financial facts for the two financial cards, and a non-financial strong card (read-only)."""
import sys, json
from pathlib import Path
repo = Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal import plain
ev = repo / "reports/maturity_assessment_2026_11_25/evidence/agent_08"
led = Ledger(repo)
notes = json.load(open(ev / "big/_api_qsf_rank-notes_market_US.json"))
sectors = notes.get("sectors") or {}
def snaps(mk):
    rows = [r for r in led._live_rows() if r["market"] == mk and str(r.get("session", "")).startswith("2026-11-23")]
    return led._load(rows[-1])
US, KR = snaps("US"), snaps("KR")
fp = lambda s: ((s.get("fund_period") or {}).get("trailing") or {}).get("score")
def show(s, facts, tag):
    p = plain.card_plain(s, facts)
    print("==", tag, s["ticker"], s["strategy"], round(s["score"], 1), s.get("confidence"), "sector", sectors.get(s["ticker"]), "trailing", fp(s) and round(fp(s), 1))
    for part in p["parts"]:
        if part["h"] in ("한 줄로", "좋게 본 점", "걱정되는 점", "말하지 않은 것"):
            print("   [%s]" % part["h"], " / ".join(part["lines"])[:400])
for s in US + KR:
    if s["ticker"] in ("ACGL", "005830") and s["strategy"] == "LONG_TERM":
        show(s, {"financial": True}, "financial facts")
for s in sorted(US, key=lambda x: -(x.get("score") or 0)):
    sec = sectors.get(s["ticker"]) or ""
    if (s["strategy"] == "LONG_TERM" and s.get("confidence") == "HIGH" and s.get("entry_status") == "ENTRY_NOW" and s.get("band") in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE")
            and "Financ" not in sec and sec and not s.get("band_held_back") and fp(s) is not None and abs(fp(s) - s["score"]) < 5):
        show(s, {}, "strong non-financial"); break
