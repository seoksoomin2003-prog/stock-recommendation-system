"""In-memory check: stance.for_plan under today's recorded market states (no provider, no file writes)."""
import json, sys
from pathlib import Path
repo = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo))
from terminal.qsf import stance, engine, config
here = Path(__file__).parent
for m in ("US", "KR"):
    st = json.loads((here / f"market_state_{m}.json").read_text())
    for lvl in ("DEFENSIVE", "NORMAL", "AGGRESSIVE"):
        _, used, shown = stance.for_plan([], st, {}, lvl, {})
        print(m, lvl, "state", st["state"], round(st["score_100"], 1), "-> size_factor used", used["size_factor"], "cap", used["new_exposure_cap"])
        if lvl == "AGGRESSIVE":
            print("   note:", shown["note"])
# market_state boundary: 49.9 vs 50.1, and coverage exactly 0.5 with all STALE
def rows(vals, status="REAL"):
    return [{"domain": "REGIME", "factor": f, "status": status, "normalized": v} for f, v in zip(config.MARKET_STATE_WEIGHTS["US"], vals)]
for v in (0.499, 0.501):
    r = engine.market_state(rows([v] * 4), "US"); print("all factors", v, "->", round(r["score_100"], 1), r["state"], r["size_factor"])
r = engine.market_state(rows([0.8] * 4, "STALE"), "US"); print("all STALE ->", r["state"], r["coverage"])
# slow decline: index trend+breadth 0, others calm
r = engine.market_state(rows([0.8, 0.83, 0.67, 0.0]), "US"); print("trend/breadth 0, vix .8 term .83 credit .67 ->", round(r["score_100"], 1), r["state"])
# today's US with the credit factor at the middle instead of its 3-year percentile
st = json.loads((here / "market_state_US.json").read_text())
vals = [f["normalized"] for f in st["factors"]]
vals2 = list(vals); vals2[2] = 0.5
print("today US", round(engine.market_state(rows(vals), "US")["score_100"], 1), "credit at middle ->", round(engine.market_state(rows(vals2), "US")["score_100"], 1))
