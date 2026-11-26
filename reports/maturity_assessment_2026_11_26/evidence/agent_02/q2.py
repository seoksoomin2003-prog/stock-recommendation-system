"""Question 2 on recorded cards of one session: no returns."""
import sys
from pathlib import Path
from collections import Counter
import numpy as np
from terminal.qsf.ledger import Ledger
led = Ledger(Path(".")); rows = led._live_rows(); market = sys.argv[1]
snaps = led._load([r for r in rows if r["market"] == market][-1])
def fac(c, f):
    r = next((x for x in c["factors"] if x["factor"] == f), None)
    return r["normalized"] if r and r.get("normalized") is not None and r.get("status") in ("REAL", "STALE") else None
def raw(c, f, k):
    r = next((x for x in c["factors"] if x["factor"] == f), None)
    return (r.get("raw") or {}).get(k) if r else None
BUY = ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE")
for strat in ("LONG_TERM", "SWING"):
    cs = [c for c in snaps if c["strategy"] == strat]
    buy = [c for c in cs if c["band"] in BUY]
    print(f"\n== {market} {strat} n={len(cs)} buy-band={len(buy)}")
    fc = lambda c: (c.get("fund_checks") or {})
    print("direction all:", dict(Counter(fc(c).get("direction") for c in cs)))
    print("direction buy band:", dict(Counter(fc(c).get("direction") for c in buy)))
    print("pattern all:", dict(Counter(fc(c).get("pattern") for c in cs)))
    print("pattern buy band:", dict(Counter(fc(c).get("pattern") for c in buy)))
    print("buy band x entry_status x direction:", dict(Counter((c.get("entry_status"), fc(c).get("direction")) for c in buy)))
    flags = Counter(f["code"] for c in buy for f in fc(c).get("flags") or [])
    print("flags in buy band:", dict(flags))
    if strat == "LONG_TERM":
        v = np.array([np.nan if fac(c, "valuation") is None else fac(c, "valuation") for c in cs]); q = np.array([np.nan if fac(c, "business_quality") is None else fac(c, "business_quality") for c in cs])
        g = np.array([np.nan if fac(c, "growth_quality") is None else fac(c, "growth_quality") for c in cs]); s = np.array([c["score"] if c["score"] is not None else np.nan for c in cs])
        lt = np.array([np.nan if fac(c, "long_trend") is None else fac(c, "long_trend") for c in cs])
        def desc(name, m):
            print(f"  {name}: n={int(m.sum())} median score={np.nanmedian(s[m]) if m.sum() else None!s:.6} share score>=70={np.nanmean(s[m] >= 70) if m.sum() else float('nan'):.2f} entry:", dict(Counter(c.get('entry_status') for c, k in zip(cs, m) if k)))
        desc("quality>=0.8 & valuation<=0.25 (good business, dear)", (q >= .8) & (v <= .25))
        desc("quality>=0.8 & valuation 0.25-0.4 (good, fairly dear, not blocked)", (q >= .8) & (v > .25) & (v <= .4))
        desc("valuation>=0.8 & growth<=0.2 (cheap, shrinking)", (v >= .8) & (g <= .2))
        desc("valuation>=0.8 & long_trend<=0.2 (cheap, falling price)", (v >= .8) & (lt <= .2))
        desc("valuation>=0.8 & quality<=0.3 (cheap, poor business)", (v >= .8) & (q <= .3))
        desc("growth>=0.8 & valuation<=0.25 (growth, dear)", (g >= .8) & (v <= .25))
        desc("growth>=0.8 & valuation>=0.6 (growth, cheap)", (g >= .8) & (v >= .6))
        # raw one-year changes among buy band
        eg = [raw(c, "growth_quality", "rev_growth") for c in buy]
        print("  buy band: rev_growth<0:", sum(1 for x in eg if x is not None and x < 0), "of", len(buy))
        ec = [raw(c, "growth_quality", "eps_cagr3") for c in buy]
        print("  buy band: eps_cagr3<0:", sum(1 for x in ec if x is not None and x < 0), " eps_cagr3 missing:", sum(1 for x in ec if x is None))
        pes = [raw(c, "valuation", "pe") for c in cs]; print("  PE<=0 count all:", sum(1 for x in pes if x is not None and x <= 0), " PE None:", sum(1 for x in pes if x is None))
        vb = [fac(c, "valuation") for c in buy if fac(c, "valuation") is not None]; print("  buy band valuation normalized quartiles:", np.round(np.percentile(vb, [0, 25, 50, 75, 100]), 2) if vb else None)
    if strat == "SWING":
        # fund_period, fuller inputs keys
        c0 = cs[0]; print("  fund_period keys:", list((c0.get("fund_period") or {}).keys()), " fuller_inputs keys:", list((c0.get("fuller_inputs") or {}).keys()) if c0.get("fuller_inputs") else None)
        ms = Counter()
    ms = cs[0]
print("market_state stored in snapshot?", "market_state" in snaps[0], " regime rows:", [(r["factor"], r.get("normalized"), r.get("status")) for r in snaps[0]["factors"] if r["domain"] == "REGIME"])
