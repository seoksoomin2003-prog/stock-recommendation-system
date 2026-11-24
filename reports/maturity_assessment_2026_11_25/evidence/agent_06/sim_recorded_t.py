"""Agent 06 (2026-11-25).  Random numbers only.  The historical Korean tests read the nominal bar 2.24 on overlapping samples
(evaluation dates ~21 sessions apart; a 252-session outcome overlaps 12 neighbours, Newey-West lag 12; a 63-session outcome
overlaps 3).  How often does pure noise reach the recorded t values?  Uses the program's own calibrate.noise / t_many."""
import sys
from pathlib import Path
import numpy as np
repo = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo))
from terminal.qsf import calibrate
rng = np.random.default_rng(7)
def dist(n, h, lag, sims=40000):
    return np.concatenate([calibrate.t_many(calibrate.noise(rng, 4000, n, h, 1), lag) for _ in range(sims // 4000)])
for label, n, h, lag, ts in (("KR long 252d, 77 dates (lag 12)", 77, 12, 12, (2.46, 8.20)),
                             ("KR long 63d, 86 dates (lag 3)", 86, 3, 3, (3.40, 7.18)),
                             ("KR swing 20d, 88 dates (lag 1)", 88, 1, 1, (0.47, 1.90)),
                             ("US long 252d, 142 dates (lag 12)", 142, 12, 12, (1.30, 1.83, 2.00))):
    d = dist(n, h, lag)
    d = d[np.isfinite(d)]
    print(f"{label}: noise reaches 2.24 in {np.mean(d >= 2.24):.2%}; 1.25% bar = {np.quantile(d, 0.9875):.2f}; " + ", ".join(f"P(t>={t})={np.mean(d >= t):.3%}" for t in ts))
