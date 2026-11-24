"""Agent 02: list the newest ledger sessions per market (no returns)."""
import sys
from pathlib import Path
repo = Path.home() / "Developer" / "quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
led = Ledger(repo)
rows = led._live_rows()
for m in ("US", "KR"):
    rs = [r for r in rows if r["market"] == m][-4:]
    for r in rs:
        print(m, {k: r.get(k) for k in ("session", "model_version", "n", "count", "stocks") if k in r}, list(r.keys())[:12])
