"""Agent 06 (2026-11-25).  Fabricated prices only: does the fixed record.performance give a buy-and-hold paper portfolio's true
return?  A portfolio bought once (10 stocks, 80% invested), never traded, its recorded weights following prices as the program
records them (portfolios.drift).  Truth = value of the actually held shares from the close of D+1 (first trade) to the end."""
import sys
from pathlib import Path
import numpy as np
repo = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo))
from terminal.committee import record, portfolios

def one(seed, n=240, k=10, rho=0.0, cost=0.0):
    rng = np.random.default_rng(seed)
    e = rng.normal(0, 0.02, (n + 2, k))
    r = e.copy()
    for i in range(1, n + 2):
        r[i] = e[i] + rho * e[i - 1]
    px = 100 * np.cumprod(1 + r, axis=0)
    sess = [f"d{i:04d}" for i in range(n + 2)]
    tick = [f"T{j}" for j in range(k)]
    P = {(tick[j], sess[i]): float(px[i, j]) for i in range(n + 2) for j in range(k)}
    w = {t: 0.08 for t in tick}
    rows = []
    for i in range(n + 2):
        if i:
            w = portfolios.drift(w, lambda t, i=i: P[(t, sess[i])] / P[(t, sess[i - 1])] - 1)
        rows.append({"session": sess[i], "portfolios": {"P": {"holdings": dict(w)}}})
    out = record.performance(rows, lambda t, s: P.get((t, s)), lambda s: 100.0, cost, keep_daily=True)
    daily = out["portfolios"]["P"]["daily"]
    prog = float(np.prod([1 + d for d in daily]) - 1)
    # truth: buy 8% in each at the close of sess[1], hold to sess[n+1]
    shares = {j: 0.08 / px[1, j] for j in range(k)}
    v_end = 0.2 + sum(shares[j] * px[n + 1, j] for j in range(k))
    return prog, v_end - 1.0, out["portfolios"]["P"].get("cost_total"), out["portfolios"]["P"].get("turnover_per_day")

for rho in (0.0, -0.1, 0.1):
    diffs, tov = [], []
    for s in range(200):
        a, b, c, t = one(s, rho=rho)
        diffs.append(a - b); tov.append(t or 0)
    d = np.array(diffs)
    print(f"daily autocorrelation {rho:+.1f}: program minus true over 240 days mean {d.mean()*100:+.3f}%  sd {d.std()*100:.3f}%  max |diff| {abs(d).max()*100:.3f}%  turnover/day mean {np.mean(tov):.5f}")
a, b, c, t = one(1, cost=0.002)
print("with one-way cost 0.2%: recorded cost total", c, "(first purchase of 80% x 0.2% = 0.0016 expected if nothing else is traded)")
