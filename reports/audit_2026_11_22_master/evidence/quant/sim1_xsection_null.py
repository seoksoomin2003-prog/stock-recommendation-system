"""SIM 1: false-positive rate of the Newey-West t on daily cross-sectional ICs of overlapping h-day forward returns, under the null.

Design (stated exactly):
  * N = 300 stocks, daily log returns i.i.d. N(0, 0.02^2), independent across stocks and days (no factor structure).
  * Score has NO relation to returns.  Three persistence cases: 'fixed' (one draw per stock, kept all days: a slow fundamental score),
    'ar98' (AR(1) per stock, daily rho 0.98), 'redrawn' (a fresh i.i.d. score every day).
  * Forward return of day t = sum of daily returns t+1 .. t+h, h = 20.  n = 240 consecutive days (every recorded day counts).
  * IC_t = Spearman rank correlation(score_t, forward return_t).  Also top-fifth mean minus universe mean (spread).
  * Statistic: the repo's newey_west_t (Bartlett weights 1-k/(lag+1)), lag = h (what live_forward.py:111 uses), plus lag 0, 2h,
    Hansen-Hodrick (uniform weights, lag h-1), and the non-overlapping t on every h-th day (12 samples).
  * 2,000 simulations per case (seeded).  One-sided rate = share with t >= threshold; two-sided = |t| >= threshold.
"""
import sys, json
import numpy as np
from simlib import nw_t, plain_t, ranks, rowcorr, selfcheck

selfcheck()
N, H, NDAYS, SIMS = 300, 20, 240, 2000
THR = (2.0, 2.24, 2.39, 2.45, 2.86, 3.0)
rng = np.random.default_rng(20261122)

def one_case(kind):
    ic = np.empty((SIMS, NDAYS)); sp = np.empty((SIMS, NDAYS))
    for s in range(SIMS):
        r = rng.standard_normal((NDAYS + H, N)) * 0.02
        c = np.vstack([np.zeros((1, N)), r.cumsum(axis=0)])          # c[t] = sum of r[0..t-1]
        fwd = c[H + 1:H + 1 + NDAYS] - c[1:NDAYS + 1]               # day t: returns t+1..t+H  (r index t+1 .. t+H)
        if kind == "fixed":
            score = np.repeat(rng.standard_normal((1, N)), NDAYS, axis=0)
        elif kind == "redrawn":
            score = rng.standard_normal((NDAYS, N))
        else:
            eps = rng.standard_normal((NDAYS, N)) * np.sqrt(1 - 0.98 ** 2)
            score = np.empty((NDAYS, N)); score[0] = rng.standard_normal(N)
            for t in range(1, NDAYS):
                score[t] = 0.98 * score[t - 1] + eps[t]
        rs, rf = ranks(score), ranks(fwd)
        ic[s] = rowcorr(rs, rf)
        top = rs >= 0.8 * (N - 1)
        sp[s] = (fwd * top).sum(axis=1) / top.sum(axis=1) - fwd.mean(axis=1)
    return ic, sp

def rates(t, thr):
    t = t[np.isfinite(t)]
    return round(float((t >= thr).mean()) * 100, 2), round(float((np.abs(t) >= thr).mean()) * 100, 2)

out = {}
for kind in ("fixed", "ar98", "redrawn"):
    ic, sp = one_case(kind)
    res = {"ic_sd_daily": round(float(ic.std()), 4), "ic_lag1_autocorr": round(float(np.mean([np.corrcoef(x[1:], x[:-1])[0, 1] for x in ic[:200]])), 3)}
    for name, series in (("IC", ic), ("top_fifth_minus_universe", sp)):
        stats = {"NW lag 0 (plain)": nw_t(series, 0), f"NW lag {H} (repo)": nw_t(series, H), f"NW lag {2 * H}": nw_t(series, 2 * H),
                 f"Hansen-Hodrick lag {H - 1}": nw_t(series, H - 1, "uniform"), "non-overlapping every 20th (n=12)": plain_t(series[:, ::H])}
        res[name] = {k: {str(th): rates(v, th) for th in THR} for k, v in stats.items()}
        res[name]["HH_nonpositive_variance_share_pct"] = round(float(np.isnan(stats[f"Hansen-Hodrick lag {H - 1}"]).mean()) * 100, 2)
    # the full condition A of live_forward (t part, IC floor and both halves; spread/buy-band parts need costs and are left out = upper bound)
    t = nw_t(ic, H); m = ic.mean(axis=1); e = ic[:, :NDAYS // 2].mean(axis=1); l = ic[:, NDAYS // 2:].mean(axis=1)
    res["live_forward_condition_A_upper_bound_pct"] = {"t>=2.24": round(float((t >= 2.24).mean()) * 100, 2),
        "t>=2.24 & IC>=0.02": round(float(((t >= 2.24) & (m >= 0.02)).mean()) * 100, 2),
        "t>=2.24 & IC>=0.02 & both halves>0": round(float(((t >= 2.24) & (m >= 0.02) & (e > 0) & (l > 0)).mean()) * 100, 2)}
    out[kind] = res
    print(kind, json.dumps(res, indent=1)); sys.stdout.flush()
