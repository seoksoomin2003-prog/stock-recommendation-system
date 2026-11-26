"""Random numbers only. Independent check of the t bars of the live forward verdict and its power.
Own implementation of the Newey-West t (Bartlett weights, variance /n) and of the overlapping-noise series; a different seed.
No price, no return, no record is read."""
import math, sys
import numpy as np
rng = np.random.default_rng(987654321)

def nw_t(x, lag):
    n = x.shape[1]; e = x - x.mean(1, keepdims=True); v = (e * e).sum(1) / n
    for k in range(1, min(lag, n - 1) + 1):
        v += 2 * (1 - k / (lag + 1)) * (e[:, k:] * e[:, :-k]).sum(1) / n
    return x.mean(1) / np.sqrt(v / n)

def series(rows, n, h, mu=0.0, block_sd=1.0, rho=0.0):
    """n daily values, each the mean of h consecutive iid draws (overlapping h-session outcome); block_sd = sd of one value.
    rho: AR(1) of the underlying draws' slow component at block scale (persistence across neighbouring h-blocks)."""
    raw = rng.standard_normal((rows, n + h - 1))
    if rho:
        # add a slow component: AR(1) with per-step coefficient phi so that neighbouring h-block sums correlate about rho
        phi = 1 - 1.0 / (h * 3)
        slow = np.zeros_like(raw); z = rng.standard_normal(raw.shape) * math.sqrt(1 - phi * phi)
        slow[:, 0] = rng.standard_normal(rows)
        for t in range(1, raw.shape[1]): slow[:, t] = phi * slow[:, t - 1] + z[:, t]
        raw = raw + rho * slow
    c = np.cumsum(raw, 1); s = c[:, h - 1:] - np.concatenate([np.zeros((rows, 1)), c[:, :-h]], 1)
    s = s / s.std()           # one value has sd 1 (pooled)
    return mu + block_sd * s

def many(n, h, lag, sims, **kw):
    out = []
    for _ in range(0, sims, 2000): out.append(nw_t(series(2000, n, h, **kw), lag))
    return np.concatenate(out)

SIMS = 40000
print("== 1. null: chance that noise reaches the table bar and the program's bar; my own 1.25%/0.3%/0.41% quantile")
designs = [("swing verdict 240 x 20d", 240, 20, 2.24, 3.3, 0.0125), ("long verdict 756 x 63d", 756, 63, 2.24, 3.35, 0.0125),
           ("early 60 x 5d", 60, 5, 2.75, 4.29, 0.00298), ("early 120 x 5d", 120, 5, 2.75, 3.76, 0.00298),
           ("cont 480 x 20d", 480, 20, 2.64, None, 0.00415), ("cont 720 x 20d", 720, 20, 2.64, None, 0.00415), ("cont 960 x 20d", 960, 20, 2.64, None, 0.00415)]
mine = {}
for name, n, h, nominal, claimed, level in designs:
    sims = SIMS if n <= 480 else 16000
    t = many(n, h, h, sims)
    q = float(np.quantile(t, 1 - level)); mine[name] = q
    print(f"{name:26s} sims {sims}: P(t>={nominal}) = {100*np.mean(t>=nominal):.2f}%  my quantile at {100*level:.3f}% = {q:.2f}  documented bar = {claimed}"
          + (f"  P(t>=documented) = {100*np.mean(t>=claimed):.2f}%" if claimed else ""))
print("== 2. power of the 240-session swing verdict, t condition alone and with 'IC > 0 in both halves' and 'mean IC >= 0.02'")
print("   sd = standard deviation of one day's 20-session IC (BT-1's recorded figures imply roughly 0.10 for Korea, 0.15-0.20 for the US)")
for sd in (0.08, 0.10, 0.15, 0.20):
    for mu in (0.02, 0.03, 0.05, 0.08, 0.10):
        x = np.concatenate([series(2000, 240, 20, mu=mu, block_sd=sd) for _ in range(10)])
        t = nw_t(x, 20); ok_t = t >= 3.3
        halves = (x[:, :120].mean(1) > 0) & (x[:, 120:].mean(1) > 0) & (x.mean(1) >= 0.02)
        print(f"   sd {sd:.2f} true IC {mu:.2f}: t>=3.3 {100*ok_t.mean():5.1f}%   t and halves and mean {100*(ok_t&halves).mean():5.1f}%")
print("== 3. power by record length at true IC 0.05 (same design, bar re-read from my own quantile for that length)")
for n, bar in ((240, 3.3), (480, mine["cont 480 x 20d"]), (720, mine["cont 720 x 20d"]), (960, mine["cont 960 x 20d"])):
    for sd in (0.10, 0.18):
        x = np.concatenate([series(2000, n, 20, mu=0.05, block_sd=sd) for _ in range(5)])
        print(f"   n {n} sd {sd}: bar {bar:.2f} pass {100*np.mean(nw_t(x,20)>=bar):.1f}%")
print("== 4. persistence between neighbouring 20-session blocks: false passes of the 3.3 bar")
for rho in (0.0, 0.5, 1.0, 1.5):
    x = np.concatenate([series(2000, 240, 20, rho=rho) for _ in range(10)])
    b = x[:, ::20]; e = b - b.mean(1, keepdims=True); r1 = ((e[:, :-1] * e[:, 1:]).sum(1) / (e * e).sum(1)).mean()
    print(f"   slow share {rho}: mean lag-1 of 12 blocks {r1:+.2f}  P(t>=3.3) = {100*np.mean(nw_t(x,20)>=3.3):.2f}%")
print("== 5. money condition (sign in both halves) under no score effect: two independent halves with a common drift d (in sd of a half mean)")
for d in (0.0, 0.3, 0.6):
    z = rng.standard_normal((200000, 2)) + d
    print(f"   drift {d}: both halves > 0 = {100*np.mean((z>0).all(1)):.1f}%")
