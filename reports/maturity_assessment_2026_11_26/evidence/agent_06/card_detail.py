import json, collections
from pathlib import Path
from terminal.qsf.ledger import Ledger
from terminal.qsf import order_plan as op, config
led = Ledger(Path(".").resolve()); S = "2026-11-25"
def fac(s, fid): return next((f for f in s.get("factors") or [] if f.get("factor") == fid), {})
for market, ticks in (("KR", ("064350", "051600", "012450")), ("US", ("TRV", "SWK", "HAS"))):
    snaps = [s for s in op.session_snaps(led, market, S) if s.get("data_date") == S]
    for s in snaps:
        if s["ticker"] in ticks and s["strategy"] == "SWING":
            h = s.get("holding") or {}
            print(market, s["ticker"], "score", round(s["score"], 1), s["band"], s["entry_status"], "price", s["price"], "stop", round(s["stop"], 2), "target", round(s["target"], 2))
            print("   holding keys:", sorted(h.keys())[:30])
            print("   expected_sessions", h.get("expected_sessions"), "range", h.get("range_sessions"), "why", h.get("why"))
            print("   invalidation", h.get("invalidation"))
            for fid in ("trend_structure", "risk_reward", "momentum", "relative_strength"):
                f = fac(s, fid); print("   ", fid, f.get("domain"), f.get("weight"), f.get("normalized"), json.dumps(f.get("raw"), ensure_ascii=False)[:260], (f.get("explanation") or "")[:120])
    # how many swing ENTRY_NOW cards already meet the swing exit rule "close under a falling 50-day line" (read from the trend factor's raw fields, if present)
    en = [s for s in snaps if s["strategy"] == "SWING" and s.get("entry_status") == "ENTRY_NOW"]
    raws = [fac(s, "trend_structure").get("raw") or {} for s in en]
    print(market, "ENTRY_NOW swing", len(en), "trend raw keys", sorted(raws[0].keys()) if raws else None)
    # target distance in ATR vs the plan's stated horizon cap
    far = [(s["ticker"], round((s["target"] - s["price"]) / op.atr_of(s), 1), (s.get("holding") or {}).get("expected_sessions")) for s in en if op.atr_of(s)]
    print("   (ticker, target distance in ATR, expected sessions):", far)
    # long cards: stop distance of 5 ATR as a share of price
    lg = [s for s in snaps if s["strategy"] == "LONG_TERM" and s.get("entry_status") == "ENTRY_NOW"]
    sw = {s["ticker"]: s for s in snaps if s["strategy"] == "SWING"}
    d = sorted(5 * op.atr_of(sw[s["ticker"]]) / s["price"] for s in lg if s["ticker"] in sw and op.atr_of(sw[s["ticker"]]))
    if d: print(f"   long ENTRY_NOW: 5-ATR stop distance as share of price: min {d[0]:.1%} median {d[len(d)//2]:.1%} p90 {d[int(len(d)*.9)]:.1%} max {d[-1]:.1%}; over 50%: {sum(x>0.5 for x in d)}; over 100% (no stop): {sum(x>=1 for x in d)}")
    d2 = sorted(op.atr_of(s) / s["price"] for s in sw.values() if op.atr_of(s))
    print(f"   ATR%% of all swing cards: median {d2[len(d2)//2]:.2%} p90 {d2[int(len(d2)*.9)]:.2%}")
