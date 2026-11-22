"""SIM 3: (a) remaining null designs, (b) null critical values, (c) power of the main forward verdicts, (d) the paper-book and committee readings.

All series are synthetic.  Overlap is modelled as in SIM 2: a statistic of an h-session return observed every `step` sessions with a slow
score = moving sum of i.i.d. shocks, scaled to a stated standard deviation.  20,000 simulations per row unless said (seeded).
"""
import json, math, sys
import numpy as np
from simlib import nw_t, plain_t, selfcheck

selfcheck()
SIMS = 20000
rng = np.random.default_rng(20261124)

def moving_sum(n, h, step, sims=SIMS, unit=True, dist="normal"):
    L = n * step + h + 1
    out = np.empty((sims, n)); B = 2000
    for b in range(0, sims, B):
        e = rng.standard_normal((B, L)) if dist == "normal" else rng.standard_t(3, size=(B, L)) / math.sqrt(3.0)
        c = np.concatenate([np.zeros((B, 1)), e.cumsum(axis=1)], axis=1)
        idx = np.arange(n) * step
        out[b:b + B] = c[:, idx + h + 1] - c[:, idx + 1]
    return out / math.sqrt(h) if unit else out

def P(x): return round(float(np.mean(x)) * 100, 2)

print("## (a) remaining null designs: step 5 sampling with lag ceil(h/5)  [research_swing.py:353; us_challenger.py:215,238; kr_challenger.py:220]")
for label, n, h, step, lag in (("US/KR challenger swing forward: 240 matured /5 = 48 samples, h20", 48, 20, 5, 4), ("challenger long forward: 756/5 = 151 samples, h63", 151, 63, 5, 13),
                               ("historical swing test 2022-2026, 232 dates, h20", 232, 20, 5, 4), ("historical SUE test, 232 dates, h10", 232, 10, 5, 2)):
    t = nw_t(moving_sum(n, h, step), lag)
    print(json.dumps({"label": label, "n": n, "h": h, "step": step, "lag": lag, "one_sided_2.0": P(t >= 2.0), "two_sided_2.0": P(np.abs(t) >= 2.0), "one_sided_2.24": P(t >= 2.24), "one_sided_2.86": P(t >= 2.86)}))
t12 = plain_t(moving_sum(240, 20, 1)[:, ::20])
print(json.dumps({"label": "kr_swing_challenger / kr_swing_prior: 12 separate samples, plain t (kr_swing_challenger.py:103,144)", "one_sided_2.0": P(t12 >= 2.0), "two_sided_2.0": P(np.abs(t12) >= 2.0)}))

print("## (b) null quantiles of the repo's t: the threshold that would really give 2.5% / 1.25% / 0.5% one-sided")
for label, n, h, step, lag in (("daily h20 n240 lag20", 240, 20, 1, 20), ("daily h63 n756 lag63", 756, 63, 1, 63), ("monthly h252 n142 lag12 (US 2014-2025)", 142, 252, 21, 12),
                               ("monthly h252 n77 lag12 (KR replay)", 77, 252, 21, 12), ("monthly h252 n23 lag12 (KR long early)", 23, 252, 21, 12), ("monthly h252 n22 lag12 (US OOS 2011-12)", 22, 252, 21, 12)):
    t = nw_t(moving_sum(n, h, step, sims=100000 if n <= 150 else SIMS), lag)
    q = np.quantile(t, [0.975, 0.9875, 0.995, 0.999])
    extra = {}
    if "KR replay" in label:
        extra = {"P(t>=8.2029)_pct": round(float((t >= 8.2029).mean()) * 100, 4), "P(t>=2.4569)_pct": P(t >= 2.4569), "sims": len(t), "max_t_seen": round(float(t.max()), 2)}
    if "KR long early" in label:
        extra = {"P(t>=2.0464)_pct": P(t >= 2.0464)}
    if "n142" in label:
        extra = {"P(t>=2.00)_pct": P(t >= 2.0), "P(t>=1.4468)_pct": P(t >= 1.4468)}
    print(json.dumps({"label": label, "q97.5": round(q[0], 2), "q98.75": round(q[1], 2), "q99.5": round(q[2], 2), "q99.9": round(q[3], 2), **extra}))

print("## (c) power of the live forward verdict's t condition: daily IC = mu + sd * (overlapping noise), pass = t>=2.24 & mean>=0.02 & both halves>0")
print("#     sd values are the project's own recorded figures (reports/QSF_LIVE_FORWARD_POWER_2026_11_11.md); 0.058 is the pure-noise floor of 300 names (SIM 1)")
def power_curve(n, h, sd, mus, thr=2.24):
    z = moving_sum(n, h, 1, sims=10000)
    out = {}
    for mu in mus:
        x = mu + sd * z
        t = nw_t(x, h)
        ok = (t >= thr) & (x.mean(axis=1) >= 0.02) & (x[:, :n // 2].mean(axis=1) > 0) & (x[:, n // 2:].mean(axis=1) > 0)
        out[mu] = P(ok)
    return out
def crossing(curve, level):
    ks = sorted(curve)
    for a, b in zip(ks, ks[1:]):
        if curve[a] < level <= curve[b]:
            return round(a + (b - a) * (level - curve[a]) / (curve[b] - curve[a]), 3)
    return None
grid = [round(0.01 * k, 2) for k in range(0, 31)]
for label, n, h, sd in (("KR swing 20d, 240 sessions", 240, 20, 0.138), ("US swing 20d, 240 sessions", 240, 20, 0.197), ("pure-noise floor swing", 240, 20, 0.058),
                        ("KR long 63d, 756 sessions", 756, 63, 0.107), ("US long 63d, 756 sessions", 756, 63, 0.140)):
    c = power_curve(n, h, sd, grid)
    print(json.dumps({"label": label, "sd": sd, "power_pct_at_IC": {str(k): c[k] for k in (0.0, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20)}, "IC_for_50pct": crossing(c, 50), "IC_for_80pct": crossing(c, 80)}))

print("## (d1) committee paper reading: 240 daily excess returns, NW lag 5, |t| >= 3.0  (terminal/committee/reading.py:18,25,48)")
for dist in ("normal", "t3"):
    e = rng.standard_normal((SIMS, 240)) if dist == "normal" else rng.standard_t(3, size=(SIMS, 240))
    t = nw_t(e, 5)
    print(json.dumps({"null": dist, "P(t>=3)": P(t >= 3), "P(t<=-3)": P(t <= -3), "P(|t|>=3)": P(np.abs(t) >= 3)}))
# volatility clustering (GARCH(1,1) a=0.08 b=0.90) under the null
g = np.empty((SIMS, 240)); v = np.ones(SIMS)
for k in range(240):
    z = rng.standard_normal(SIMS); g[:, k] = np.sqrt(v) * z; v = 0.02 + 0.08 * g[:, k] ** 2 + 0.90 * v
t = nw_t(g, 5); print(json.dumps({"null": "garch(0.08,0.90)", "P(t>=3)": P(t >= 3), "P(|t|>=3)": P(np.abs(t) >= 3)}))
print("#   power: tracking error TE (annual sd of the daily excess), true annual excess alpha; daily mean = alpha/252, daily sd = TE/sqrt(252)")
for te in (0.05, 0.10, 0.15, 0.20):
    z = rng.standard_normal((10000, 240)); sd = te / math.sqrt(252)
    curve = {}
    for a in [round(0.02 * k, 2) for k in range(0, 61)]:
        curve[a] = P(nw_t(a / 252 + sd * z, 5) >= 3.0)
    print(json.dumps({"TE_annual": te, "alpha_for_50pct": crossing(curve, 50), "alpha_for_80pct": crossing(curve, 80), "power_at_alpha": {str(a): curve[a] for a in (0.02, 0.06, 0.10, 0.20, 0.30, 0.40)}}))
print("#   cash drag: a portfolio that holds a fraction w of stocks with zero selection skill (stock part = index), excess = -(1-w) * index return")
print("#   index: daily mean m/252, daily sd 16%/sqrt(252); the reading says BETTER when the index FELL enough, WORSE when it rose enough")
for w in (0.3, 0.5, 0.7):
    for m in (-0.30, -0.15, 0.0, 0.15, 0.30):
        idx = m / 252 + 0.16 / math.sqrt(252) * rng.standard_normal((10000, 240))
        t = nw_t(-(1 - w) * idx, 5)
        print(json.dumps({"invested": w, "index_annual_drift": m, "P(BETTER)": P(t >= 3), "P(WORSE)": P(t <= -3)}))

print("## (d2) rank book RK-1: 240 daily differences, NW lag 20, ADOPT at mean>0 & t>=2.0 (rank_book.py:26-27,84)")
e = rng.standard_normal((SIMS, 240)); print(json.dumps({"null": "iid normal", "P(ADOPT)": P(nw_t(e, 20) >= 2.0)}))
# the two books differ only while a position differs: episodes.  k episodes of 30 sessions, zero elsewhere.
for k in (2, 4):
    x = np.zeros((SIMS, 240))
    for s in range(SIMS):
        for st in rng.choice(210, size=k, replace=False):
            x[s, st:st + 30] = rng.standard_normal(30)
    print(json.dumps({"null": f"{k} episodes of 30 sessions, zero elsewhere", "P(ADOPT)": P(nw_t(x, 20) >= 2.0)}))
# persistent difference in holdings: AR(1) daily difference with rho 0.2 (stale prices / shared drift)
for rho in (0.1, 0.3):
    x = np.empty((SIMS, 240)); x[:, 0] = rng.standard_normal(SIMS)
    for k in range(1, 240):
        x[:, k] = rho * x[:, k - 1] + math.sqrt(1 - rho * rho) * rng.standard_normal(SIMS)
    print(json.dumps({"null": f"AR(1) rho {rho}", "P(ADOPT)": P(nw_t(x, 20) >= 2.0)}))
print("## (d3) turnover book TO-1: ADOPT at cheaper & mean difference >= 0, no t (turnover_book.py:146-147)")
e = rng.standard_normal((SIMS, 240)); print(json.dumps({"null": "iid, cost condition taken as met", "P(mean>=0)": P(e.mean(axis=1) >= 0)}))
