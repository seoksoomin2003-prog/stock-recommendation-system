"""AGENT 6 - script 1.  Independent check of terminal/qsf/calibrate.py and the null tail of every recorded t.
Random numbers only: no price, no return, no record is read.  Seed 60606.
Model of the null (the same idea calibrate.py states, written again from scratch): a date's IC for an h-session return is the sum
of h independent daily contributions; dates are `step` sessions apart; t = mean / sqrt(NW long-run variance / n), Bartlett, `lag`.
"""
import math, sys, json
import numpy as np
sys.path.insert(0, "../../..")           # repository root, read-only import of the program's own function for comparison
from terminal.qsf import calibrate

SEED, SIMS, BLOCK = 60606, 60000, 3000


def nw_t(x, lag):
    n = x.shape[1]
    e = x - x.mean(axis=1, keepdims=True)
    lrv = np.einsum("ij,ij->i", e, e) / n
    for k in range(1, min(lag, n - 1) + 1):
        lrv += 2.0 * (1.0 - k / (lag + 1.0)) * np.einsum("ij,ij->i", e[:, k:], e[:, :-k]) / n
    return x.mean(axis=1) / np.sqrt(lrv / n)


def series(rng, rows, n, h, step):
    raw = rng.standard_normal((rows, (n - 1) * step + h))
    win = np.lib.stride_tricks.sliding_window_view(raw, h, axis=1)[:, ::step, :]      # (rows, n, h): my own way, not a cumsum
    return win.sum(axis=2)


def null_t(n, h, step, lag, sims=SIMS):
    rng = np.random.default_rng([SEED, n, h, step, lag])
    out = []
    for done in range(0, sims, BLOCK):
        out.append(nw_t(series(rng, min(BLOCK, sims - done), n, h, step), lag))
    return np.concatenate(out)


def direct_nw(x, lag):                 # scalar re-derivation to check nw_t itself
    n = len(x); m = x.mean(); g0 = ((x - m) ** 2).sum() / n; s = g0
    for k in range(1, lag + 1):
        gk = ((x[k:] - m) * (x[:-k] - m)).sum() / n
        s += 2 * (1 - k / (lag + 1)) * gk
    return m / math.sqrt(s / n)


rng = np.random.default_rng(1)
chk = series(rng, 5, 240, 20, 1)
print("nw_t matches a scalar re-derivation:", np.allclose(nw_t(chk, 20), [direct_nw(r, 20) for r in chk]))
# and matches the program's validate.newey_west_t
from terminal.qsf import validate
print("nw_t matches validate.newey_west_t:", np.allclose(nw_t(chk, 20), [validate.newey_west_t(list(r), 20) for r in chk]))

tail = calibrate.tail
out = {}
print("\n== A. bars of the live readings: program (seed 20261122, 100k) vs my simulation (seed 60606, 60k)")
print(f"{'design':38s} {'nominal':>7s} {'program':>8s} {'mine':>6s} {'noise>=nominal':>15s} {'noise>=program bar':>19s}")
live = [("verdict swing 240 x 20d", 2.24, 240, 20, 1, 20), ("verdict long 756 x 63d", 2.24, 756, 63, 1, 63), ("early 60 x 5d", 2.75, 60, 5, 1, 5),
        ("early 120 x 5d", 2.75, 120, 5, 1, 5), ("continuation 480 x 20d", 2.64, 480, 20, 1, 20), ("continuation 720 x 20d", 2.64, 720, 20, 1, 20),
        ("continuation 960 x 20d", 2.64, 960, 20, 1, 20), ("book 240 daily diffs, lag 20 (2.0)", 2.0, 240, 1, 1, 20), ("fund period 240 x 20d (3.0)", 3.0, 240, 20, 1, 20)]
for name, nom, n, h, step, lag in live:
    t = null_t(n, h, step, lag, 40000 if n * h > 20000 else SIMS)
    prog = calibrate.bar(nom, n, h, step, lag)
    mine = float(np.quantile(t, 1 - tail(nom)))
    out[name] = {"nominal": nom, "program_bar": prog, "my_bar": round(mine, 2), "p_noise_ge_nominal": float((t >= nom).mean()), "p_noise_ge_program_bar": float((t >= prog).mean())}
    print(f"{name:38s} {nom:7.2f} {prog:8.2f} {mine:6.2f} {100*(t>=nom).mean():14.2f}% {100*(t>=prog).mean():18.2f}%   (table says {100*tail(nom):.2f}%)")

print("\n== B. every recorded BT-1 t against the null of its own design (dates every 21 sessions)")
bt = json.load(open("bt1_cells.json"))
print(f"{'cell':22s} {'n':>4s} {'h':>4s} {'lag':>4s} {'t':>6s} {'bar@1.25%':>10s} {'p one-sided':>12s} {'p from normal table':>20s} {'95% two-sided crit':>19s}")
cells = []
for c in bt:
    t = null_t(c["n"], c["h"], 21, c["lag"])
    bar = float(np.quantile(t, 1 - tail(2.24)))
    p = float(((t >= c["t"]).sum() + 1) / (len(t) + 1))
    crit = float(np.quantile(np.abs(t), 0.95))
    cells.append({**c, "bar_1.25": round(bar, 2), "p": p, "p_normal": tail(c["t"]), "crit95": round(crit, 3)})
    print(f"{c['name']:22s} {c['n']:4d} {c['h']:4d} {c['lag']:4d} {c['t']:6.2f} {bar:10.2f} {p:12.5f} {tail(c['t']):20.5f} {crit:19.3f}")
out["bt1_cells"] = cells

print("\n== C. earlier recorded t values (file values) against the null of their own design")
earlier = [("KR replay long 252 (traded 300)", 77, 252, 12, 8.20), ("KR replay long 63", 86, 63, 3, 7.18), ("KR replay swing 20", 88, 20, 1, 1.90),
           ("KR universe test long 252 (cap)", 77, 252, 12, 2.46), ("KR universe test long 63 (cap)", 86, 63, 3, 3.40), ("KR universe test long 126 (cap)", 83, 126, 6, 2.73),
           ("KR universe RISK domain 20 (cap)", 88, 20, 1, 4.48), ("KR long early 252 (2016-18)", 23, 252, 12, 2.05), ("KR long early 63", 32, 63, 3, 3.02),
           ("KR long early 126", 29, 126, 6, 2.77), ("KR tech early TECH 20 (neg)", 81, 20, 1, 2.42), ("US corrected open A long 252", 142, 252, 12, 1.83),
           ("US open A long 252 (before fix)", 142, 252, 12, 2.00), ("US open A long 126 (before fix)", 148, 126, 6, 2.30), ("US OOS 2011-12 A long 252", 22, 252, 12, 0.31)]
rows = []
for name, n, h, lag, tv in earlier:
    t = null_t(n, h, 21, lag)
    bar = float(np.quantile(t, 1 - tail(2.24)))
    p = float(((t >= tv).sum() + 1) / (len(t) + 1))
    rows.append({"name": name, "n": n, "h": h, "lag": lag, "t": tv, "bar_1.25": round(bar, 2), "p": p})
    print(f"{name:36s} n={n:3d} h={h:3d} lag={lag:2d} t={tv:5.2f}  bar@1.25%={bar:5.2f}  p(noise>=t)={p:.5f}  (normal table {tail(tv):.5f})")
out["earlier"] = rows
json.dump(out, open("s01_out.json", "w"), indent=1)
