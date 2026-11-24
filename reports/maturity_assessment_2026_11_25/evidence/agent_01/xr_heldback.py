"""Agent 01 cross review: 2026-11-23 ledger cards whose buy band was held back (band_held_back), with their entry status.
One market at a time; labels only, no prices, no returns."""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
led = Ledger(REPO)
for market in ("US", "KR"):
    rows = [r for r in led._live_rows() if r["market"] == market]
    snaps = led._load(rows[-1])
    hb = [s for s in snaps if s.get("band_held_back")]
    print(market, rows[-1]["session"], "held back:", len(hb))
    for s in hb:
        print("   ", s["ticker"], s["strategy"], round(s["score"], 2), "cons", round(s["conservative_score"], 2), s["band"], s["action"], s["actionability"], s["entry_status"])
    del snaps
