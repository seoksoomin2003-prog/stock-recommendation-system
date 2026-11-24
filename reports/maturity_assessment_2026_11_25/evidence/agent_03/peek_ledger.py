"""Agent 03: list the live ledger sessions (version, count) and the keys of one snapshot. No returns computed."""
import sys, json
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
led = Ledger(REPO)
rows = led._live_rows()
for r in rows[-14:]:
    print({k: r.get(k) for k in r if k not in ("path",)})
snaps = led._load([r for r in rows if r["market"] == "US"][-1])
s = snaps[0]
print(len(snaps), sorted(s.keys()))
print(json.dumps(s.get("factors", [])[:2], ensure_ascii=False, default=str)[:1500])
