"""Read-only: per ledger shard, model version, record time vs the next session's open, data_date vs session, provenance labels.
No prices, no returns."""
import gzip, json, sys
from collections import Counter
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from pathlib import Path
repo = Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from utils import nyse_calendar
led = Ledger(repo)
print("verify:", led.verify())
out = []
for row in led._live_rows():
    snaps = led._load(row)
    m, sess = row["market"], row["session"]
    rec = sorted(s.get("recorded_at") for s in snaps if s.get("recorded_at"))
    first = datetime.fromisoformat(rec[0]); last = datetime.fromisoformat(rec[-1])
    d = date.fromisoformat(sess)
    # next open: US 09:30 NY next weekday (holidays ignored, approx), KR 09:00 Seoul next weekday
    n = d + timedelta(days=1)
    while n.weekday() >= 5: n += timedelta(days=1)
    if m == "US":
        nxt = datetime(n.year, n.month, n.day, 9, 30, tzinfo=ZoneInfo("America/New_York"))
    else:
        nxt = datetime(n.year, n.month, n.day, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    dd = Counter(s.get("data_date") for s in snaps)
    conf = Counter(s.get("confidence") for s in snaps)
    prov = Counter()
    stale = 0
    for s in snaps:
        p = s.get("provenance") or {}
        if isinstance(p, dict):
            prov[str(p.get("price"))[:40]] += 1
            if p.get("stale"): stale += 1
    out.append({"file": row["file"], "market": m, "session": sess, "model": row.get("model_version"), "records": len(snaps),
                "first_rec_local": first.astimezone(ZoneInfo("Asia/Seoul")).strftime("%m-%d %H:%M KST"),
                "last_rec_local": last.astimezone(ZoneInfo("Asia/Seoul")).strftime("%m-%d %H:%M KST"),
                "before_next_open": last < nxt, "data_dates": dict(dd.most_common(3)), "confidence": dict(conf),
                "price_label": dict(prov.most_common(2)), "cards_with_stale_inputs": stale})
for o in out:
    print(json.dumps(o, ensure_ascii=False))
json.dump(out, open(repo / "reports/maturity_assessment_2026_11_25/evidence/agent_05/ledger_timeliness.json", "w"), ensure_ascii=False, indent=1)
