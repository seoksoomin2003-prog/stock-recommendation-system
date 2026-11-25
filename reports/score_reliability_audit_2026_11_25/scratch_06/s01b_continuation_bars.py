"""AGENT 6 - script 1b.  A larger run (400,000 noise series each, seed 60612) for the three continuation bars, whose program
values (3.66 / 3.52 / 3.44) came out a little above script 1's.  Random numbers only."""
import math, json
import numpy as np
def nw_t(x, lag):
    n = x.shape[1]; e = x - x.mean(axis=1, keepdims=True)
    lrv = np.einsum("ij,ij->i", e, e) / n
    for k in range(1, lag + 1):
        lrv += 2.0 * (1.0 - k / (lag + 1.0)) * np.einsum("ij,ij->i", e[:, k:], e[:, :-k]) / n
    return x.mean(axis=1) / np.sqrt(lrv / n)
tail = 0.5 * math.erfc(2.64 / math.sqrt(2)); out = {}
for n, prog in ((240, None), (480, 3.66), (720, 3.52), (960, 3.44)):
    rng = np.random.default_rng([60612, n]); ts = []
    for _ in range(0, 400000, 4000):
        cs = np.cumsum(rng.standard_normal((4000, n + 20)), axis=1); ts.append(nw_t(cs[:, 20:] - cs[:, :-20], 20))
    t = np.concatenate(ts)
    if prog is None:
        q = float(np.quantile(t, 1 - 0.0125)); print(f"n={n}: 1.25% point {q:.3f} (program 3.33); chance of noise >= 3.33: {100*(t>=3.33).mean():.3f}%"); out[n] = q; continue
    q = float(np.quantile(t, 1 - tail)); p = float((t >= prog).mean()); se = math.sqrt(p * (1 - p) / len(t))
    out[n] = {"my_bar": q, "program_bar": prog, "p_at_program_bar": p}
    print(f"n={n}: point of chance {100*tail:.3f}%: {q:.3f} (program {prog}); chance of noise >= program bar: {100*p:.3f}% +- {100*se:.3f}%")
json.dump(out, open("s01b_out.json", "w"), indent=1)
