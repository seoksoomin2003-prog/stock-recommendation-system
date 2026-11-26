"""Counts only (no price, no return): sessions in the verdict sample, duplicates per session, and how the band of 70 overlaps the entry status."""
from collections import Counter
from pathlib import Path
from terminal.qsf.ledger import Ledger
from terminal.qsf import live_forward as lf
led = Ledger(Path("."))
print("verify", led.verify()["status"])
rows = led._live_rows()
per = Counter((r["market"], r["session"]) for r in rows)
print("live shards", len(rows), "sessions with more than one live shard:", {k: v for k, v in per.items() if v > 1})
print("voided rows:", sum(1 for r in led.read_index()["rows"] if r.get("type") == "VOID"))
for m in ("US", "KR"):
    mine = [r for r in rows if r["market"] == m]
    print(m, "sessions", len({r["session"] for r in mine}), "first", mine[0]["session"], "last", mine[-1]["session"], "from FIRST:", sorted({r["session"] for r in mine if r["session"] >= lf.FIRST}))
    snaps = led._load(mine[-1])
    print("  last shard", mine[-1]["session"], "rows", len(snaps), "versions", Counter(s.get("model_version") for s in snaps), "rules", Counter(s.get("rules_version") for s in snaps))
    print("  fields", sorted(snaps[0])[:60])
    for st in ("SWING", "LONG_TERM"):
        ss = [s for s in snaps if s.get("strategy") == st and s.get("score") is not None]
        counted = [s for s in ss if s.get("actionability") != "INSUFFICIENT_DATA" and s.get("data_date") == mine[-1]["session"]]
        band = [s for s in counted if s["score"] >= 70]
        print("  ", st, "scored", len(ss), "counted by verdict", len(counted), ">=70:", len(band), "max score", round(max(s["score"] for s in ss), 1),
              "| actionability of >=70:", dict(Counter(s.get("actionability") for s in band)), "| entry_status of >=70:", dict(Counter(str(s.get("entry_status")) for s in band)),
              "| entry-ok cards overall:", dict(Counter(str(s.get("entry_status")) for s in counted)), "| fund_period live:", dict(Counter(str((s.get("fund_period") or {}).get("live")) for s in counted)))
