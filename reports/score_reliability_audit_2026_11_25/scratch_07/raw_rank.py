"""AGENT 7: (a) continued.  The stored normalized value is already clipped at its anchors (KR: 46% of stocks at 0 on atr_risk),
and a rank of clipped values cannot tell the clipped stocks apart.  For the price-risk factors every input is in the ledger's
raw record, so their percentile can be taken on the inputs themselves.  No return is read."""
import json, sys
import numpy as np
sys.path.insert(0, "reports/score_reliability_audit_2026_11_25/scratch_07")
from common import *

RAW = {"atr_risk": (("atr_pct", -1), ("hist_vol", -1)), "drawdown_gap": (("max_drawdown_252", 1), ("max_gap_60", -1)), "liquidity": (("adv_value", 1),),
       "downside_drawdown": (("downside_vol", -1), ("max_drawdown_252", 1))}
out = {}
for m, s in PROFILES:
    acc = {"rho_live_A": [], "rho_live_Araw": [], "rho_A_Araw": [], "top_kept_live_Araw": [], "tied_share_before": [], "tied_share_after": []}
    for d in sessions(m):
        fr = frame(m, d, s)
        X, w, names, tick = fr["X"], fr["w"], fr["names"], fr["tick"]
        rows = fr["slot"]["rows"]
        P = np.column_stack([pct_col(X[:, j]) for j in range(X.shape[1])])
        Q = P.copy()
        tb, ta = [], []
        for j, f in enumerate(names):
            if f not in RAW:
                continue
            parts = []
            for key, sign in RAW[f]:
                v = np.array([(rows[t]["fac"][f]["raw"].get(key) if rows[t]["fac"].get(f) and rows[t]["fac"][f]["st"] in OK else None) or np.nan for t in tick], dtype=float)
                parts.append(pct_col(sign * v))
            with np.errstate(invalid="ignore"):
                col = np.nanmean(np.stack(parts), axis=0)
            col[~np.isfinite(X[:, j])] = np.nan
            Q[:, j] = pct_col(col)
            x = X[:, j][np.isfinite(X[:, j])]
            tb.append(1 - len(np.unique(np.round(x, 9))) / len(x)); q = Q[:, j][np.isfinite(Q[:, j])]; ta.append(1 - len(np.unique(np.round(q, 9))) / len(q))
        live, A, Ar = wmean(X, w), wmean(P, w), wmean(Q, w)
        acc["rho_live_A"].append(spearman(live, A)); acc["rho_live_Araw"].append(spearman(live, Ar)); acc["rho_A_Araw"].append(spearman(A, Ar))
        acc["top_kept_live_Araw"].append(len(top_set(live, tick) & top_set(Ar, tick)) / (len(tick) // 5))
        acc["tied_share_before"].append(float(np.mean(tb))); acc["tied_share_after"].append(float(np.mean(ta)))
    out[f"{m}_{s}"] = {k: float(np.mean(v)) for k, v in acc.items()}
    print(m, s, {k: round(v, 3) for k, v in out[f"{m}_{s}"].items()})
json.dump(out, open(HERE / "raw_rank.json", "w"), indent=1)
