"""Count how many swing buy-band cards of the newest ledger session per market the EN-1 rule (order_plan.breakout_wait) adds.
Reads one ledger session per market; computes no return."""
import sys
from collections import Counter
from pathlib import Path
REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
from terminal.qsf import order_plan
led = Ledger(REPO)
rows = led._live_rows()
for m in ("US", "KR"):
    r = [x for x in rows if x["market"] == m][-1]
    snaps = led._load(r)
    sw = [s for s in snaps if s.get("strategy") == "SWING"]
    bb = [s for s in sw if s.get("band") in ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE") and s.get("actionability") == "ACTIONABLE"]
    print(m, r.get("session"), r.get("model_version") or r.get("version"), "swing", len(sw), "buy-band actionable", len(bb),
          dict(Counter(s.get("entry_status") for s in bb)), "breakout_wait", sum(order_plan.breakout_wait(s) for s in bb),
          "all-swing WAIT", sum(s.get("entry_status") == "WAIT_FOR_PULLBACK" for s in sw))
