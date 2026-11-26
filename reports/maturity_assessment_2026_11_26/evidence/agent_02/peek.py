import json, sys
from pathlib import Path
from terminal.qsf.ledger import Ledger
led = Ledger(Path("."))
rows = led._live_rows()
print(len(rows), rows[-1].keys() if rows else None)
for r in rows[-6:]:
    print({k: r[k] for k in r if k in ("market","session","model_version","rules_version","n","strategy","file","count")})
for m in ("US","KR"):
    rr = [r for r in rows if r["market"] == m]
    snaps = led._load(rr[-1])
    print(m, type(snaps), len(snaps))
    s = snaps[0] if isinstance(snaps, list) else next(iter(snaps.values()))
    print(sorted(s.keys()))
    print({k: (v if not isinstance(v, (list, dict)) else type(v).__name__ + str(len(v))) for k, v in s.items()})
    print(json.dumps(s.get("factors", [])[:2], ensure_ascii=False)[:900])
