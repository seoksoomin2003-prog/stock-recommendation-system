"""Read-only: receipt dates of stored Korean annual statements (krfund3) by fiscal year end, to see whether amended values carry a
later receipt date (PIT-safe) or the original one.  Also: krlist2 copies with and without the new 'end' field, and their ages."""
import json, glob, sys
from collections import Counter
from pathlib import Path
repo = Path.home() / "Developer/quant-stock-engine"
late, months, n, lag = Counter(), Counter(), 0, []
for p in glob.glob(str(repo / "data/qsf/cache/krfund3_*.json")):
    d = json.load(open(p)).get("data") or {}
    for metric in ("revenue", "net_income", "equity"):
        for r in d.get(metric) or []:
            if not r.get("filed") or not r.get("end"):
                continue
            n += 1
            days = (int(r["filed"][:4]) - int(r["end"][:4])) * 365 + (int(r["filed"][5:7]) - int(r["end"][5:7])) * 30 + int(r["filed"][8:10]) - int(r["end"][8:10])
            lag.append(days)
            months[r["filed"][:7]] += 1
            if days > 120:
                late[(Path(p).name[:16], r["end"], r["filed"])] += 1
import statistics
print("rows", n, "median lag days", statistics.median(lag), "rows filed >120 days after FY end:", sum(1 for x in lag if x > 120))
print("examples of late receipt (likely amended reports):", list(late)[:8])
ends, ages, n2 = Counter(), [], 0
import time
for p in glob.glob(str(repo / "data/qsf/cache/krlist2_*.json")):
    rec = json.load(open(p)); d = rec.get("data") or {}
    n2 += 1; ends[d.get("end")] += 1; ages.append(round((time.time() - rec["stored_at"]) / 3600))
print("krlist2 copies", n2, "by end:", dict(ends.most_common(6)), "age hours min/median/max", min(ages), statistics.median(ages), max(ages))
