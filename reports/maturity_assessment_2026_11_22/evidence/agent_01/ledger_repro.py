"""Read-only consistency check (no returns, no prices): the hash chain, and whether each recorded score of the newest session of
each market can be recomputed from the factor rows stored beside it (100 * sum(w*n) / sum(w) over the scored rows)."""
import sys
from pathlib import Path
repo = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import engine
led = Ledger(repo)
print("verify:", led.verify())
rows = led._live_rows()
print("live shards:", len(rows), "versions:", sorted({r.get("model_version") for r in rows}))
by = {}
for r in rows:
    by.setdefault(r["market"], {}).setdefault(r["session"], []).append(r)
for m, d in by.items():
    print(m, "sessions:", len(d), "first:", min(d), "last:", max(d), "sessions with >1 shard:", sum(1 for v in d.values() if len(v) > 1))
for m in ("US", "KR"):
    last = [r for r in rows if r["market"] == m][-1]
    snaps = led._load(last)
    n = bad = none = 0
    worst = 0.0
    for s in snaps:
        if s.get("score") is None:
            none += 1
            continue
        scored = [f for f in s["factors"] if f.get("scored") is not False]
        got = engine.formula_score(scored, counted=())
        n += 1
        diff = abs(got - s["score"]) if got is not None else 999
        worst = max(worst, diff)
        bad += diff > 1e-9
    keys = sorted(snaps[0])
    print(m, last["session"], last["model_version"], "snapshots:", len(snaps), "scored:", n, "no score:", none, "recompute mismatches:", bad, "worst abs diff:", worst)
    print("   fields:", keys)
    f0 = snaps[0]["factors"][0]
    print("   factor row keys:", sorted(f0), "| provenance keys:", sorted((snaps[0].get("provenance") or {})))
