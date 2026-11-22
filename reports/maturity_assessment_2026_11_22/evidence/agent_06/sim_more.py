"""AGENT 6: further checks on random numbers only (no ledger, no price, no record)."""
import math, sys
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf import calibrate

def nw(x, lag):
    n = x.shape[1]; d = x - x.mean(axis=1, keepdims=True)
    v = np.einsum("ij,ij->i", d, d) / n
    for k in range(1, min(lag, n - 1) + 1):
        v += 2 * (1 - k / (lag + 1.0)) * np.einsum("ij,ij->i", d[:, k:], d[:, :-k]) / n
    return x.mean(axis=1) / np.sqrt(v / n)

def series(rng, rows, n, h, step=1):
    raw = rng.standard_normal((rows, (n - 1) * step + h))
    c = np.cumsum(raw, axis=1); c = np.concatenate([np.zeros((rows, 1)), c], axis=1)
    idx = np.arange(n) * step
    return (c[:, idx + h] - c[:, idx]) / math.sqrt(h)

def null_t(n, h, step, lag, sims, seed):
    rng = np.random.default_rng(seed); out = []
    for _ in range(sims // 4000):
        out.append(nw(series(rng, 4000, n, h, step), lag))
    return np.concatenate(out)

print("1. pooled reference of live_forward._pooled: (t_US + t_KR)/sqrt(2) >= 2.24, two independent null markets")
for name, n, h in (("swing", 240, 20), ("long", 756, 63)):
    a, b = null_t(n, h, 1, h, 40000, 11 + n), null_t(n, h, 1, h, 40000, 12 + n)
    z = (a + b) / math.sqrt(2)
    print(f"  {name}: noise passes 2.24 in {float((z >= 2.24).mean())*100:.2f}% (table says 1.25%); sd of null t {a.std():.2f}")

print("2. family of the four primary verdicts, t condition only, independent nulls: P(any passes) = 1-(1-p)^4")
for name, n, h in (("swing", 240, 20), ("long", 756, 63)):
    t = null_t(n, h, 1, h, 40000, 99 + n)
    p = float((t >= calibrate.bar(2.24, n, h, 1, h)).mean())
    print(f"  {name}: single pass {p*100:.2f}%")

print("3. bars of other designs as the code calls them")
for label, args in (("rank/turnover book: bar(2.0, 240, 1, 1, 20)", (2.0, 240, 1, 1, 20)),
                    ("committee paper: bar(3.0, 240, 1, 1, 5)", (3.0, 240, 1, 1, 5)),
                    ("fund period / score split swing: bar(3.0 / 2.0, 240, 20, 1, 20)", (3.0, 240, 20, 1, 20)),
                    ("score split: bar(2.0, 240, 20, 1, 20)", (2.0, 240, 20, 1, 20)),
                    ("kr_forward / us_challenger swing: bar(2.24, 48, 20, 5, 4)", (2.24, 48, 20, 5, 4)),
                    ("us/kr challenger long: bar(2.24, 151, 63, 5, 13)", (2.24, 151, 63, 5, 13))):
    print(f"  {label} -> {calibrate.bar(*args)}")
print("  plain_bar(2.0, 12) ->", calibrate.plain_bar(2.0, 12))

print("4. already-recorded historical t values against the null of their own design (what nominal bars meant)")
for label, n, h, step, lag, got in (("KR live replay LONG 252d: 77 monthly dates, lag 12, recorded t 8.20", 77, 252, 21, 12, 8.20),
                                    ("KR universe test LONG 252d: 77 monthly dates, lag 12, recorded t 2.46", 77, 252, 21, 12, 2.46),
                                    ("KR long early: 23 monthly dates, lag 12, recorded t 2.05", 23, 252, 21, 12, 2.05),
                                    ("KR all-stock signal 20d: 232 dates step 5, lag 4, recorded t 13.43", 232, 20, 5, 4, 13.43),
                                    ("KR all-stock signal 252d: 186 dates step 5, lag 51, recorded t 13.69", 186, 252, 5, 51, 13.69),
                                    ("US 1.2 SWING 20d: 153 monthly dates, lag 1 (no overlap), bar 2.24", 153, 20, 21, 1, 2.24)):
    t = null_t(n, h, step, lag, 40000, 7 + n + h)
    t = t[np.isfinite(t)]
    print(f"  {label}: null P(t>=2.24) {float((t >= 2.24).mean())*100:.1f}%, null 98.75% quantile {np.quantile(t, .9875):.2f}, 99.9% quantile {np.quantile(t, .999):.2f}, P(null t >= recorded) {float((t >= got).mean())*100:.3f}%")

print("5. committee paper reading: annual excess return needed, tracking error 10%/yr, bar", calibrate.bar(3.0, 240, 1, 1, 5))
rng = np.random.default_rng(5)
x = rng.standard_normal((40000, 240)) * (0.10 / math.sqrt(252))
m = x.mean(axis=1); d = x - m[:, None]
v = np.einsum("ij,ij->i", d, d) / 240
for k in range(1, 6):
    v += 2 * (1 - k / 6.0) * np.einsum("ij,ij->i", d[:, k:], d[:, :-k]) / 240
se = np.sqrt(v / 240)
bar = calibrate.bar(3.0, 240, 1, 1, 5)
for target in (.5, .8):
    lo, hi = 0.0, 2.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if float((((mid / 252) + m) / se >= bar).mean()) < target: lo = mid
        else: hi = mid
    print(f"  power {target:.0%}: annual excess {hi*100:.0f}%")
