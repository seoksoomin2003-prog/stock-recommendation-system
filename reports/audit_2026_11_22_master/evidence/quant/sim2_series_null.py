"""SIM 2: false-positive rates of the repo's Newey-West t for every (n, overlap, lag, threshold) design the project uses.

Fast series-level design (20,000 simulations per row, seeded):
  * A statistic of an h-session forward return, observed every `step` sessions, with a score that does not change (the worst case of a
    slow score) is a moving sum of i.i.d. per-session shocks:  x_t = sum_{j=1..h} e_{t*step + j},  e ~ N(0,1) i.i.d. (or Student t3).
    This is exactly the autocorrelation the IC / spread series of SIM 1 'fixed' has (checked there on full cross-sections).
  * For daily non-overlapping series (paper-book differences, committee excess returns) x_t = e_t (h = 1).
  * One-sided rate = P(t >= thr), two-sided = P(|t| >= thr) under the null of zero mean.
Rows = the designs found in the code (file:line in the label).
"""
import json, math, sys
import numpy as np
from simlib import nw_t, plain_t, selfcheck

selfcheck()
SIMS = 20000
rng = np.random.default_rng(20261123)

def moving_sum(n, h, step, dist="normal"):
    L = n * step + h + 1
    out = np.empty((SIMS, n))
    B = 2000
    for b in range(0, SIMS, B):
        e = rng.standard_normal((B, L)) if dist == "normal" else rng.standard_t(3, size=(B, L))
        c = np.concatenate([np.zeros((B, 1)), e.cumsum(axis=1)], axis=1)
        idx = np.arange(n) * step
        out[b:b + B] = c[:, idx + h + 1] - c[:, idx + 1]
    return out

def row(label, n, h, step, lag, thrs, dist="normal", kernel="bartlett"):
    x = moving_sum(n, h, step, dist)
    t = nw_t(x, lag, kernel)
    bad = float(np.isnan(t).mean()) * 100
    t = t[np.isfinite(t)]
    res = {"label": label, "n": n, "h": h, "step": step, "lag": lag, "dist": dist, "kernel": kernel, "nonpositive_var_pct": round(bad, 2),
           "t_sd": round(float(t.std()), 3)}
    for th in thrs:
        res[f"one_sided_{th}"] = round(float((t >= th).mean()) * 100, 2)
        res[f"two_sided_{th}"] = round(float((np.abs(t) >= th).mean()) * 100, 2)
    print(json.dumps(res)); sys.stdout.flush()
    return res

T = (2.0, 2.24, 3.0)
print("# A. daily overlapping 20-session statistics, n=240 (live_forward swing, fund_period, score_split, kr_*_universe, kr_avoid_marks, kr_swing_*, us_challenger?)")
for lag in (0, 20, 40, 60):
    row("n240 h20 daily", 240, 20, 1, lag, T)
row("n240 h20 daily Hansen-Hodrick", 240, 20, 1, 19, T, kernel="uniform")
row("n240 h20 daily fat tails t3", 240, 20, 1, 20, T, dist="t3")
x = moving_sum(240, 20, 1)
tt = plain_t(x[:, ::20])
print(json.dumps({"label": "n240 h20: non-overlapping every 20th (n=12), plain t", **{f"one_sided_{th}": round(float((tt >= th).mean()) * 100, 2) for th in T}}))
print("# B. daily overlapping 63-session statistics, n=756 (live_forward long: live_forward.py:23,111; challengers long)")
for lag in (63, 126):
    row("n756 h63 daily", 756, 63, 1, lag, T)
row("n756 h63 daily Hansen-Hodrick", 756, 63, 1, 62, T, kernel="uniform")
print("# C. monthly-step historical designs (validate.py:247 lag = ceil(h/21))")
for n in (142, 77, 23, 22):
    row(f"h252 step21 lag12 n{n}", n, 252, 21, 12, T)
    row(f"h252 step21 lag24 n{n}", n, 252, 21, 24, T)
row("h252 step21 n142 Hansen-Hodrick lag 11", 142, 252, 21, 11, T, kernel="uniform")
row("h252 step21 n77 Hansen-Hodrick lag 11", 77, 252, 21, 11, T, kernel="uniform")
for n in (153, 88):
    row(f"h20 step21 lag1 n{n} (no overlap)", n, 20, 21, 1, T)
row("h126 step21 lag6 n148", 148, 126, 21, 6, T)
row("h63 step21 lag3 n151", 151, 63, 21, 3, T)
print("# D. research_swing design: step 5, h 10/20, lag_of(h) (research_swing.py:353) -- lag printed by the caller script")
print("# E. daily NON-overlapping series, n=240")
for lag, thr in ((20, (2.0, 2.24, 3.0)), (5, (2.0, 2.64, 3.0)), (0, (2.0, 3.0))):
    row("iid daily n240", 240, 1, 1, lag, thr)
    row("iid daily n240 t3 tails", 240, 1, 1, lag, thr, dist="t3")
print("# F. other thresholds in the code: market_state min_t 2.39 lag 20 (daily h20), kr_method select_t 2.45 lag 1, swing BONFERRONI 2.86")
row("n240 h20 daily lag20 thr 2.39/2.45/2.86", 240, 20, 1, 20, (2.39, 2.45, 2.86))
row("n4000 h20 daily lag20 (market_state, long history)", 4000, 20, 1, 20, (2.0, 2.39, 3.0))
