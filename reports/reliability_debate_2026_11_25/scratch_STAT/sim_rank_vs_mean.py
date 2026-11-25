"""STAT seat, random numbers only.  Can a score rank well (IC ~ +0.05, large t) and still earn nothing at the top?

Made-up cross-sections of 280 stocks on 89 separate days.  The score orders stocks by a risk trait.  Every stock has the SAME
expected return; a low-score stock has a wider spread of outcomes and a small chance of a very large gain (paid for by a slightly
lower ordinary return), as lottery-like names do.  A rank correlation looks at the ordinary (median) outcome; an account earns
the average outcome.  For contrast: a bell-shaped world where the same IC comes from a real difference in averages.
"""
import numpy as np

rng = np.random.default_rng(20261125)
N, DAYS, SIMS, COST = 280, 89, 1500, 0.0053


def rank(a):
    return np.argsort(np.argsort(a, axis=-1), axis=-1).astype(float)


def ic_of(score, ret):
    s, r = rank(score), rank(ret)
    s -= s.mean(-1, keepdims=True); r -= r.mean(-1, keepdims=True)
    return (s * r).sum(-1) / np.sqrt((s * s).sum(-1) * (r * r).sum(-1))


def fifths(score, ret):
    order = np.argsort(score, axis=-1)
    parts = np.array_split(np.take_along_axis(ret, order, -1), 5, axis=-1)
    return np.stack([p.mean(-1) for p in parts], -1)            # lowest fifth first


def run(kind, jump_p=0.04, jump=0.45, sd_lo=0.07, sd_hi=0.14, ic_target=0.054):
    out = {"ic": [], "t": [], "spread": [], "f": []}
    for _ in range(SIMS):
        z = rng.standard_normal((DAYS, N))                          # the score (higher = calmer stock)
        u = (rank(z) + 0.5) / N                                     # 0 (lowest score) .. 1 (highest)
        if kind == "skew":
            sd = sd_hi + (sd_lo - sd_hi) * u                        # low score: wider outcomes
            p = jump_p * (1 - u)                                    # low score: a chance of a very large gain
            hit = rng.random((DAYS, N)) < p
            ret = sd * rng.standard_normal((DAYS, N)) + hit * jump - p * jump      # every stock: expected return 0
        else:                                                       # bell-shaped: the IC is a difference in averages
            ret = 0.10 * (ic_target * 1.05 * z + np.sqrt(1 - ic_target ** 2) * rng.standard_normal((DAYS, N)))
        ic = ic_of(z, ret)
        f = fifths(z, ret).mean(0)
        out["ic"].append(ic.mean()); out["t"].append(ic.mean() / (ic.std(ddof=1) / np.sqrt(DAYS)))
        out["spread"].append(f[4] - f[0]); out["f"].append(f)
    f = np.mean(out["f"], 0) * 100
    sp = np.array(out["spread"]) * 100
    print(f"{kind:5s} | mean IC {np.mean(out['ic']):+.3f} | mean t {np.mean(out['t']):+.2f} | share of runs with t>=2.24: {np.mean(np.array(out['t']) >= 2.24) * 100:.0f}% | "
          f"fifths (low->high, %) {' / '.join(f'{x:+.2f}' for x in f)} | top-bottom {sp.mean():+.2f}% (sd across runs {sp.std():.2f}) | "
          f"runs where top-bottom beats one round trip {COST * 100:.2f}%: {np.mean(sp > COST * 100) * 100:.0f}%")


print("280 stocks, 89 days.  'skew': equal expected return for every stock.  'bell': IC from a real difference in averages.")
run("skew")
run("skew", jump_p=0.06, jump=0.40)
run("skew", jump_p=0.02, jump=0.60)
run("bell")
