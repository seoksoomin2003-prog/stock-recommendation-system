import sys, collections, json
from pathlib import Path
repo = Path(".").resolve()
from terminal.qsf.ledger import Ledger
from terminal.qsf import config, engine, order_plan
led = Ledger(repo)
for market in ("US", "KR"):
    rows = [r for r in led._live_rows() if r["market"] == market]
    sess = sorted({r["session"] for r in rows})
    print("==", market, "sessions", len(sess), sess[-3:])
    snaps = order_plan.session_snaps(led, market, "2026-11-25")
    snaps = [s for s in snaps if s.get("data_date") == "2026-11-25"]
    print("snaps", len(snaps), "keys", sorted(snaps[0].keys())[:80] if snaps else None)
    print("versions", collections.Counter((s.get("model_version"), s.get("rules_version")) for s in snaps))
    ms = order_plan.state_for_plan(snaps, market, "2026-11-25")
    print("market_state", {k: ms.get(k) for k in ("score_100","coverage","state","size_factor","new_exposure_cap")})
    for f in ms.get("factors", []): print("   ", f["factor"], f["weight"], f["status"], f["normalized"])
    for strat in ("SWING", "LONG_TERM"):
        ss = [s for s in snaps if s.get("strategy") == strat]
        tab = collections.Counter((s.get("band"), s.get("entry_status"), s.get("actionability")) for s in ss)
        print(" --", strat, len(ss))
        for k, v in sorted(tab.items(), key=lambda kv: str(kv[0])): print("    ", k, v)
    def fac(s, fid):
        for f in s.get("factors") or []:
            if f.get("factor") == fid: return f
        return {}
    sw = [s for s in snaps if s.get("strategy") == "SWING" and s.get("score") is not None]
    # reward/risk factor vs entry status
    print(" -- swing: risk_reward factor normalized by entry status (count, min, median, max)")
    by = collections.defaultdict(list)
    for s in sw:
        n = fac(s, "risk_reward").get("normalized")
        by[s.get("entry_status")].append(n)
    for k, v in by.items():
        vv = sorted(x for x in v if x is not None)
        print("    ", k, len(v), "none", sum(x is None for x in v), (vv[0], vv[len(vv)//2], vv[-1]) if vv else None)
    # breakout-wait in buy band
    bw = [s for s in snaps if order_plan.breakout_wait(s)]
    print(" -- breakout_wait (buy band, no resistance, WAIT_FOR_PULLBACK):", len(bw), [(s["ticker"], round(s["score"],1)) for s in bw][:12])
    top = [s for s in sw if s.get("band") in ("STRONG_BUY_CANDIDATE","BUY_CANDIDATE")]
    print(" -- swing buy-band cards:", len(top))
    for s in sorted(top, key=lambda s: -s["score"])[:12]:
        p, st, tg = s.get("price"), s.get("stop"), s.get("target")
        atr = order_plan.atr_of(s)
        print("    ", s["ticker"], "score", round(s["score"],1), s.get("band"), s.get("entry_status"), "rrF", fac(s,"risk_reward").get("normalized"), "rr_raw", fac(s,"risk_reward").get("raw"),
              "trend", fac(s,"trend_structure").get("normalized"), "tgt_atr", None if not atr or not tg else round((tg-p)/atr,2), "conf", s.get("confidence"), (s.get("entry_reason") or "")[:60])
    en = [s for s in sw if s.get("entry_status") == "ENTRY_NOW"]
    print(" -- swing ENTRY_NOW:", len(en), "by band", collections.Counter(s.get("band") for s in en))
    for s in sorted(en, key=lambda s: -s["score"])[:8]:
        p, st, tg = s.get("price"), s.get("stop"), s.get("target"); atr = order_plan.atr_of(s)
        print("    ", s["ticker"], round(s["score"],1), s.get("band"), "trend", fac(s,"trend_structure").get("normalized"), "mom", fac(s,"momentum").get("normalized"), "rrF", fac(s,"risk_reward").get("normalized"), "tgt_atr", None if not atr or not tg else round((tg-p)/atr,2))
    tr = sorted(x for x in (fac(s,"trend_structure").get("normalized") for s in en) if x is not None)
    if tr: print("    trend factor of ENTRY_NOW swing: median", tr[len(tr)//2], "share<0.5", sum(x<0.5 for x in tr)/len(tr))
    tra = sorted(x for x in (fac(s,"trend_structure").get("normalized") for s in sw) if x is not None)
    if tra: print("    trend factor of all swing: median", tra[len(tra)//2])
    lg = [s for s in snaps if s.get("strategy") == "LONG_TERM" and s.get("entry_status") == "ENTRY_NOW"]
    print(" -- long ENTRY_NOW:", len(lg), collections.Counter(s.get("band") for s in lg))
    c = order_plan.candidates(snaps, "2026-11-25")
    print(" -- plan candidates:", len(c), order_plan.count_by(c))
