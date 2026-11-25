"""Agent 4: Korean annual statements kept for the replay: receipt date (first 8 digits of rcept_no) against the business year.
A receipt long after the March deadline means the API served a corrected report (restated values, later date).  No prices, no returns."""
import gzip, json
from collections import Counter
from datetime import date
from pathlib import Path
root = Path("research_data/dart/single")
out = {}
tot = Counter(); late = Counter(); very = Counter(); empty = Counter(); nextyear = Counter()
for ydir in sorted(p for p in root.iterdir() if p.is_dir()):
    y = int(ydir.name)
    for f in ydir.glob("*.json.gz"):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            rec = json.load(fh)
        rows = rec.get("rows") or []
        if not rows:
            empty[y] += 1; continue
        r = str(rows[0][0] or "")
        if len(r) < 8: continue
        d = date(int(r[:4]), int(r[4:6]), int(r[6:8]))
        lag = (d - date(y, 12, 31)).days      # December year-end assumed (all but a few companies)
        tot[y] += 1
        if lag > 120: late[y] += 1            # after April: not the first filing of a December company
        if lag > 365: very[y] += 1
        if lag > 455: nextyear[y] += 1
print("year  files  empty  receipt>120d  >365d  >455d   share>120d")
for y in sorted(tot):
    print(y, tot[y], empty[y], late[y], very[y], nextyear[y], f"{late[y]/tot[y]:.1%}")
    out[y] = {"files": tot[y], "empty": empty[y], "late120": late[y], "late365": very[y], "late455": nextyear[y]}
T = sum(tot.values()); print("all", T, sum(late.values()), f"{sum(late.values())/T:.1%}", sum(very.values()), f"{sum(very.values())/T:.1%}")
json.dump(out, open(Path(__file__).with_name("s4_dart_receipt_lag.json"), "w"), indent=1)
