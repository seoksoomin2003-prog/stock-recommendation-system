"""Agent 03: score and band agreement between two consecutive recorded sessions (2026-11-20 under QSF-1.4.1, 2026-11-23 under QSF-1.5.2).
Only recorded scores, bands and the risk_reward factor value are read; no price, return or IC."""
import json, sys, gc
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
led = Ledger(REPO)
rows = led._live_rows()
def rank(x): return np.argsort(np.argsort(x)).astype(float)
def get(market, session):
    r = [x for x in rows if x["market"] == market and x["session"] == session][-1]
    out = {}
    for s in led._load(r):
        rr = next((f.get("normalized") for f in s.get("factors") or [] if f["factor"] == "risk_reward"), None)
        out[(s["ticker"], s["strategy"])] = (s.get("score"), s.get("band"), rr, s.get("actionability"))
    gc.collect()
    return out
res = {}
for m in ("US", "KR"):
    a, b = get(m, "2026-11-20"), get(m, "2026-11-23")
    for st in ("SWING", "LONG_TERM"):
        keys = [k for k in a if k[1] == st and k in b and a[k][0] is not None and b[k][0] is not None]
        x = np.array([a[k][0] for k in keys]); y = np.array([b[k][0] for k in keys])
        d = np.abs(y - x)
        rrd = np.array([abs((b[k][2] or 0) - (a[k][2] or 0)) for k in keys])
        x2 = x - np.array([6 * (a[k][2] or 0) for k in keys]) * 0  # placeholder
        res[f"{m}_{st}"] = {"n": len(keys), "rank_corr": round(float(np.corrcoef(rank(x), rank(y))[0, 1]), 3),
            "band_changed_share": round(float(np.mean([a[k][1] != b[k][1] for k in keys])), 3),
            "abs_change_median": round(float(np.median(d)), 2), "abs_change_p90": round(float(np.percentile(d, 90)), 2),
            "ge70_before_after_kept": [int((x >= 70).sum()), int((y >= 70).sum()), int(((x >= 70) & (y >= 70)).sum())],
            "risk_reward_moved_by_0.5_or_more": int((rrd >= 0.5).sum()) if st == "SWING" else None}
        print(m, st, res[f"{m}_{st}"])
    del a, b; gc.collect()
(Path(__file__).parent / "an_day_to_day.json").write_text(json.dumps(res, indent=1))
