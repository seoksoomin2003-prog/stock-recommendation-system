"""Agent 01 cross review of Agent 03: is the Korean swing score's day-to-day reshuffle (record 2026-11-19 -> 2026-11-20) the risk_reward factor?
Scores and factor values of two recorded sessions only, one shard in memory at a time.  No price, no return."""
import sys
from pathlib import Path
import pandas as pd
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
led = Ledger(REPO)

def day(market, session):
    out = {}
    for r in led._live_rows():
        if r["market"] == market and r["session"] == session:
            for s in led._load(r):
                if s["strategy"] == "SWING" and s.get("score") is not None and s.get("data_date") == session:
                    out[s["ticker"]] = {f["factor"]: (f["weight"], f["normalized"]) for f in s["factors"] if f.get("scored") is not False and f.get("normalized") is not None and f.get("status") in ("REAL", "STALE")}
    return out

def score(rows, swap=None):
    w = c = 0.0
    for f, (weight, norm) in rows.items():
        norm = swap[f] if swap and f in swap else norm
        w, c = w + weight, c + weight * norm
    return 100 * c / w

for market in ("KR", "US"):
    a, b = day(market, "2026-11-19"), day(market, "2026-11-20")
    keys = sorted(set(a) & set(b))
    s0 = pd.Series({t: score(a[t]) for t in keys}); s1 = pd.Series({t: score(b[t]) for t in keys})
    print(f"{market} swing, {len(keys)} stocks: rank correlation {s0.rank().corr(s1.rank()):.4f}; moves over 3 points {((s1 - s0).abs() > 3).mean():.1%}")
    names = sorted({f for t in keys for f in b[t]})
    res = []
    for f in names:
        held = pd.Series({t: score(b[t], {f: a[t][f][1]}) if f in a[t] and f in b[t] else score(b[t]) for t in keys})
        jump = sum(1 for t in keys if f in a[t] and f in b[t] and abs(a[t][f][1] - b[t][f][1]) >= 0.5)
        res.append((s0.rank().corr(held.rank()), f, ((held - s0).abs() > 3).mean(), jump))
    for rho, f, big, jump in sorted(res, reverse=True)[:4]:
        print(f"   with {f:26s} held at its 11-19 value: rank correlation {rho:.4f}; moves over 3 points {big:.1%}; stocks whose factor value moved by 0.5 or more in the day: {jump}")
    del a, b
