"""AGENT 6 - script 4.  Can a score have a clearly positive rank correlation with returns while its top and bottom fifths earn
the same on average?  A made-up market in which EVERY stock has the same expected return.  Random numbers only.  Seed 60610.

  280 stocks, 89 separate 20-session periods (the shape of BT-1's Korean swing table).
  Stock i has its own volatility v_i (20 sessions): lognormal, median 10%, 5%..95% about 5%..21%.           ASSUMPTION
  log return_i = b_i * market - v_i^2/2 + v_i * e_i      (so the expected simple own return is 0 for every stock)
  market: sd 6% per period;  b_i = 0.5 + 5 * v_i  (a wilder stock has a higher beta), less b^2*var/2 so the mean stays equal
  score_i = -(v_i) + noise: a "risk" score that likes calm stocks (rank correlation of score with -v about 0.8)
  variant "lottery": besides, with chance 2% * (v_i/median) a stock jumps +60% in a period, paid for by a lower drift.
The same statistics validate.per_date computes: rank correlation of score with return less the day's mean; top fifth - bottom fifth.
"""
import math, json
import numpy as np
SEED = 60610
N, D, REPS = 280, 89, 500          # x 3 batches = 1,500 made-up histories


def rank(a):
    return np.argsort(np.argsort(a, axis=-1), axis=-1).astype(float)


def world(rng, lottery):
    v = np.exp(rng.normal(math.log(0.10), 0.45, (REPS, 1, N)))
    score = -np.log(v) + rng.normal(0, 0.33, (REPS, D, N)) * 1.0           # log scale; noisy every period
    mkt = rng.normal(0.0, 0.06, (REPS, D, 1))
    b = 0.5 + 5 * v
    ell = b * mkt - (b * 0.06) ** 2 / 2 - v ** 2 / 2 + v * rng.standard_normal((REPS, D, N))
    r = np.exp(ell) - 1
    if lottery:
        p = np.clip(0.02 * v / 0.10, 0, 0.2)
        jump = rng.random((REPS, D, N)) < p
        r = (1 + r) * np.where(jump, 1.6, 1.0) / (1 + 0.6 * p) - 1          # the drift pays for the jump: the mean stays the same
    return score, r, v


def stats(score, r):
    ex = r - r.mean(axis=2, keepdims=True)
    rs, rr = rank(score), rank(ex)
    rs -= rs.mean(axis=2, keepdims=True); rr -= rr.mean(axis=2, keepdims=True)
    ic = (rs * rr).sum(axis=2) / np.sqrt((rs ** 2).sum(axis=2) * (rr ** 2).sum(axis=2))          # (REPS, D)
    q = rank(score) / (N - 1)
    top, bot = q >= 0.8, q <= 0.2
    mtop = (ex * top).sum(axis=2) / top.sum(axis=2); mbot = (ex * bot).sum(axis=2) / bot.sum(axis=2)
    med_top = np.nanmedian(np.where(top, ex, np.nan), axis=2); med_bot = np.nanmedian(np.where(bot, ex, np.nan), axis=2)
    t = ic.mean(axis=1) / (ic.std(axis=1, ddof=1) / math.sqrt(D))
    sp = mtop - mbot
    t_sp = sp.mean(axis=1) / (sp.std(axis=1, ddof=1) / math.sqrt(D))
    return {"ic_mean": float(ic.mean()), "ic_sd_between_dates": float(ic.std(axis=1, ddof=1).mean()), "t_median": float(np.median(t)), "t_5_95": [float(np.quantile(t, 0.05)), float(np.quantile(t, 0.95))],
            "share_t_ge_2.35": float((t >= 2.35).mean()), "ic_positive_share": float((ic > 0).mean()),
            "top_minus_bottom_mean_pct": float(sp.mean() * 100), "spread_t_median": float(np.median(t_sp)), "share_spread_t_ge_2": float((t_sp >= 2).mean()),
            "top_minus_bottom_median_pct": float((med_top - med_bot).mean() * 100),
            "top_fifth_vol_vs_bottom": None}


out = {}
for name, lot in (("equal means, calm vs wild stocks (lognormal)", False), ("the same + rare large jumps among the wild stocks", True)):
    rng = np.random.default_rng([SEED, int(lot)])
    parts = []
    for _ in range(3):                                   # 3 x 500 made-up histories, memory
        s, r, v = world(rng, lot)
        parts.append(stats(s, r))
    agg = {k: (float(np.mean([p[k] for p in parts])) if not isinstance(parts[0][k], (list, type(None))) else parts[0][k]) for k in parts[0]}
    out[name] = agg
    print(f"\n== {name}")
    print(f"   mean rank correlation {agg['ic_mean']:+.3f} (BT-1 Korea swing 20 sessions: +0.054) | its sd between dates {agg['ic_sd_between_dates']:.3f} (file-implied 0.100) | share of dates positive {100*agg['ic_positive_share']:.0f}% (file 72%)")
    print(f"   t of the rank correlation over 89 dates: median {agg['t_median']:.2f}, 5%..95% {agg['t_5_95'][0]:.2f}..{agg['t_5_95'][1]:.2f}; histories with t >= 2.35: {100*agg['share_t_ge_2.35']:.0f}%  (file: 5.13)")
    print(f"   top fifth - bottom fifth, MEAN: {agg['top_minus_bottom_mean_pct']:+.3f}% a period (file: +0.08% before the spread's cost line; true value in this world: 0) | histories where that difference has t >= 2: {100*agg['share_spread_t_ge_2']:.1f}%")
    print(f"   top fifth - bottom fifth, MEDIAN: {agg['top_minus_bottom_median_pct']:+.3f}% a period")
print("\nFor comparison, in a bell-shaped world where every stock has the same volatility, a rank correlation of 0.054 means a top-minus-bottom mean of about")
for sx in (0.08, 0.10, 0.12):
    print(f"   2.80 x 0.054 x {sx:.2f} = {280*0.054*sx:.2f}% a period (cross-sectional sd {sx:.0%})")
json.dump(out, open("s04_out.json", "w"), indent=1)
