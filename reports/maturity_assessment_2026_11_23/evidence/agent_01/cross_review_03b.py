"""Agent 01 cross review of Agent 03, small additions: the size factor on an adverse US day under each stance, and how often risk_reward reads 0."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
from terminal.qsf import config, stance, order_plan as op
adverse = {"size_factor": config.ADVERSE_SIZE_FACTOR.get("US", 1.0), "new_exposure_cap": config.ADVERSE_NEW_EXPOSURE_CAP.get("US")}
print("adverse US day as the market state gives it:", adverse)
for lvl in stance.LEVELS:
    _, used, shown = stance.for_plan([], adverse, {}, lvl, op.STRATEGY_OF)
    print(f"   {lvl:10s}: size factor {used['size_factor']:g}, cap on new orders {used['new_exposure_cap']}")
dump = json.loads((HERE.parent / "agent_03" / "big" / "cards_151.json").read_text(encoding="utf-8"))
for market in ("US", "KR"):
    v = [f["normalized"] for c in dump[market]["cards"].values() if c["strategy"] == "SWING" for f in c["factors"] if f["factor"] == "risk_reward" and f["normalized"] is not None]
    tr = {c["ticker"]: next((f["normalized"] for f in c["factors"] if f["factor"] == "trend_structure"), None) for c in dump[market]["cards"].values() if c["strategy"] == "SWING"}
    ent = {}
    for c in dump[market]["cards"].values():
        if c["strategy"] == "SWING" and c["band"] in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE") and c["actionability"] == "ACTIONABLE":
            ent[c["entry_status"]] = ent.get(c["entry_status"], 0) + 1
    print(f"{market} swing risk_reward: cards {len(v)}, exactly 0: {sum(1 for x in v if x == 0) / len(v):.0%}, mean {sum(v) / len(v):.2f} | actionable buy-band cards by entry status: {ent}")
