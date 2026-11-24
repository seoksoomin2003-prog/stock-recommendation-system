"""Agent 02: how many long-term cards that read 'no condition blocks entry' (ENTRY_NOW) on the newest session would, if the
stock were held, meet the holding rule PROFITABILITY_DOWN (ROE fell more than 5 points and is under 8%, holding.py) -- i.e.
the same fact that invalidates a held thesis does not stop a new entry.  Uses today's fundamentals.metrics on the stored
statement copies (no provider).  ROE only; no returns."""
import sys
from pathlib import Path
repo = Path.home() / "Developer" / "quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import fundamentals
from terminal.qsf.service import _us_fund_key, _kr_fund_key
from terminal.cache import FileCache
cache = FileCache(repo / "data" / "qsf" / "cache")
led = Ledger(repo)
for m in ("US", "KR"):
    row = [r for r in led._live_rows() if r["market"] == m][-1]
    snaps = [s for s in led._load(row) if s["strategy"] == "LONG_TERM"]
    hits, seen, nocache = [], 0, 0
    for s in snaps:
        if s.get("entry_status") != "ENTRY_NOW":
            continue
        seen += 1
        key = _us_fund_key(s["ticker"], s.get("cik")) if m == "US" else _kr_fund_key(s["ticker"], 12)
        rec = cache.read(key)
        if not rec or not rec.get("data"):
            nocache += 1
            continue
        f = fundamentals.metrics(rec["data"], s.get("price"), row["session"])
        roe, prev = f.get("roe"), f.get("roe_prev")
        if roe is not None and prev is not None and roe < prev - 0.05 and roe < 0.08:
            hits.append((s["ticker"], round(prev, 3), round(roe, 3), round(s["score"], 1), s["band"]))
    print(m, row["session"], "ENTRY_NOW long cards", seen, "no stored copy", nocache, "meeting PROFITABILITY_DOWN:", len(hits))
    for h in sorted(hits, key=lambda h: -h[3]):
        print("   ", h)
