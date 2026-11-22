"""Newest US session: which rule made each committee buy decision, and what the six portfolios hold at this market state.  No returns."""
from common import *
from pathlib import Path
from collections import Counter
from terminal.qsf.ledger import Ledger
from terminal.cache import FileCache
from terminal.committee import figures as fg, investors as iv, council, portfolios
from terminal.committee import service as cs
from terminal import analyst_extra as ax
led = Ledger(Path(REPO)); cache = FileCache(Path(REPO) / "data" / "qsf" / "cache")
rows = led._live_rows(); last = max(r["session"] for r in rows if r["market"] == "US")
snaps = [s for r in rows if r["market"] == "US" and r["session"] == last for s in led._load(r) if s.get("data_date") == last]
lt = {s["ticker"]: s for s in snaps if s["strategy"] == "LONG_TERM"}; sw = {s["ticker"]: s for s in snaps if s["strategy"] == "SWING"}
figs = {}
for t in sorted(set(lt) | set(sw)):
    if t in cs.BENCHMARKS: continue
    info = (cache.read(f"info:{t}") or {}).get("data") or {}
    f = fg.read(lt.get(t), sw.get(t), info, ax.SECTOR_KO.get(info.get("sector"), info.get("sector"))); f["name"] = t; figs[t] = f
c = cs.context(figs)
book = {t: cs.judge(f, None, c) for t, f in figs.items()}
buys = {t: e for t, e in book.items() if e["committee"]["decision"] in ("BUY", "STRONG_BUY", "CONDITIONAL_BUY")}
shape = Counter((len(e["committee"]["buyers"]), len(e["committee"]["against"])) for e in buys.values())
print("committee buy-side decisions:", len(buys), "| (buyers, against) ->", dict(sorted(shape.items())))
lone = [(t, e["committee"]["decision"], e["committee"]["buyers"], e["committee"]["against"], f"{(figs[t]['price'] / figs[t]['ma200'] - 1) * 100:+.1f}% vs MA200" if figs[t].get("ma200") else None) for t, e in buys.items() if len(e["committee"]["buyers"]) == 1 and len(e["committee"]["against"]) >= 3]
print(f"one buyer, three or more against, still a buy decision: {len(lone)}")
for x in lone[:10]:
    print("   ", x)
below = [t for t, e in buys.items() if figs[t].get("ma200") and figs[t]["price"] < figs[t]["ma200"]]
print(f"committee buy-side decisions with the price under its 200-day average: {len(below)} of {len(buys)}")
who = Counter(b for e in buys.values() for b in e["committee"]["buyers"])
print("who the buyers are:", dict(who))
state = next(f["market_state"] for f in figs.values() if f["market_state"] is not None)
ports = portfolios.build(book, None, state, None)
print(f"\nmarket state {state:.1f}: six portfolios built from this session (no previous holdings, correlation check off)")
for k, p in ports.items():
    print(f"   {k:14s} holdings {p['count']:2d} invested {p['invested'] * 100:5.1f}% cash {p['cash'] * 100:5.1f}% exposure limit {p['exposure_limit']} largest {p['largest']} sectors {dict(list(p['sectors'].items())[:3])}")
ports0 = portfolios.build(book, None, None, None)
print("the same with the market state MISSING (None):", {k: p["invested"] for k, p in ports0.items()})
