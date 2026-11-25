"""Agent 02 recheck: apply today's fund_checks.read to the newest stored ledger session (11-24) with today's
fundamentals.metrics on the stored statement copies (no provider).  Counts patterns among long cards, buy band and entry
status.  No returns.  is_financial approximated from the card (leverage NOT_APPLICABLE)."""
import sys
from collections import Counter
from pathlib import Path
repo = Path.home() / "Developer" / "quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import fundamentals
from terminal.cache import FileCache
from terminal import fund_checks
from terminal import sources
cache = FileCache(repo / "data" / "qsf" / "cache")
led = Ledger(repo)
for m in ("US", "KR"):
    row = [r for r in led._live_rows() if r["market"] == m][-1]
    snaps = [s for s in led._load(row) if s["strategy"] == "LONG_TERM"]
    pat, dirs, buy_trap, entry_trap, nocopy = Counter(), Counter(), [], [], 0
    for s in snaps:
        if m == "US":
            k5, k4 = f"annual5:{sources.facts_key(s['ticker'], s.get('cik'))}", f"annual4:{sources.facts_key(s['ticker'], s.get('cik'))}"
            rec = cache.read(k5) or cache.read(k4)
        else:
            rec = cache.read(f"krfund3:{s['ticker']}")
        if not rec or not rec.get("data"):
            nocopy += 1; continue
        fin = any(f["factor"] == "leverage" and f.get("status") == "NOT_APPLICABLE" for f in s["factors"])
        f = fundamentals.metrics(rec["data"], s.get("price"), row["session"], is_financial=fin)
        fc = fund_checks.read(f, s)
        dirs[fc["direction"]] += 1
        pat[fc["pattern"]] += 1
        if fc["pattern"] == "CHEAP_AND_WORSENING":
            if s["band"] in ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE"):
                buy_trap.append((s["ticker"], round(s["score"], 1)))
            if s.get("entry_status") == "ENTRY_NOW":
                entry_trap.append(s["ticker"])
    print(m, row["session"], row["model_version"], "long cards", len(snaps), "no copy", nocopy)
    print("  direction:", dict(dirs))
    print("  pattern:", dict(pat))
    print("  CHEAP_AND_WORSENING in buy band:", len(buy_trap), buy_trap)
    print("  CHEAP_AND_WORSENING with ENTRY_NOW:", len(entry_trap))
