# Does a card the entry rule reads ENTRY_NOW already meet the program's own swing exit rule on the same day?  Recorded numbers only.
from datetime import date
from pathlib import Path
from terminal.qsf.ledger import Ledger
from terminal.qsf import order_plan as op, holding, config
led = Ledger(Path(".").resolve()); S = "2026-11-25"
def fac(s, fid): return next((f for f in s.get("factors") or [] if f.get("factor") == fid), {})
for market in ("KR", "US"):
    snaps = [s for s in op.session_snaps(led, market, S) if s.get("data_date") == S]
    en = [s for s in snaps if s["strategy"] == "SWING" and s.get("entry_status") == "ENTRY_NOW"]
    n = 0; acts = {}
    for s in en:
        raw = fac(s, "trend_structure").get("raw") or {}
        adv = (fac(s, "liquidity").get("raw") or {}).get("adv_value")
        below = raw.get("ma50") and s["price"] < raw["ma50"] and (raw.get("ma50_slope") or 0) < 0
        n += bool(below)
        res = {"tech": {"close": s["price"], "ma50": raw.get("ma50"), "ma50_slope": raw.get("ma50_slope"), "adv_value": adv}, "strategy": "SWING", "market": market,
               "factors": s["factors"], "domains": s["domains"], "score": s["score"], "actionability": s["actionability"]}
        out = holding.evaluate_exit(res, {"market": market}, {"stop": s["stop"], "target": s["target"], "opened": "2026-11-26"}, date(2026, 11, 26))
        acts[out["action"]] = acts.get(out["action"], 0) + 1
        if below and n <= 3: print("  ", market, s["ticker"], "->", out["action"], [h["code"] for h in out["conditions"]], out["reason"][:80])
    print(market, "swing ENTRY_NOW:", len(en), "| close under a falling 50-day line (the plan's own invalidation):", n, "| exit reading on the entry day itself:", acts)
