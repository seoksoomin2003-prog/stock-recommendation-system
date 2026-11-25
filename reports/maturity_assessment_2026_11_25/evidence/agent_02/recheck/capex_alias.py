"""Agent 02 recheck: in the stored US annual copies (annual5:*), which capex tag the newest year was read from, and capex as a
share of operating cash flow for the fallback tags (a partial 'other' line would read small).  No provider, no returns."""
import sys, json, glob
from collections import Counter
from pathlib import Path
repo = Path.home() / "Developer" / "quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf import fundamentals
prim = {"PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "PaymentsForCapitalImprovements"}
alias, fall, none, stored = Counter(), [], [], []
for p in glob.glob(str(repo / "data/qsf/cache/annual5_*.json")):
    d = json.load(open(p))
    data = d.get("data") or {}
    stored.append(d.get("stored_at") or d.get("time") or "")
    cap, ocf = data.get("capex") or [], data.get("ocf") or []
    if not ocf:
        continue
    last_end = max(r["end"] for r in ocf)
    c = [r for r in cap if r["end"] == last_end]
    o = [r for r in ocf if r["end"] == last_end][-1]["val"]
    name = Path(p).name.split("_")[1]
    if not c:
        none.append(name); continue
    a = c[-1].get("alias", "?"); alias[a] += 1
    if a not in prim:
        fall.append((name, a[:45], round(c[-1]["val"] / o, 3) if o else None))
print("files", len(stored), "newest stored stamps sample", __import__("datetime").datetime.fromtimestamp(min(stored)).isoformat(), __import__("datetime").datetime.fromtimestamp(max(stored)).isoformat())
print("newest-year capex alias:", dict(alias))
print("no capex in newest year (with OCF):", len(none))
print("fallback-read companies (CIK, tag, capex/OCF):")
for x in sorted(fall, key=lambda x: (x[1], x[2] or 0)):
    print("  ", x)
