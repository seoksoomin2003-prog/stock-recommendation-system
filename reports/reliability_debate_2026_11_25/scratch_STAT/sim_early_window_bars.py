"""STAT seat, random numbers only: the noise bar (1.25% one-sided) for the designs of earlier Korean readings, and the chance
noise reaches the t each one recorded.  The t values are copied from reports/QSF_KR_LONG_EARLY_RESULTS.md and
reports/QSF_KR_UNIVERSE_TEST_RESULTS.md.  Run from the repository root: .venv/bin/python <this file>.  Output: sim_early_window_bars_out.txt
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from terminal.qsf import calibrate as c

for label, n, h, lag, t in (("KR long early 252d (2016-18)", 23, 252, 12, 2.05), ("KR long early 63d", 32, 63, 3, 3.02), ("KR cap universe long 63d", 86, 63, 3, 3.40),
                            ("KR cap universe long 252d", 77, 252, 12, 2.46), ("KR cap universe risk domain swing 20d", 88, 20, 1, 4.5)):
    rng = np.random.default_rng([11, n, h, lag])
    got = np.concatenate([c.t_many(c.noise(rng, 4000, n, h, 21), lag) for _ in range(10)])
    got = got[np.isfinite(got)]
    print(f"{label}: n={n} bar {np.quantile(got, 1 - c.tail(2.24)):.2f} | chance noise reaches t {t}: {np.mean(got >= t) * 100:.2f}%")
