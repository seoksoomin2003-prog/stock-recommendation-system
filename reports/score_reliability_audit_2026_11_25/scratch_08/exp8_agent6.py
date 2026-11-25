"""Agent 8, second pass on Agent 6.  Random numbers and file values only (the t-values and designs of the twelve BT-1 cells
are read from reports/qsf/QSF_BACKTEST_CURRENT_*.json; no return is computed).  Seed 8808.
(1) one-sided chance of each cell's t under noise of its own design, then Holm at 5% under three definitions of the family.
(2) the three nested continuation looks: chance that noise passes at least one of them (bars 3.66 / 3.52 / 3.44).
(3) a pay-off that persists for months, built differently from Agent 6's AR(0.98) part: a two-state mean (+m / -m) that
    switches with chance 1/60 a day.  Adjacent-month correlation of separate 20-session sums, and the chance of passing 3.33."""
import sys, json, math
import numpy as np
sys.path.insert(0, '.')
from terminal.qsf import calibrate
rng = np.random.default_rng(8808)
STEP = 21
cells = []
for m in ('US', 'KR'):
    d = json.load(open(f'reports/qsf/QSF_BACKTEST_CURRENT_{m}.json'))
    for st, v in d['strategies'].items():
        for h, x in v['horizons'].items():
            r = x['rank']; cells.append((m, st, int(h), r['dates'], r['lag'], r['t']))
print("(1) cell | dates | lag | t | chance under noise of its design (one-sided)")
p = {}
for m, st, h, n, lag, t in cells:
    sims = 200000
    got = np.concatenate([calibrate.t_many(calibrate.noise(rng, 4000, n, h, STEP), lag) for _ in range(sims // 4000)])
    pv = float((got >= t).mean()); p[(m, st, h)] = max(pv, 1.0 / sims)
    print(f"   {m} {st:9s} {h:3d} | {n:3d} | {lag:2d} | {t:5.2f} | {pv*100:7.3f}%" + ("  (under 1 in 200,000)" if pv == 0 else ""))
def holm(keys, alpha=0.05):
    order = sorted(keys, key=lambda k: p[k]); out = []
    for i, k in enumerate(order):
        if p[k] * (len(order) - i) <= alpha: out.append((k, round(p[k] * (len(order) - i) * 100, 2)))
        else: break
    return out
fam = {"all twelve cells": list(p),
       "four primary cells of BT-1 (swing 20, long 252)": [k for k in p if (k[1] == 'SWING' and k[2] == 20) or (k[1] == 'LONG_TERM' and k[2] == 252)],
       "four primary cells of the live verdict (swing 20, long 63)": [k for k in p if (k[1] == 'SWING' and k[2] == 20) or (k[1] == 'LONG_TERM' and k[2] == 63)]}
for name, keys in fam.items():
    print(f"   Holm 5%, {name}: passes ->", holm(keys))
k = ('KR', 'LONG_TERM', 63)
print(f"   Korean long 63: raw chance {p[k]*100:.2f}%; times 3 (live-verdict family, after Korean swing) {p[k]*300:.2f}%; times 9 (twelve cells) {p[k]*900:.1f}%; times 12 implicit tries {p[k]*1200:.1f}%")

print("\n(2) nested looks of one record (h=20, daily, lag 20)")
bars = {240: calibrate.bar(2.24, 240, 20, 1, 20), 480: calibrate.bar(2.64, 480, 20, 1, 20), 720: calibrate.bar(2.64, 720, 20, 1, 20), 960: calibrate.bar(2.64, 960, 20, 1, 20)}
hit = {n: 0 for n in bars}; anyc = 0; anyall = 0; after_fail = 0; tot = 0
for _ in range(60):
    x = calibrate.noise(rng, 2000, 960, 20, 1)
    ok = {n: calibrate.t_many(x[:, :n], 20) >= bars[n] for n in bars}
    for n in bars: hit[n] += int(ok[n].sum())
    c = ok[480] | ok[720] | ok[960]
    anyc += int(c.sum()); anyall += int((c | ok[240]).sum()); after_fail += int((c & ~ok[240]).sum()); tot += 2000
print("   bars", bars, "sims", tot)
print("   each look:", {n: f"{hit[n]/tot*100:.2f}%" for n in bars})
print(f"   at least one of the three continuation looks: {anyc/tot*100:.2f}%  (sum of the three {sum(hit[n] for n in (480,720,960))/tot*100:.2f}%);  after a failed first verdict {after_fail/tot*100:.2f}%;  first verdict or a continuation {anyall/tot*100:.2f}%")

print("\n(3) a persisting pay-off of a different shape: two-state mean, expected stay 60 sessions")
for m_size in (0.0, 0.05, 0.10, 0.15, 0.20, 0.30):
    ts, a, b = [], [], []
    for _ in range(10):
        rows, T = 2000, 240 + 40 + 19
        sw = rng.random((rows, T)) < 1 / 60.0
        state = np.where(rng.random((rows, 1)) < 0.5, 1.0, -1.0) * np.cumprod(np.where(sw, -1.0, 1.0), axis=1)
        e = rng.standard_normal((rows, T)) + m_size * state
        c = np.cumsum(e, axis=1); s = c[:, 19:] - np.concatenate([np.zeros((rows, 1)), c[:, :-20]], axis=1)
        ts.append(calibrate.t_many(s[:, :240], 20)); a.append(s[:, 0]); b.append(s[:, 20])
    t = np.concatenate(ts); rho = np.corrcoef(np.concatenate(a), np.concatenate(b))[0, 1]
    print(f"   state mean +-{m_size:.2f} sd: correlation of one separate 20-session value with the next {rho:+.3f};  noise passes 3.33: {(t>=3.33).mean()*100:.2f}%  (passes 2.24: {(t>=2.24).mean()*100:.1f}%)")
