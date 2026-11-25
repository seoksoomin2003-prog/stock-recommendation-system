"""Agent 4: checks of errata items 7, 8, 9 that need no return.  Stored scores, stored extracts, ledger factor statuses."""
import gzip, json, os, time
from collections import Counter
from pathlib import Path
root = Path("data/qsf/research")
doc = json.load(gzip.open(root/"scores_current_us.json.gz", "rt"))
dates, recs = doc["dates"], doc["records"]
# item 7: names with a row (member, bars, facts) but no SWING score, 2014-2019 - by ticker
miss = Counter(); rows = Counter()
for r in recs:
    if dates[r["i"]] < "2020":
        rows[r["t"]] += 1
        if r.get("SWING") is None: miss[r["t"]] += 1
print("item 7 - evaluation days 2014-2019:", len({r["i"] for r in recs if dates[r["i"]] < "2020"}))
print("  NVDA rows", rows["NVDA"], "without swing score", miss["NVDA"])
print("  tickers with >=5 unscored swing rows 2014-2019:", [(t, n, rows[t]) for t, n in miss.most_common(25) if n >= 5])
allmiss = sum(1 for r in recs if r.get("SWING") is None); print("  all rows", len(recs), "rows without swing score", allmiss, f"{allmiss/len(recs):.2%}")
# item 8: GICS financials against the live SIC rule (ledger: leverage NOT_APPLICABLE = scored as financial)
from terminal.qsf import validate
u = validate._universe(Path("."))
gics_fin = {t for t, s in u["sectors"].items() if s == "Financials"}
idx = [json.loads(l) for l in open("data/qsf/ledger/index.jsonl")]
last = [r for r in idx if r.get("type") != "VOID" and r.get("market") == "US"][-1]
sic_fin = set(); seen = set()
for line in gzip.open(Path("data/qsf/ledger")/last["file"], "rt"):
    s = json.loads(line)
    if s["strategy"] != "LONG_TERM": continue
    seen.add(s["ticker"])
    if any(f["factor"] == "leverage" and f["status"] == "NOT_APPLICABLE" for f in s["factors"]): sic_fin.add(s["ticker"])
only_gics = sorted((gics_fin & seen) - sic_fin); only_sic = sorted(sic_fin - gics_fin)
print("item 8 - session", last["session"], ": GICS Financials among scanned", len(gics_fin & seen), "| scored as financial by the live SIC rule", len(sic_fin))
print("  financial in the replay only (GICS yes, live no):", len(only_gics), only_gics)
print("  financial in live only (SIC yes, GICS no):", len(only_sic), only_sic)
# item 9: when the replay's statement extracts were made, and which debt keys they hold
folder = root/"facts_corrected"
files = sorted(folder.glob("*.json.gz"))
mt = sorted(os.path.getmtime(f) for f in files)
print("item 9 - facts_corrected files", len(files), "written between", time.strftime("%Y-%m-%d %H:%M", time.localtime(mt[0])), "and", time.strftime("%Y-%m-%d %H:%M", time.localtime(mt[-1])))
keys = Counter()
for f in files[:60]:
    keys.update(json.load(gzip.open(f, "rt"))["annual"].keys())
print("  keys in the first 60 extracts:", dict(keys))
from terminal.qsf import fundamentals
print("  keys the live reader extracts today:", sorted(list(fundamentals.US_FLOW) + list(fundamentals.US_INSTANT)))
