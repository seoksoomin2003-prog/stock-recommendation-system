"""List ledger shards: market, session, snapshot count, model versions.  Read-only."""
import sys, collections
from pathlib import Path
sys.path.insert(0, ".")
from terminal.qsf.ledger import Ledger
led = Ledger(Path("."))
print("verify:", led.verify())
rows = led._live_rows()
print("row keys:", sorted(rows[0].keys()))
for r in rows:
    snaps = led._load(r)
    mv = collections.Counter((s.get("strategy"), s.get("model_version"), s.get("rules_version")) for s in snaps)
    dd = collections.Counter(s.get("data_date") for s in snaps)
    print(r["market"], r["session"], r.get("file"), len(snaps), dict(mv), "data_dates:", dict(dd.most_common(2)), r.get("recorded_at") or r.get("ts"))
