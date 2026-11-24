"""Market state per recorded session (regime factors only), read from the ledger one session at a time. No returns computed."""
import sys, json
from pathlib import Path
repo = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import engine
led = Ledger(repo)
out = []
for m in ("US", "KR"):
    rows = [r for r in led._live_rows() if r["market"] == m]
    by = {}
    for r in rows:
        by.setdefault(r.get("session"), r)          # first live row of each session
    for sess in sorted(k for k in by if k)[-8:]:
        snaps = led._load(by[sess])
        s = next((x for x in snaps if x.get("strategy") == "SWING" and x.get("factors")), None)
        if not s:
            continue
        st = engine.market_state(s["factors"], m)
        f = {p["factor"]: (None if p["normalized"] is None else round(p["normalized"], 3), p.get("as_of")) for p in st["factors"]}
        out.append({"market": m, "session": sess, "model": s.get("model_version"), "value": None if st["score_100"] is None else round(st["score_100"], 1),
                    "state": st["state"], "coverage": st["coverage"], "factors": f})
        del snaps
for o in out:
    print(o["market"], o["session"], o["model"], o["value"], o["state"], o["coverage"], json.dumps(o["factors"], ensure_ascii=False))
json.dump(out, open(Path(__file__).with_name("state_history.json"), "w"), ensure_ascii=False, indent=1)
