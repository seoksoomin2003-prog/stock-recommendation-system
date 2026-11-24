"""Agent 06: on the last recorded session (2026-11-23), how the group the live verdict reads (score >= 70) differs from what the
screen calls a buy candidate (band) and from what it lets the user enter (entry status).  Labels and scores only: no price, no return."""
import collections, sys
from pathlib import Path
repo = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import engine
led = Ledger(repo)
rows = [r for r in led._live_rows()]
last = {}
for r in rows:
    last[r["market"]] = r
for m, r in sorted(last.items()):
    snaps = led._load(r)
    for strat in ("SWING", "LONG_TERM"):
        ss = [s for s in snaps if s.get("strategy") == strat and s.get("score") is not None and s.get("actionability") != "INSUFFICIENT_DATA"]
        hi = [s for s in ss if s["score"] >= 70]
        band = [s for s in ss if s.get("band") in engine.BUY_CODES]
        hi_not_band = [s for s in hi if s.get("band") not in engine.BUY_CODES]
        band_not_hi = [s for s in band if s["score"] < 70]
        es = lambda s: s.get("entry_status") if isinstance(s.get("entry_status"), str) else (s.get("entry_status") or {}).get("status")
        st = collections.Counter(es(s) for s in hi)
        blocked = sum(1 for s in hi if s.get("actionability") == "BLOCKED")
        print(f"{r['session']} {m} {strat} {r.get('model_version')}: rows {len(ss)} | score>=70 {len(hi)} | buy band {len(band)} | >=70 but no band {len(hi_not_band)} | band <70 {len(band_not_hi)} | >=70 blocked {blocked} | >=70 entry statuses {dict(st)}")
        top = sorted(ss, key=lambda s: -s["score"])[: max(1, len(ss) // 5)]
        print(f"      top fifth: {len(top)} rows, lowest score {top[-1]['score']:.1f}; in buy band {sum(1 for s in top if s.get('band') in engine.BUY_CODES)}")
