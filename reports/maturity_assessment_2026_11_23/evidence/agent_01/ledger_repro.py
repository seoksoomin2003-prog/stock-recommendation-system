"""Agent 01 scratch: ledger chain check, and whether the newest session's recorded scores come back from their stored factor rows.
Reads one shard per market.  No prices, no returns, no provider."""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf import config, engine
from terminal.qsf.ledger import Ledger

led = Ledger(REPO)
print("verify:", led.verify())
print("live code model version:", config.MODEL_VERSION)
for market in ("US", "KR"):
    rows = [r for r in led._live_rows() if r["market"] == market]
    print(market, "sessions:", len({r["session"] for r in rows}), "first", rows[0]["session"], "last", rows[-1]["session"])
    snaps = led._load(rows[-1])
    worst, n, none, versions, keys = 0.0, 0, 0, set(), set()
    for s in snaps:
        versions.add(s.get("model_version"))
        keys |= set(s)
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
    print(market, "record has input_coverage/partial/band_kept/conservative_score/band_held_back:", [k in keys for k in ("input_coverage", "partial", "band_kept", "conservative_score", "band_held_back")])
    prov = {}
    for s in snaps:
        p = (s.get("provenance") or {}).get("price")
        prov[p] = prov.get(p, 0) + 1
    print(market, "price provenance labels:", prov)
    del snaps
