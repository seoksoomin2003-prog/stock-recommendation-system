"""Agent 4: Korean replay rows without statements: are they names that later left the market?  Reads only whether a stock still
has a close on the panel's last day (listed or not) - no return, no price level is used."""
import gzip, json
from collections import Counter, defaultdict
import numpy as np
d = json.load(gzip.open("research_data/krx_live/scores_cap.json.gz", "rt"))
dates, recs = d["dates"], d["records"]
corp = json.load(open("research_data/krx_live/corp_codes.json"))
with np.load("research_data/krx_live/panel.npz", allow_pickle=False) as z:
    syms = [str(s) for s in z["symbols"]]; pdates = [str(x) for x in z["dates"]]
    last = z["close"][-1]
    listed = {s for s, v in zip(syms, last) if np.isfinite(v)}
print("panel last day", pdates[-1], "symbols", len(syms), "listed on last day", len(listed))
tab = defaultdict(Counter)
names = defaultdict(set)
for r in recs:
    y = dates[r["i"]][:4]
    gone = r["t"] not in listed
    tab[y]["rows"] += 1
    tab[y]["gone_later"] += gone
    if r.get("fund_status") == "UNAVAILABLE":
        tab[y]["unavail"] += 1
        tab[y]["unavail_gone"] += gone
        tab[y]["unavail_no_corp"] += r["t"] not in corp
        names[y].add(r["t"])
print("year rows unavailable share | of universe rows: later delisted | of unavailable: later delisted, no DART code")
out = {}
for y in sorted(tab):
    t = tab[y]
    print(y, t["rows"], t["unavail"], f"{t['unavail']/t['rows']:.1%}", "|", f"{t['gone_later']/t['rows']:.1%}", "|", f"{t['unavail_gone']/max(t['unavail'],1):.1%}", f"{t['unavail_no_corp']/max(t['unavail'],1):.1%}", "names", len(names[y]))
    out[y] = dict(t)
T = Counter()
for t in tab.values(): T.update(t)
print("all", dict(T), f"gone among all rows {T['gone_later']/T['rows']:.1%}; gone among unavailable {T['unavail_gone']/T['unavail']:.1%}; gone rows without statements {T['unavail_gone']/max(T['gone_later'],1):.1%}; staying rows without statements {(T['unavail']-T['unavail_gone'])/(T['rows']-T['gone_later']):.1%}")
json.dump(out, open(__file__.replace(".py", ".json"), "w"), indent=1)
