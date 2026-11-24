"""Agent 02: print the structure of one long-term snapshot of the newest session (no returns)."""
import sys, json
from pathlib import Path
repo = Path.home() / "Developer" / "quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
led = Ledger(repo)
m, t = sys.argv[1], sys.argv[2]
row = [r for r in led._live_rows() if r["market"] == m][-1]
snaps = led._load(row)
print(row["session"], len(snaps))
for s in snaps:
    if s["ticker"] == t and s["strategy"] == "LONG_TERM":
        print(sorted(s.keys()))
        for f in s["factors"]:
            if f.get("domain") == "FUNDAMENTAL" or f["factor"] in ("financial_resilience", "leverage", "capital_allocation"):
                print(json.dumps({k: f.get(k) for k in ("factor", "status", "normalized", "raw", "explanation", "as_of", "inputs", "weight")}, ensure_ascii=False))
        print({k: s.get(k) for k in ("score", "band", "entry_status", "confidence", "conservative_score", "band_held_back", "deal_pin", "action", "price")})
        print("entry:", s.get("entry"))
