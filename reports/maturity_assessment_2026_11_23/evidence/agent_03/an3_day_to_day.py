"""Agent 03, analysis 3: score stability between two recorded sessions of one version (2026-11-19 -> 2026-11-20, QSF-1.4.1).
Scores only (rank correlation of scores, moves, band changes).  No return or price figure is computed."""
import json, sys
from pathlib import Path
import pandas as pd
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger
led = Ledger(REPO)
out = {}
for market in ("US", "KR"):
    rows = [r for r in led._live_rows() if r["market"] == market][-2:]
    days = []
    for r in rows:
        snaps = led._load(r)
        days.append((r["session"], r["model_version"], {(s["ticker"], s["strategy"]): (s.get("score"), s.get("band")) for s in snaps}))
        del snaps
    (d0, v0, a), (d1, v1, b) = days
    for strat in ("SWING", "LONG_TERM"):
        keys = [k for k in a if k[1] == strat and k in b and a[k][0] is not None and b[k][0] is not None]
        s0 = pd.Series({k[0]: a[k][0] for k in keys}); s1 = pd.Series({k[0]: b[k][0] for k in keys})
        mv = (s1 - s0).abs()
        buy0, buy1 = set(s0.index[s0 >= 70]), set(s1.index[s1 >= 70])
        out[f"{market}_{strat}"] = {"from": d0, "to": d1, "versions": [v0, v1], "n": len(keys), "rho": round(float(pd.concat([s0, s1], axis=1).corr(method="spearman").iloc[0, 1]), 4),
                                    "median_move": round(float(mv.median()), 2), "p90_move": round(float(mv.quantile(.9)), 2), "share_move_gt3": round(float((mv > 3).mean()), 3),
                                    "band_changed_share": round(sum(1 for k in keys if a[k][1] != b[k][1]) / len(keys), 3), "top20_kept": len(set(s0.nlargest(20).index) & set(s1.nlargest(20).index)),
                                    "ge70_before": len(buy0), "ge70_after": len(buy1), "ge70_kept": len(buy0 & buy1)}
print(json.dumps(out, indent=1))
(Path(__file__).parent / "an3_day_to_day.json").write_text(json.dumps(out, indent=1))
