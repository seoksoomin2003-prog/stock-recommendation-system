"""AGENT 7: is my rebuilt bundle score (D1) the registered challenger's?  Reads the challenger records' scores only (no outcome
exists in those files) for one session per market and compares."""
import gzip, json, sys
import numpy as np
sys.path.insert(0, "reports/score_reliability_audit_2026_11_25/scratch_07")
from common import *
from terminal.qsf import us_challenger as uc, kr_challenger as kc, research_ensemble as en

for m, folder, day in (("US", "research_data/us_challenger", "2026-11-24"), ("KR", "research_data/kr_challenger", "2026-11-24")):
    doc = json.load(gzip.open(f"{folder}/{day}.json.gz", "rt"))
    for s in ("SWING", "LONG_TERM"):
        rec = doc["strategies"][s] if m == "US" else [r for r in doc["rows"] if r["strategy"] == s]
        stored = {r["ticker"]: r["score"] for r in rec if r["score"] is not None}
        live = {r["ticker"]: r["live"] for r in rec}
        fr = frame(m, day, s, judged_only=False)
        P = {n: pct_col(fr["X"][:, j]) for j, n in enumerate(fr["names"])}
        bundles = (uc if m == "US" else kc).BUNDLES[s]
        mine = dict(zip(fr["tick"], en.combine(P, bundles)))
        common = [t for t in fr["tick"] if t in stored and np.isfinite(mine[t])]
        a, b = np.array([mine[t] for t in common]), np.array([stored[t] for t in common])
        l = np.array([live[t] for t in common])
        print(m, s, day, "stocks", len(common), "max |mine - recorded|", round(float(np.abs(a - b).max()), 6), "rank corr recorded challenger vs live", round(spearman(b, l), 3),
              "recorded >=70:", int((b >= 70).sum()), "live >=70:", int((l >= 70).sum()))
