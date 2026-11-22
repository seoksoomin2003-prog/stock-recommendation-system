"""Agent 06, 2026-11-23.  RANDOM NUMBERS ONLY: no ledger, no forward record, no price is read.

A. The bars of terminal/qsf/calibrate.py against an independent noise generator (direct window sums, another seed).
B. The pooled reference of live_forward._pooled.
C. plain_bar at a dozen samples, and what a verdict that is re-read every day (top_picks) does to it.
D. kr_method block design.
E. Robustness of the main bar to noise that is not the calibration's own (fat tails, volatility clusters, persistent daily IC).
"""
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf import calibrate  # noqa: E402  (pure numpy; reads nothing)

RNG = np.random.default_rng(606)
SIMS = 20000


def nw_t(x: np.ndarray, lag: int) -> np.ndarray:
    """Newey-West t per row, written separately from calibrate.t_many (Bartlett weights, variance over n)."""
    n = x.shape[1]
    e = x - x.mean(axis=1, keepdims=True)
    g0 = np.einsum("ij,ij->i", e, e) / n
    var = g0.copy()
    for k in range(1, min(lag, n - 1) + 1):
        w = 1.0 - k / (lag + 1.0)
        var += 2.0 * w * np.einsum("ij,ij->i", e[:, k:], e[:, :-k]) / n
    out = np.full(x.shape[0], np.nan)
    ok = var > 0
    out[ok] = x.mean(axis=1)[ok] / np.sqrt(var[ok] / n)
    return out


def windows(raw: np.ndarray, n: int, h: int, step: int) -> np.ndarray:
    """n values per row: sum of h consecutive draws, one every `step` draws (direct sums, no cumulative sum)."""
    out = np.empty((raw.shape[0], n))
    for j in range(n):
        out[:, j] = raw[:, j * step:j * step + h].sum(axis=1)
    return out


def gauss(rows: int, length: int) -> np.ndarray:
    return RNG.standard_normal((rows, length))


def rate(n, h, step, lag, bar, draw=gauss, sims=SIMS, block=2500):
    got = []
    for done in range(0, sims, block):
        raw = draw(min(block, sims - done), (n - 1) * step + h)
        got.append(nw_t(windows(raw, n, h, step), lag))
    t = np.concatenate(got)
    t = t[np.isfinite(t)]
    return float(np.mean(t >= bar)), t


print("A. calibrated bars: chance of noise passing (independent generator, %d series each)" % SIMS)
print("design                                   nominal  table%%  bar    pass@nominal%%  pass@bar%%  own_quantile")
DESIGNS = [
    ("live swing   n240 h20 step1 lag20", 2.24, 240, 20, 1, 20),
    ("live long    n756 h63 step1 lag63", 2.24, 756, 63, 1, 63),
    ("fund period  n240 h20 step1 lag20", 3.0, 240, 20, 1, 20),
    ("split/univ.  n240 h20 step1 lag20", 2.0, 240, 20, 1, 20),
    ("committee    n240 h1  step1 lag5 ", 3.0, 240, 1, 1, 5),
    ("rank/turnover n240 h1 step1 lag20", 2.0, 240, 1, 1, 20),
    ("kr_forward   n48  h20 step5 lag4 ", 2.24, 48, 20, 5, 4),
    ("challenger L n151 h63 step5 lag13", 2.24, 151, 63, 5, 13),
    ("kr_method    n12  h1  step1 lag1 ", 2.0, 12, 1, 1, 1),
    ("kr_method    n24  h1  step1 lag1 ", 2.0, 24, 1, 1, 1),
]
KEEP = {}
for name, nominal, n, h, step, lag in DESIGNS:
    bar = calibrate.bar(nominal, n, h, step, lag)
    sims = SIMS if n < 500 else 8000
    p_nom, t = rate(n, h, step, lag, nominal, sims=sims)
    p_bar = float(np.mean(t >= bar))
    own = float(np.quantile(t, 1 - calibrate.tail(nominal)))
    KEEP[name] = t
    print(f"{name:40s} {nominal:5.2f}  {calibrate.tail(nominal) * 100:6.3f}  {bar:5.2f}  {p_nom * 100:10.2f}  {p_bar * 100:9.3f}  {own:8.2f}")

print()
print("B. pooled reference (t_US + t_KR)/sqrt(2) against max of the two bars (live swing design)")
t = KEEP["live swing   n240 h20 step1 lag20"]
half = len(t) // 2
z = (t[:half] + t[half:2 * half]) / math.sqrt(2)
bar = calibrate.bar(2.24, 240, 20, 1, 20)
print(f"  pass at table 2.24: {np.mean(z >= 2.24) * 100:.2f}%   pass at bar {bar}: {np.mean(z >= bar) * 100:.2f}%   (table says 1.25%)   sd of one t: {t.std():.2f}, of pooled: {z.std():.2f}")
t = KEEP["live long    n756 h63 step1 lag63"]
half = len(t) // 2
z = (t[:half] + t[half:2 * half]) / math.sqrt(2)
bar = calibrate.bar(2.24, 756, 63, 1, 63)
print(f"  long design: pass at bar {bar}: {np.mean(z >= bar) * 100:.2f}%")

print()
print("C. plain t of a few separate samples (kr_swing_challenger, kr_swing_prior, top_picks)")
for n in (12, 13, 15, 20):
    x = RNG.standard_normal((200000, n))
    tt = x.mean(axis=1) / (x.std(axis=1, ddof=1) / math.sqrt(n))
    pb = calibrate.plain_bar(2.0, n)
    print(f"  n={n:2d}: plain_bar(2.0)={pb:.2f}  pass@2.0 {np.mean(tt >= 2.0) * 100:.2f}%  pass@bar {np.mean(tt >= pb) * 100:.2f}%  (table 2.28%)")

# top_picks: the wording is recomputed on every look once 12 separate samples exist; daily IC of h=20 returns, spaced every 20th
sims, h = 6000, 20
last = 240 + 250                                 # one more year of daily looks after the first possible verdict
raw = RNG.standard_normal((sims, last + h))
ic = windows(raw, last, h, 1)
ever = np.zeros(sims, dtype=bool)
first = None
for days in range(240, last + 1):
    sp = ic[:, :days:h]
    n = sp.shape[1]
    tt = sp.mean(axis=1) / (sp.std(axis=1, ddof=1) / math.sqrt(n))
    good = (ic[:, :days].mean(axis=1) > 0) & (tt >= calibrate.plain_bar(2.0, n))
    if first is None:
        first = good.mean()
    ever |= good
print(f"  top_picks wording 'evidence' under noise: on the first day it can appear {first * 100:.2f}%, at least once in the following 250 daily looks {ever.mean() * 100:.2f}%")

print()
print("E. main bar under noise that is not the calibration's own (live swing design, bar %.2f)" % calibrate.bar(2.24, 240, 20, 1, 20))


def t_fat(rows, length):
    return RNG.standard_t(3, size=(rows, length))


def clustered(rows, length):
    """Volatility that comes in runs: log-volatility AR(1) with half-life of about a month."""
    lv = np.zeros((rows, length))
    e = RNG.standard_normal((rows, length)) * 0.25
    for j in range(1, length):
        lv[:, j] = 0.97 * lv[:, j - 1] + e[:, j]
    return RNG.standard_normal((rows, length)) * np.exp(lv)


def persistent(rows, length, rho=0.15):
    """The one-day ingredient of the IC itself carries over from day to day (rho): slow scores on trending factor returns."""
    x = RNG.standard_normal((rows, length))
    for j in range(1, length):
        x[:, j] += rho * x[:, j - 1]
    return x


bar = calibrate.bar(2.24, 240, 20, 1, 20)
for label, draw in (("fat tails (t, 3 d.o.f.)", t_fat), ("volatility clusters", clustered), ("one-day part AR(1) 0.15", persistent),
                    ("one-day part AR(1) 0.30", lambda r, l: persistent(r, l, 0.30))):
    p, t = rate(240, 20, 1, 20, bar, draw=draw, sims=10000)
    print(f"  {label:28s} pass@bar {p * 100:.2f}%  (target 1.25%)")
