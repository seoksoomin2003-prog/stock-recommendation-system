"""STAT seat, random numbers only.  How long must ONE frozen formula be recorded before a real but modest rank effect is found?

Day-by-day IC of 20-session outcomes = true IC + noise that overlaps like 20-session returns do (terminal/qsf/calibrate.noise),
with the day scatter of reports/QSF_LIVE_FORWARD_POWER_2026_11_11.md (KR 0.138, US 0.197).  Only the t condition and "IC above 0
in both halves" are applied, so every figure is an upper limit for the full verdict.

Two designs:  (1) one reading at n sessions, bar = the value noise passes 1.25% of the time at that n.
(2) the registered reading at 240 sessions (1.25%), then, if it did not pass, readings of the SAME frozen record at 480, 720 and
960 sessions whose bars are set so that noise passes ANY of the three 1.25% of the time (a rule fixed in advance, not a re-read).
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from terminal.qsf import calibrate as c

H, LOOKS, SIMS = 20, (240, 480, 720, 960), 24000
rng = np.random.default_rng(20261125)
z = np.concatenate([c.noise(rng, 4000, LOOKS[-1], H, 1) for _ in range(SIMS // 4000)]) / np.sqrt(H)      # unit day scatter


def looks(x):
    """t at every look and whether both halves' means are above 0."""
    t = np.stack([c.t_many(x[:, :n], H) for n in LOOKS], 1)
    ok = np.stack([(x[:, :n // 2].mean(1) > 0) & (x[:, n // 2:n].mean(1) > 0) for n in LOOKS], 1)
    return t, ok


t0, _ = looks(z)
single = [float(np.quantile(t0[:, k], 1 - c.tail(2.24))) for k in range(len(LOOKS))]
# continuation bars: one common per-look chance for looks 2..4 such that noise passes any of them 1.25% of the time
lo, hi = 0.0005, 0.0125
for _ in range(30):
    mid = (lo + hi) / 2
    bars = [float(np.quantile(t0[:, k], 1 - mid)) for k in (1, 2, 3)]
    any_pass = np.mean((t0[:, 1] >= bars[0]) | (t0[:, 2] >= bars[1]) | (t0[:, 3] >= bars[2]))
    lo, hi = (mid, hi) if any_pass < c.tail(2.24) else (lo, mid)
cont = [float(np.quantile(t0[:, k], 1 - lo)) for k in (1, 2, 3)]
print("single-reading bars at", LOOKS, [round(b, 2) for b in single])
print("continuation bars at 480/720/960 (any of three = 1.25% under noise):", [round(b, 2) for b in cont], "per-look chance", round(lo * 100, 2), "%")
print("noise: first reading passes", f"{np.mean(t0[:, 0] >= single[0]):.2%}", "| any continuation passes", f"{np.mean((t0[:, 1] >= cont[0]) | (t0[:, 2] >= cont[1]) | (t0[:, 3] >= cont[2])):.2%}")
for market, sd in (("KR", 0.138), ("US", 0.197)):
    for ic in (0.03, 0.05, 0.08):
        t, ok = looks(ic + sd * z)
        one = [np.mean((t[:, k] >= single[k]) & ok[:, k]) for k in range(len(LOOKS))]
        first = (t[:, 0] >= single[0]) & ok[:, 0]
        cum = [np.mean(first)]
        got = first.copy()
        for k in (1, 2, 3):
            got |= (t[:, k] >= cont[k - 1]) & ok[:, k]
            cum.append(np.mean(got))
        print(f"{market} true IC {ic:.2f} | one reading at 240/480/720/960: " + " / ".join(f"{v:.0%}" for v in one) + " | registered 240 then continuations, found by 240/480/720/960: " + " / ".join(f"{v:.0%}" for v in cum))
