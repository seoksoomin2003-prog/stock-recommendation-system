"""Read-only: the market state of every recorded session, one session at a time.  No returns, no prices beyond the regime rows."""
import gc, json, sys
from pathlib import Path
repo = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import engine
led = Ledger(repo)
out = []
for market in ("US", "KR"):
    rows = [r for r in led._live_rows() if r["market"] == market]
    seen = {}
    for r in rows:
        seen[r["session"]] = r          # newest row of a session wins
    for session in sorted(seen):
        r = seen[session]
        snaps = led._load(r)
        pick = next((s for s in snaps if s.get("data_date") == session and s.get("strategy") == "SWING" and any(f.get("domain") == "REGIME" for f in s.get("factors") or [])), None)
        if pick is None:
            out.append({"market": market, "session": session, "state": None, "n": len(snaps)})
        else:
            ms = engine.market_state(pick["factors"], market)
            out.append({"market": market, "session": session, "model": pick.get("model_version"), "n": len(snaps), "score": None if ms["score_100"] is None else round(ms["score_100"], 1), "state": ms["state"], "coverage": ms["coverage"],
                        "factors": {p["factor"]: (None if p["normalized"] is None else round(p["normalized"], 3), p["status"], p["as_of"], {k: (round(v, 3) if isinstance(v, float) else v) for k, v in (p["raw"] or {}).items()}) for p in ms["factors"]}})
        del snaps
        gc.collect()
Path(__file__).with_name("state_history.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
for o in out:
    f = o.get("factors") or {}
    print(o["market"], o["session"], o.get("model"), o.get("n"), o.get("score"), o.get("state"), o.get("coverage"), " ".join(f"{k}={v[0]}({v[1][0]},{v[2]})" for k, v in f.items()))
