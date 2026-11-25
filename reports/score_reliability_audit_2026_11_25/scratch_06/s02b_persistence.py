"""AGENT 6 - script 2b.  How much a pay-off that drifts for months (which the Newey-West lag of one horizon cannot see) lifts the
chance pass rate of the 240-session swing verdict and the 756-session long verdict.  Random numbers only.  Seed 60608.
Daily shock = sqrt(1-w) * white noise + sqrt(w) * slow part (daily AR 0.98).  w = 0 is the program's own null."""
import math, json
import numpy as np
SEED, BLOCK = 60608, 2000

def nw_t(x, lag):
    n = x.shape[1]; e = x - x.mean(axis=1, keepdims=True)
    lrv = np.einsum("ij,ij->i", e, e) / n
    for k in range(1, min(lag, n - 1) + 1):
        lrv += 2.0 * (1.0 - k / (lag + 1.0)) * np.einsum("ij,ij->i", e[:, k:], e[:, :-k]) / n
    return x.mean(axis=1) / np.sqrt(lrv / n)

def shocks(rng, rows, n, w, phi=0.98):
    if w == 0:
        return rng.standard_normal((rows, n))
    z = rng.standard_normal((rows, n + 200)); slow = np.empty_like(z); slow[:, 0] = z[:, 0]
    for j in range(1, z.shape[1]):
        slow[:, j] = phi * slow[:, j - 1] + math.sqrt(1 - phi * phi) * z[:, j]
    return math.sqrt(1 - w) * rng.standard_normal((rows, n)) + math.sqrt(w) * slow[:, 200:]

out = {}
print(f"{'design':26s} {'w':>6s} {'corr of next separate IC':>25s} {'t>=2.24':>9s} {'t>=bar':>8s} {'bar':>5s}")
for name, n, h, bar, sims in (("swing 240 x 20d", 240, 20, 3.33, 40000), ("long 756 x 63d", 756, 63, 3.35, 16000)):
    for w in (0.0, 0.005, 0.01, 0.02, 0.05):
        rng = np.random.default_rng([SEED, n, int(w * 1000)])
        ts, a, b = [], [], []
        for done in range(0, sims, BLOCK):
            e = shocks(rng, BLOCK, n + 2 * h, w)
            cs = np.cumsum(e, axis=1); x = cs[:, h:] - cs[:, :-h]
            ts.append(nw_t(x[:, :n], h)); a.append(x[:, 0]); b.append(x[:, h])
        t = np.concatenate(ts); rho = float(np.corrcoef(np.concatenate(a), np.concatenate(b))[0, 1])
        out[f"{name}|{w}"] = {"rho_next": rho, "p_ge_2.24": float((t >= 2.24).mean()), "p_ge_bar": float((t >= bar).mean())}
        print(f"{name:26s} {w:6.3f} {rho:25.3f} {100*(t>=2.24).mean():8.2f}% {100*(t>=bar).mean():7.2f}% {bar:5.2f}")
json.dump(out, open("s02b_out.json", "w"), indent=1)
