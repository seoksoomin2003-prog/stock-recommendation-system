"""Agent 4: when was each ledger shard written relative to the next open?  No prices, no outcomes."""
import gzip, json, sys
from collections import Counter
from datetime import datetime, time, date
from pathlib import Path
from zoneinfo import ZoneInfo
base = Path(".")
rows = [json.loads(l) for l in (base/"data/qsf/ledger/index.jsonl").read_text().splitlines()]
void = {r["file"] for r in rows if r.get("type") == "VOID"}
NY, SEOUL = ZoneInfo("America/New_York"), ZoneInfo("Asia/Seoul")
out = []
for r in rows:
    if r.get("type") == "VOID":
        continue
    with gzip.open(base/"data/qsf/ledger"/r["file"], "rt") as fh:
        snaps = [json.loads(x) for x in fh]
    rec = sorted(s["recorded_at"] for s in snaps if s.get("recorded_at"))
    entries = Counter(s.get("entry_session") for s in snaps)
    dd = Counter(s.get("data_date") for s in snaps)
    first, last = datetime.fromisoformat(rec[0]), datetime.fromisoformat(rec[-1])
    es = entries.most_common(1)[0][0]
    tz, op = (NY, time(9, 30)) if r["market"] == "US" else (SEOUL, time(9, 0))
    open_at = datetime.combine(date.fromisoformat(es), op, tzinfo=tz)
    stale_price = sum(n for d, n in dd.items() if d != r["session"])
    act = Counter(s.get("actionability") for s in snaps)
    out.append({"seq": r["seq"], "void": r["file"] in void, "session": r["session"], "market": r["market"], "version": r["model_version"], "n": len(snaps),
                "first_rec_local": first.astimezone(tz).strftime("%m-%d %H:%M"), "last_rec_local": last.astimezone(tz).strftime("%m-%d %H:%M"),
                "entry_session": es, "n_entry_sessions": len(entries), "before_open": last < open_at, "hours_before_open": round((open_at - last).total_seconds()/3600, 1),
                "data_date_not_session": stale_price, "actionability": dict(act)})
for o in out:
    print(o)
json.dump(out, open(Path(__file__).with_name("s1_ledger_timing.json"), "w"), indent=1)
