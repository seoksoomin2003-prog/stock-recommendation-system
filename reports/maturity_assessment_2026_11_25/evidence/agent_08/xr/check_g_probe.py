"""Cross-review probe (read-only): from the 2026-11-23 live ledger, count LOW-confidence cards with buy-like words and list
candidate cards for System Test G.  No provider calls, no returns computed, nothing written outside this folder."""
import sys, json
from collections import Counter
from pathlib import Path
repo = Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
led = Ledger(repo)
out = {}
for mk in ("US", "KR"):
    rows = [r for r in led._live_rows() if r["market"] == mk and str(r.get("session", "")).startswith("2026-11-23")]
    if not rows:
        rows = [r for r in led._live_rows() if r["market"] == mk][-1:]
    snaps = led._load(rows[-1])
    print(mk, "row session", rows[-1].get("session"), "cards", len(snaps))
    if snaps and mk == "US":
        print(" keys:", sorted(snaps[0].keys())[:80])
    conf = Counter((s.get("confidence"), (s.get("band") or "")) for s in snaps)
    print(" confidence x band:", dict(conf))
    low_buy = [s for s in snaps if s.get("confidence") in ("LOW", "INSUFFICIENT") and s.get("band") in ("STRONG_BUY", "BUY_CANDIDATE", "BUY")]
    print(" LOW/INSUFF in buy band:", len(low_buy), [(s["ticker"], s["strategy"], round(s["score"], 1), s.get("band_label"), s.get("action_label"), s.get("entry_status")) for s in low_buy[:8]])
    low_any = [s for s in snaps if s.get("confidence") in ("LOW", "INSUFFICIENT")]
    print(" LOW/INSUFF action labels:", dict(Counter(s.get("action_label") for s in low_any)))
    held = [s for s in snaps if s.get("band_held_back")]
    print(" band_held_back:", len(held), [(s["ticker"], s["strategy"], round(s["score"], 1), s.get("conservative_score") and round(s["conservative_score"], 1), s.get("band_label")) for s in held[:5]])
    out[mk] = snaps
json.dump({mk: [{k: s.get(k) for k in ("ticker", "strategy", "score", "band", "band_label", "action", "action_label", "confidence", "coverage", "entry_status", "actionability", "missing", "conservative_score", "band_held_back", "stale_fund_days", "price", "data_date", "deal", "gates")} for s in v] for mk, v in out.items()},
          open(Path(__file__).with_name("cards_1123.json"), "w"), ensure_ascii=False, default=str)
