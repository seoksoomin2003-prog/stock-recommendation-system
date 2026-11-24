"""Agent 01 scratch (2026-11-25): ledger chain check, model versions per session (index only), and whether the newest
session's recorded scores come back from their stored factor rows.  One shard per market at a time.  No prices, no returns."""
import sys
from collections import defaultdict
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf import config
from terminal.qsf.ledger import Ledger

led = Ledger(REPO)
print("verify:", led.verify())
print("live code model version:", config.MODEL_VERSION)
rows_all = led._live_rows()
print("index row keys:", sorted(rows_all[0].keys()))
for market in ("US", "KR"):
    rows = [r for r in rows_all if r["market"] == market]
    per = defaultdict(set)
    for r in rows:
        per[r["session"]].add(r.get("model_version") or r.get("version"))
    print(market, "sessions:", len(per))
    for s in sorted(per)[-8:]:
        print("   ", s, sorted(x for x in per[s] if x))
    snaps = led._load(rows[-1])
    worst, n, none, versions, keys = 0.0, 0, 0, set(), set()
    pinned = held = 0
    for s in snaps:
        versions.add(s.get("model_version"))
        keys |= set(s)
        pinned += bool(s.get("deal_pin")); held += bool(s.get("deal_held"))
        w = c = 0.0
        for f in s["factors"]:
            if f.get("scored") is False or f.get("normalized") is None or f.get("status") not in ("REAL", "STALE"):
                continue
            w += f["weight"]; c += f["weight"] * f["normalized"]
        mine = 100 * c / w if w else None
        if s.get("score") is None or mine is None:
            none += (s.get("score") is None) != (mine is None)
            continue
        worst = max(worst, abs(mine - s["score"])); n += 1
    print(market, rows[-1]["session"], "snapshots", len(snaps), "recomputed", n, "max abs diff", worst, "None mismatches", none, "versions", sorted(versions))
    print(market, "fields present:", {k: k in keys for k in ("input_coverage", "conservative_score", "band_held_back", "band_kept", "deal_pin", "deal_held")}, "deal_pin rows", pinned, "deal_held rows", held)
    del snaps
