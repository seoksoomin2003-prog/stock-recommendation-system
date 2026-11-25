"""List recorded sessions per market with model_version and row counts.  Read-only; no return, no outcome."""
from pathlib import Path
from collections import Counter
from terminal.qsf.ledger import Ledger
led = Ledger(Path("."))
rows = led._live_rows()
c = Counter()
for r in rows:
    c[(r["market"], r["session"], r.get("model_version"))] += r.get("count", 1) if isinstance(r.get("count"), int) else 1
for k in sorted(c):
    print(k, c[k])
print(rows[-1].keys())
