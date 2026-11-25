"""Agent 4: how much of the day's universe do the stored replay scores cover?  Scores only (counts); no price, no return is read."""
import bisect, csv, gzip, json
from collections import defaultdict
from pathlib import Path
root = Path("data/qsf/research")
doc = json.load(gzip.open(root/"scores_current_us.json.gz", "rt"))
dates, recs = doc["dates"], doc["records"]
rows = sorted((r[0], {x.strip().upper().replace(".", "-") for x in ",".join(r[1:]).strip('"').split(",") if x.strip()}) for r in csv.reader(open(root/"survivorship/hist_updated.csv", newline="", encoding="utf-8")) if r and r[0][:2] in ("19", "20"))
keys, snaps = [d for d, _ in rows], [s for _, s in rows]
by = defaultdict(list)
for r in recs: by[r["i"]].append(r)
yr = defaultdict(lambda: defaultdict(float))
for i, g in by.items():
    d = dates[i]; y = d[:4]
    snap = snaps[bisect.bisect_right(keys, d) - 1]
    yr[y]["days"] += 1; yr[y]["index"] += len(snap)
    yr[y]["rows"] += len(g)
    yr[y]["swing"] += sum(1 for r in g if r.get("SWING") is not None)
    yr[y]["long"] += sum(1 for r in g if r.get("LONG_TERM") is not None)
    yr[y]["in_snap"] += sum(1 for r in g if r["t"] in snap)
print("US model_version", doc.get("model_version"), "last snapshot", keys[-1], "evaluation days", len(by))
print("year days index rows swing long  swing/index long/index  rows_not_in_snapshot")
out = {"US": {}, "KR": {}}
for y in sorted(yr):
    v = yr[y]; n = v["days"]
    print(y, int(n), round(v["index"]/n), round(v["rows"]/n), round(v["swing"]/n), round(v["long"]/n), f"{v['swing']/v['index']:.1%}", f"{v['long']/v['index']:.1%}", round((v["rows"]-v["in_snap"])/n, 1))
    out["US"][y] = {k: v[k]/n for k in ("index", "rows", "swing", "long")}
T = {k: sum(v[k] for v in yr.values()) for k in ("index", "swing", "long")}
print("all", f"{T['swing']/T['index']:.1%}", f"{T['long']/T['index']:.1%}")
kd = json.load(gzip.open("research_data/krx_live/scores_current_cap.json.gz", "rt"))
kdates, krecs = kd["dates"], kd["records"]
kby = defaultdict(list)
for r in krecs: kby[r["i"]].append(r)
ky = defaultdict(lambda: defaultdict(float))
for i, g in kby.items():
    y = kdates[i][:4]
    ky[y]["days"] += 1; ky[y]["rows"] += len(g)
    ky[y]["swing"] += sum(1 for r in g if r.get("SWING") is not None)
    ky[y]["long"] += sum(1 for r in g if r.get("LONG_TERM") is not None)
print("\nKR model_version", kd.get("model_version"), "evaluation days", len(kby))
print("year days rows swing long")
for y in sorted(ky):
    v = ky[y]; n = v["days"]
    print(y, int(n), round(v["rows"]/n), round(v["swing"]/n), round(v["long"]/n))
    out["KR"][y] = {k: v[k]/n for k in ("rows", "swing", "long")}
json.dump(out, open(Path(__file__).with_name("s5_replay_coverage.json"), "w"), indent=1)
