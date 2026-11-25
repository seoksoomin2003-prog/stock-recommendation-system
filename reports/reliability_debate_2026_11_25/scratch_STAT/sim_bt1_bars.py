"""STAT seat, random numbers only.  What the t values of BT-1 mean on BT-1's own sample designs.

Uses terminal/qsf/calibrate.py (noise and the same Newey-West arithmetic).  Reads no price, no return, no record.
The observed t values typed below are copied from reports/qsf/QSF_BACKTEST_CURRENT_{US,KR}.json (rank tables).
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from terminal.qsf import calibrate as c

SIMS = 40000
# (label, dates, horizon in sessions, step between dates, lag used by validate.summarize, observed t)
DESIGNS = [("US swing 20", 152, 20, 21, 1, 0.27), ("US long 63", 151, 63, 21, 3, 1.38), ("US long 126", 148, 126, 21, 6, 2.14), ("US long 252", 142, 252, 21, 12, 1.98),
           ("KR swing 5", 90, 5, 21, 1, 4.02), ("KR swing 20", 89, 20, 21, 1, 5.13), ("KR long 63", 87, 63, 21, 3, 2.92), ("KR long 126", 84, 126, 21, 6, 2.31),
           ("KR long 252", 78, 252, 21, 12, 1.99)]
print("design | noise bar for 1.25% one-sided (table says 2.24) | chance noise reaches the observed t | chance noise passes 2.24")
for label, n, h, step, lag, t_obs in DESIGNS:
    rng = np.random.default_rng([7, n, h, step, lag])
    got = np.concatenate([c.t_many(c.noise(rng, 4000, n, h, step), lag) for _ in range(SIMS // 4000)])
    got = got[np.isfinite(got)]
    print(f"{label:12s} n={n:3d} h={h:3d} lag={lag:2d} | bar {np.quantile(got, 1 - c.tail(2.24)):.2f} | P(t>={t_obs:.2f}) {np.mean(got >= t_obs) * 100:6.2f}% | P(t>=2.24) {np.mean(got >= 2.24) * 100:5.2f}%")

# How often does a family of K separate statistics show at least one |t| >= 2.2 by chance (two-sided 2.78% each)?
p = 2 * c.tail(2.2)
print("\nfamily of K independent statistics, chance of at least one |t|>=2.2:", {k: round(1 - (1 - p) ** k, 3) for k in (1, 4, 8, 12, 24)})

# The early readings and the primary verdict bars as the code computes them (for the record)
print("\nprimary swing bar (240 daily values, h 20, lag 20):", c.bar(2.24, 240, 20, 1, 20), "| long (756, 63, 63):", c.bar(2.24, 756, 63, 1, 63))
print("early bars: 60 ->", c.bar(2.75, 60, 5, 1, 5), " 120 ->", c.bar(2.75, 120, 5, 1, 5))
