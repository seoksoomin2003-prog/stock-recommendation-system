"""Agent 06.  RANDOM NUMBERS ONLY.  How often pure noise of a past test's own design reaches the t that test RECORDED
(the t values are read from the result files; nothing is recomputed from prices).  Units: one draw per evaluation step."""
import numpy as np
rng = np.random.default_rng(909)

def nw(x, lag):
    n = x.shape[1]; e = x - x.mean(axis=1, keepdims=True); var = (e * e).sum(axis=1) / n
    for k in range(1, min(lag, n - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * (e[:, k:] * e[:, :-k]).sum(axis=1) / n
    return np.where(var > 0, x.mean(axis=1) / np.sqrt(np.where(var > 0, var, 1) / n), np.nan)

def chance(n, h, lag, t_recorded, sims=40000):
    raw = rng.standard_normal((sims, n + h - 1)); c = np.cumsum(raw, axis=1)
    x = c[:, h - 1:] - np.concatenate([np.zeros((sims, 1)), c[:, :-h]], axis=1)
    t = nw(x, lag); t = t[np.isfinite(t)]
    return float(np.mean(t >= t_recorded)), float(np.quantile(t, 0.9875))

ROWS = [("KR live replay LONG 252d, former universe (n77, 21-step, lag 12)", 77, 12, 12, 8.20),
        ("KR live replay LONG 252d, CURRENT universe", 77, 12, 12, 2.46),
        ("KR live replay LONG 63d, current universe (n86, lag 3)", 86, 3, 3, 3.40),
        ("KR long early window 2016-2019 (n23, lag 12)", 23, 12, 12, 2.05),
        ("KR live replay SWING 20d, former universe (n88, lag 1)", 88, 1, 1, 1.90),
        ("US long 252d, revived names (n142, lag 12)", 142, 12, 12, 2.00),
        ("US long 252d, corrected inputs", 142, 12, 12, 1.83),
        ("KR price research SWING 20d (n232, 5-step, lag 4)", 232, 4, 4, 13.43),
        ("KR price research LONG 252d (n186, 5-step, lag 51)", 186, 51, 51, 13.69),
        ("KR fundamentals research LONG 252d", 186, 51, 51, 7.33),
        ("KR holder research LONG 252d", 186, 51, 51, 6.78)]
for name, n, h, lag, t in ROWS:
    p, q = chance(n, h, lag, t)
    print(f"{name:66s} recorded t {t:5.2f}: noise reaches it {p * 100:7.3f}%   (the t that noise reaches 1.25% of the time: {q:.2f})")
