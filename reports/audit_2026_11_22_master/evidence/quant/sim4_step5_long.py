"""SIM 4: (a) the 'step 5, 252-session return, lag ceil(252/5)=51' design of the Korean one-shot studies (186 dates = about 3.7 independent years);
(b) the live forward verdict when only half the days can be computed (live_forward.py:176 accepts 120 of 240).
Null: moving sum of i.i.d. N(0,1) per-session shocks (a slow score against overlapping returns).  100,000 simulations (a), 20,000 (b)."""
import json, math
import numpy as np
from simlib import nw_t, selfcheck
selfcheck()
rng = np.random.default_rng(20261125)
def moving_sum(n, h, step, sims):
    L = n * step + h + 1; out = np.empty((sims, n)); B = 2000
    for b in range(0, sims, B):
        c = np.concatenate([np.zeros((B, 1)), rng.standard_normal((B, L)).cumsum(axis=1)], axis=1)
        idx = np.arange(n) * step
        out[b:b + B] = c[:, idx + h + 1] - c[:, idx + 1]
    return out
P = lambda x: round(float(np.mean(x)) * 100, 3)
x = moving_sum(186, 252, 5, 100000)
for lag in (51, 12):
    t = nw_t(x, lag)
    q = np.quantile(t, [0.975, 0.9875, 0.995, 0.999])
    print(json.dumps({"design": "n186 h252 step5", "lag": lag, "t_sd": round(float(t.std()), 2), "P(t>=2.24)": P(t >= 2.24), "q97.5": round(q[0], 2), "q98.75": round(q[1], 2), "q99.5": round(q[2], 2), "q99.9": round(q[3], 2),
                      **{f"P(t>={v})": P(t >= v) for v in (6.78, 7.33, 10.14, 11.95, 13.69, 14.61)}}))
x = moving_sum(232, 20, 5, 100000); t = nw_t(x, 4); q = np.quantile(t, [0.9875, 0.999])
print(json.dumps({"design": "n232 h20 step5 lag4", "P(t>=2.24)": P(t >= 2.24), "q98.75": round(q[0], 2), "q99.9": round(q[1], 2), **{f"P(t>={v})": P(t >= v) for v in (4.71, 5.32, 7.81, 10.67, 13.43)}}))
for n in (240, 180, 120):
    t = nw_t(moving_sum(n, 20, 1, 20000), 20)
    print(json.dumps({"design": f"live forward swing with {n} usable days, h20 lag20", "P(t>=2.24)": P(t >= 2.24), "P(t>=2.0)": P(t >= 2.0), "P(t>=3.0)": P(t >= 3.0)}))
