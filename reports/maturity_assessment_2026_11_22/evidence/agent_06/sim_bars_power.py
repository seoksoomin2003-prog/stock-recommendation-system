"""AGENT 6: independent check of calibrate.py bars and power of the four primary verdicts.
Random numbers only: no ledger, no price, no record is read."""
import math, sys, time
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

def my_nw_t(x, lag):
    """My own Newey-West t (Bartlett weights), row-wise. Written independently of calibrate.t_many."""
    n = x.shape[1]
    d = x - x.mean(axis=1, keepdims=True)
    g0 = np.einsum("ij,ij->i", d, d) / n
    lrv = g0.copy()
    for k in range(1, min(lag, n - 1) + 1):
        w = 1.0 - k / (lag + 1.0)
        lrv += 2.0 * w * np.einsum("ij,ij->i", d[:, k:], d[:, :-k]) / n
    return x.mean(axis=1) / np.sqrt(lrv / n), x.mean(axis=1), np.sqrt(lrv / n)

def overlapping(rng, rows, n, h, step=1):
    """n values, each the sum of h consecutive iid draws, one every `step` draws, scaled to unit variance."""
    raw = rng.standard_normal((rows, (n - 1) * step + h))
    out = np.empty((rows, n))
    for i in range(n):                      # deliberately a different construction from calibrate.noise (no cumsum)
        out[:, i] = raw[:, i * step:i * step + h].sum(axis=1)
    return out / math.sqrt(h)

def null_quantiles(n, h, step, lag, sims, seed, levels, block=4000):
    rng = np.random.default_rng(seed)
    ts = []
    for done in range(0, sims, block):
        t, _, _ = my_nw_t(overlapping(rng, min(block, sims - done), n, h, step), lag)
        ts.append(t)
    t = np.concatenate(ts)
    return t, {lv: float(np.quantile(t, 1 - lv)) for lv in levels}

def tail(z):
    return 0.5 * math.erfc(z / math.sqrt(2))

print("== 1. Independent reproduction of calibrate bars (my code, my seed) ==")
from terminal.qsf import calibrate
designs = [
    ("live swing  n=240 h=20 step=1 lag=20 nominal 2.24", 2.24, 240, 20, 1, 20),
    ("live long   n=756 h=63 step=1 lag=63 nominal 2.24", 2.24, 756, 63, 1, 63),
    ("fund period n=240 h=20 step=1 lag=20 nominal 3.0 ", 3.0, 240, 20, 1, 20),
    ("rank/turnover book n=240 h=1 lag=5 nominal 2.0   ", 2.0, 240, 1, 1, 5),
    ("committee paper n=240 h=1 lag=5 nominal 3.0      ", 3.0, 240, 1, 1, 5),
]
for name, nominal, n, h, step, lag in designs:
    t0 = time.time()
    sims = 40000
    t, q = null_quantiles(n, h, step, lag, sims, 777 + n + h, [tail(nominal)])
    mine = q[tail(nominal)]
    theirs = calibrate.bar(nominal, n, h, step, lag)
    p_nom = float((t >= nominal).mean())
    p_their = float((t >= theirs).mean())
    print(f"{name}: my quantile {mine:.2f} | calibrate.bar {theirs:.2f} | noise passes nominal {p_nom*100:.2f}% (table {tail(nominal)*100:.2f}%) | noise passes calibrate bar {p_their*100:.2f}%  [{time.time()-t0:.0f}s]")

print()
print("== 2. Power of the primary verdicts (condition A, t part + IC>=0.02 + both halves IC>0) ==")
print("dispersion: sd of per-date IC as recorded in reports/QSF_LIVE_FORWARD_POWER_2026_11_11.md")
cohorts = [("KR SWING", 0.138, 240, 20), ("US SWING", 0.197, 240, 20), ("KR LONG", 0.107, 756, 63), ("US LONG", 0.140, 756, 63)]
for name, sd, n, h in cohorts:
    rng = np.random.default_rng(4242 + n + int(sd * 1000))
    ms, ss, e, l = [], [], [], []
    for done in range(0, 20000, 4000):
        z = overlapping(rng, 4000, n, h)
        _, m, s = my_nw_t(z, h)
        ms.append(m); ss.append(s); e.append(z[:, :n // 2].mean(axis=1)); l.append(z[:, n // 2:].mean(axis=1))
    m, s, e, l = (np.concatenate(v) for v in (ms, ss, e, l))
    new_bar = calibrate.bar(2.24, n, h, 1, h)
    def power(mu, bar, full):
        ok = (mu / sd + m) / s >= bar
        if full:
            ok &= (mu + sd * m >= 0.02) & (mu + sd * e > 0) & (mu + sd * l > 0)
        return float(ok.mean())
    def need(p, bar, full):
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if power(mid, bar, full) < p: lo = mid
            else: hi = mid
        return hi
    row = [f"{name}: sd {sd}, n {n}, h {h}, new bar {new_bar}"]
    row.append("  old bar 2.24: IC for 50% {:.3f}, 80% {:.3f}".format(need(.5, 2.24, False), need(.8, 2.24, False)))
    row.append("  new bar     : IC for 50% {:.3f}, 80% {:.3f}  (t only)".format(need(.5, new_bar, False), need(.8, new_bar, False)))
    row.append("  new bar     : IC for 50% {:.3f}, 80% {:.3f}  (t + IC>=0.02 + both halves)".format(need(.5, new_bar, True), need(.8, new_bar, True)))
    row.append("  power at true IC 0.00/0.02/0.03/0.05/0.08/0.10/0.15 (new bar, t+IC+halves): " + ", ".join(f"{power(mu, new_bar, True)*100:.1f}%" for mu in (0, .02, .03, .05, .08, .10, .15)))
    row.append("  chance of t <= -2.0 when true IC is 0.03 (a 'looks negative' misread): {:.1f}%".format(float((((0.03 / sd + m) / s) <= -2.0).mean()) * 100))
    print("\n".join(row))
