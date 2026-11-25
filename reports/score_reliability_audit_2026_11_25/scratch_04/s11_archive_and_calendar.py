"""Agent 4: (1) open-archive names scored on days whose horizon ends after the archive (their outcome is then empty and they leave
the sample after being scored); (2) KRX sessions per calendar year in the replay panel.  Dates and scores only; no return."""
import gzip, json
from collections import Counter
doc = json.load(gzip.open("data/qsf/research/scores_current_us.json.gz", "rt"))
dates, recs = doc["dates"], doc["records"]
names = set(json.load(open("reports/qsf/QSF_OPEN_UNIVERSE.json")))
END = "2017-03-31"
arch = [r for r in recs if r["t"] in names]
print("archive names scored:", len({r['t'] for r in arch}), "rows", len(arch), "of", len(recs), f"({len(arch)/len(recs):.1%})", "first", dates[min(r['i'] for r in arch)], "last", dates[max(r['i'] for r in arch)])
out = {}
for key, h in (("SWING", 20), ("SWING", 21), ("LONG_TERM", 63), ("LONG_TERM", 126), ("LONG_TERM", 252)):
    scored = [r for r in arch if r.get(key) is not None]
    lost = [r for r in scored if r["i"] + h < len(dates) and dates[r["i"] + h] > END]
    days = sorted({dates[r["i"]] for r in lost})
    print(key, h, "scored archive rows", len(scored), "outcome empty (horizon past the archive end)", len(lost), f"{len(lost)/max(len(scored),1):.1%}", "days", (days[0], days[-1]) if days else None)
    out[f"{key}_{h}"] = {"scored": len(scored), "lost": len(lost)}
by = Counter()
for r in arch: by[dates[r["i"]][:4]] += 1
print("archive rows by year", dict(sorted(by.items())))
kd = json.load(gzip.open("research_data/krx_live/scores_current_cap.json.gz", "rt"))
yc = Counter(d[:4] for d in kd["dates"])
print("KRX sessions per year in the panel:", {y: n for y, n in sorted(yc.items()) if "2019" <= y <= "2025"})
json.dump({"archive": out, "kr_sessions": dict(yc)}, open(__file__.replace(".py", ".json"), "w"), indent=1)
