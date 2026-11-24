"""Read-only: the 2026-11-23 KR ledger price (last bar from Yahoo, per its own label) against the KRX close of the same day
that arrived later.  A data-agreement check of one day's close, not a return."""
import json, sys
from pathlib import Path
import numpy as np
repo = Path.home() / "Developer/quant-stock-engine"
sys.path.insert(0, str(repo))
from terminal.qsf.ledger import Ledger
from terminal.qsf import kr_bars
led = Ledger(repo)
row = [r for r in led._live_rows() if r["market"] == "KR" and r["session"] == "2026-11-23"][0]
snaps = led._load(row)
pan = kr_bars.panel(repo)
print("panel last dates:", pan["dates"][-3:])
d = "2026-11-23"
n = pan["dates"].index(d) if d in pan["dates"] else None
print("KRX has 11-23:", n is not None)
diffs, missing, labels = [], 0, {}
seen = set()
for s in snaps:
    t = s["ticker"]
    if t in seen: continue
    seen.add(t)
    lab = (s.get("provenance") or {}).get("price")
    labels[lab] = labels.get(lab, 0) + 1
    j = pan["codes"].get(t)
    if j is None or n is None or s.get("price") is None:
        missing += 1; continue
    k = float(pan["data"][kr_bars.CLOSE, n, j])
    if not (k == k and k > 0):
        missing += 1; continue
    diffs.append((abs(s["price"] / k - 1), t, s["price"], k))
diffs.sort(reverse=True)
a = np.array([x[0] for x in diffs])
res = {"stocks": len(seen), "compared": len(diffs), "missing": missing, "labels": labels,
       "exact_equal(<1e-6)": int((a < 1e-6).sum()), "over_0.1pct": int((a > 0.001).sum()), "over_1pct": int((a > 0.01).sum()),
       "worst5": [(t, round(r * 100, 3)) for r, t, _, _ in diffs[:5]]}
print(json.dumps(res, ensure_ascii=False, indent=1))
json.dump(res, open(repo / "reports/maturity_assessment_2026_11_25/evidence/agent_05/kr_tail_vs_krx.json", "w"), ensure_ascii=False, indent=1)
