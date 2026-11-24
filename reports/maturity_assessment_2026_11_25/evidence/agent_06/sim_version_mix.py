"""Agent 06 (2026-11-25).  Random numbers only: what formula changes inside the 240-session swing sample do to the primary live
verdict.  No price, no return, no record is read.  The IC spread (sd of one 20-session IC) is taken from statistics already
recorded in result files: US swing ic -0.0144 at t -0.945 over 153 separate dates -> sd ~0.19; KR swing (live replay) ic 0.028 at
t 1.90 over 88 dates -> sd ~0.14.  Conditions modelled: mean IC >= 0.02, Newey-West t >= the program's calibrated bar, IC > 0 in
both halves.  The spread and buy-band conditions are left out, so the pass rates below are UPPER bounds."""
import math, sys
from pathlib import Path
import numpy as np
repo = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo))
from terminal.qsf import calibrate

N, H = 240, 20
BAR = calibrate.bar(2.24, N, H, 1, H)
print("program's bar for the live swing design:", BAR)
rng = np.random.default_rng(20261125)
SIMS = 20000

def run(mu_of_day, sd, label):
    hits, done = 0, 0
    while done < SIMS:
        k = min(4000, SIMS - done)
        z = calibrate.noise(rng, k, N, H, 1) / math.sqrt(H)
        mu = np.array([mu_of_day(i) for i in range(N)]) if not callable(getattr(mu_of_day, "draw", None)) else mu_of_day.draw(k)
        x = mu + sd * z
        t = calibrate.t_many(x, H)
        m = x.mean(axis=1)
        e, l = x[:, : N // 2].mean(axis=1), x[:, N // 2:].mean(axis=1)
        hits += int(((t >= BAR) & (m >= 0.02) & (e > 0) & (l > 0)).sum())
        done += k
    print(f"  {label:<62} pass {hits / SIMS:6.1%}")

class Frequent:
    """A new formula every `every` sessions, each with a true IC drawn from `levels`."""
    def __init__(self, every, levels): self.every, self.levels = every, levels
    def draw(self, k):
        blocks = math.ceil(N / self.every)
        lv = rng.choice(self.levels, size=(k, blocks))
        return np.repeat(lv, self.every, axis=1)[:, :N]

for name, sd in (("KR swing (sd 0.14)", 0.14), ("US swing (sd 0.19)", 0.19)):
    print(name)
    run(lambda i: 0.0, sd, "noise only (target 1.25%)")
    for ic in (0.05, 0.10):
        run(lambda i, ic=ic: ic, sd, f"one formula, true IC {ic:.2f} all year")
    run(lambda i: 0.10 if i < 120 else 0.0, sd, "IC 0.10 first half, formula changed to IC 0 at session 120")
    run(lambda i: 0.0 if i < 120 else 0.10, sd, "IC 0 first half, formula changed to IC 0.10 at session 120")
    run(lambda i: 0.10 if i < 60 else 0.0, sd, "IC 0.10 for 60 sessions, then a formula with IC 0")
    run(Frequent(2, [0.0, 0.05, 0.10]), sd, "new formula every 2 sessions, IC drawn from 0/0.05/0.10")
    run(Frequent(21, [0.0, 0.05, 0.10]), sd, "new formula every 21 sessions, IC drawn from 0/0.05/0.10")
    run(lambda i: 0.05, sd, "  (same average IC 0.05 under one formula, for comparison)")

print("Chance that 260 sessions pass with no formula change (changes as a Poisson process):")
for every in (14 / 7, 21, 63, 126, 252):
    print(f"  one change per {every:6.1f} sessions: {math.exp(-260 / every):.2e}")
