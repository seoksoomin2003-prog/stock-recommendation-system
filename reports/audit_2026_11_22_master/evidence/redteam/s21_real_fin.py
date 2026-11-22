"""Newest US session: how the committee judges 'Financial Services' names.  Scores and stored figures only; no returns."""
from common import *
from pathlib import Path
from collections import Counter
from terminal.qsf.ledger import Ledger
from terminal.cache import FileCache
from terminal.committee import figures as fg, investors as iv, council
from terminal.committee import service as cs
from terminal import analyst_extra as ax
led = Ledger(Path(REPO)); cache = FileCache(Path(REPO) / "data" / "qsf" / "cache")
rows = led._live_rows(); last = max(r["session"] for r in rows if r["market"] == "US")
snaps = [s for r in rows if r["market"] == "US" and r["session"] == last for s in led._load(r) if s.get("data_date") == last]
lt = {s["ticker"]: s for s in snaps if s["strategy"] == "LONG_TERM"}; sw = {s["ticker"]: s for s in snaps if s["strategy"] == "SWING"}
def build(force=None):
    figs = {}
    for t in sorted(set(lt) | set(sw)):
        if t in cs.BENCHMARKS: continue
        info = (cache.read(f"info:{t}") or {}).get("data") or {}
        sector = ax.SECTOR_KO.get(info.get("sector"), info.get("sector"))
        if force and t in force: sector = force[t]
        f = fg.read(lt.get(t), sw.get(t), info, sector); f["name"] = t; figs[t] = f
    c = cs.context(figs)
    return figs, c, {t: cs.judge(f, None, c) for t, f in figs.items()}
figs, c, book = build()
print("session", last, "| market state", next(f["market_state"] for f in figs.values() if f["market_state"] is not None), "| regimes", [r["regime"] for r in iv.regimes(next(iter(figs.values())))])
print("financial ROE peers:", {k: round(v, 3) if isinstance(v, float) else v for k, v in c["financial_roe"].items()})
names = ["V", "MA", "SPGI", "MCO", "MSCI", "CME", "ICE", "AON", "PYPL", "FDS", "NDAQ", "CBOE"]
figs2, c2, book2 = build({t: "산업재" for t in names})       # the same stored figures, read as an ordinary company (what the QSF score does)
print("\nticker | as FINANCIAL (committee today): decision, confidence, [B M G L D] | read as an ordinary company: decision, confidence, [B M G L D]")
code = {"STRONG_BUY": "S", "BUY": "B", "HOLD": "H", "WAIT": "W", "REDUCE": "R", "SELL": "X", "AVOID": "A", "INSUFFICIENT_DATA": "N", "CONDITIONAL_BUY": "C"}
for t in names:
    a, b = book[t], book2[t]
    row = lambda e: f"{e['committee']['decision']:16s} conf {e['committee']['scores']['confidence']} [{''.join(code[e['opinions'][k]['recommendation']] for k in iv.ORDER)}]"
    f = figs2[t]
    print(f"{t:5s} | {row(a)} | {row(b)} | stored: ROE {f['roe']}, op_margin {f['op_margin']}, D/E {f['debt_equity']}, no_equity {f['no_equity']}, PER {f['pe'] and round(f['pe'],1)}")
print("\n--- a bank: on how many figures is each engine judging, and how sure does it say it is?")
for t in ("JPM", "BAC", "WFC", "MTB", "SYF"):
    e, f = book[t], figs[t]
    na = [k for k, v in f["_status"].items() if v == fg.NOT_APPLICABLE]
    print(f"{t}: committee {e['committee']['decision']} confidence {e['committee']['scores']['confidence']} data {e['committee']['scores']['data']} | not-applicable figures: {len(na)}")
    for k in iv.ORDER:
        o = e["opinions"][k]
        print(f"    {k:14s} {o['recommendation']:18s} score {o['score']} confidence {o['confidence']} coverage {o['coverage']} figures used {len(o['evidence'])}: {[x['text'][:22] for x in o['evidence']][:6]}")
# every financial: evidence count vs confidence for Buffett and Munger
fin = [t for t, f in figs.items() if f["kind"] == "FINANCIAL"]
for k in ("BUFFETT", "MUNGER"):
    xs = [(len(book[t]["opinions"][k]["evidence"]), book[t]["opinions"][k]["confidence"], book[t]["opinions"][k]["recommendation"]) for t in fin if book[t]["opinions"][k]["recommendation"] != "INSUFFICIENT_DATA"]
    print(f"{k} on {len(xs)} financials: figures used min/median/max {min(x[0] for x in xs)}/{sorted(x[0] for x in xs)[len(xs)//2]}/{max(x[0] for x in xs)}; confidence min/median/max {min(x[1] for x in xs)}/{sorted(x[1] for x in xs)[len(xs)//2]}/{max(x[1] for x in xs)}; recs {dict(Counter(x[2] for x in xs))}")
gen = [t for t, f in figs.items() if f["kind"] != "FINANCIAL"]
for k in ("BUFFETT", "MUNGER"):
    xs = [(len(book[t]["opinions"][k]["evidence"]), book[t]["opinions"][k]["confidence"]) for t in gen if book[t]["opinions"][k]["recommendation"] != "INSUFFICIENT_DATA"]
    print(f"{k} on {len(xs)} non-financials: figures used median {sorted(x[0] for x in xs)[len(xs)//2]}; confidence median {sorted(x[1] for x in xs)[len(xs)//2]}")
