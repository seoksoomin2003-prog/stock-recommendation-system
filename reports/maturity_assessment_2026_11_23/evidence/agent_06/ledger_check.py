"""Agent 06.  System test F on the ledger: scores and their stored parts only.  NO price is read and NO return is computed."""
import sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf import engine
from terminal.qsf.ledger import Ledger

led = Ledger(REPO)
v = led.verify()
print("verify:", {k: (v[k] if not isinstance(v[k], (list, dict)) else len(v[k])) for k in v})
rows = led._live_rows()
print("index row keys:", sorted(rows[-1].keys()))
by = {}
for r in rows:
    by.setdefault((r["market"], r["session"]), []).append(r)
for m in ("US", "KR"):
    days = sorted(d for (mk, d) in by if mk == m)
    print(m, "sessions", len(days), days[0], "..", days[-1], "versions", sorted({str(r.get("model_version")) for (mk, d), rs in by.items() if mk == m for r in rs}))
    for day in (days[0], days[len(days) // 2], days[-1]):
        snaps = []
        for r in by[(m, day)]:
            snaps += led._load(r)
        scored = [s for s in snaps if s.get("score") is not None]
        exact = close = 0
        worst = 0.0
        late = 0
        for s in scored:
            p = engine.formula_score(s.get("factors") or [], ())          # only the scored rows count
            if p is not None:
                d = abs(p - float(s["score"]))
                worst = max(worst, d)
                exact += d < 1e-6
                close += d < 0.01
            rec, entry = str(s.get("recorded_at") or s.get("created_at") or "")[:10], str(s.get("entry_session") or "")
            late += bool(rec and entry and rec > entry)
        s0 = scored[0] if scored else {}
        f0 = (s0.get("factors") or [{}])[0]
        print(f"  {day}: snapshots {len(snaps)}, scored {len(scored)}, composite rebuilt from stored factor rows within 1e-6: {exact}, within 0.01: {close}, largest gap {worst:.4f}; "
              f"recorded after the entry session: {late}; version {sorted({str(s.get('model_version')) for s in snaps})}")
    print("  snapshot keys:", sorted(s0.keys()))
    print("  factor row keys:", sorted(f0.keys()))
    print("  has bars / statements in the snapshot:", any(k in s0 for k in ("bars", "prices", "statements", "fund_raw")), "| provenance keys:", sorted((s0.get("provenance") or {}).keys()))
