"""R1_FACTOR.md 의 모의실험 세 개와 위험 읽기의 검정력. 난수만 쓴다: 가격, 원장, 전향 기록을 읽지 않는다. 씨앗 고정.
실행: .venv/bin/python reports/reliability_debate_2026_11_25/R1_FACTOR_sim.py  (수 초, 메모리 수십 MB)"""
# Random numbers only. No prices, ledger or records are read.
import numpy as np
rng = np.random.default_rng(20261125)
def rank(a):
    o = a.argsort(); r = np.empty(len(a)); r[o] = np.arange(len(a))
    # average ranks for ties
    s = np.sort(a); 
    _, inv, cnt = np.unique(a, return_inverse=True, return_counts=True)
    cs = np.cumsum(cnt); avg = cs - (cnt - 1) / 2.0 - 1
    return avg[inv]
def sp(a, b):
    ra, rb = rank(a), rank(b)
    return np.corrcoef(ra, rb)[0, 1]

# (1) Skew artefact: equal expected return for every stock, only volatility differs.  Score = low volatility.
N, D = 280, 4000
ics, spreads, top_minus_4th = [], [], []
for _ in range(D):
    vol_a = rng.uniform(0.20, 0.70, N)                 # annual volatility, the anchor range of atr_risk
    s = vol_a * np.sqrt(20 / 252)
    mkt = rng.normal(0, 0.05)
    r = np.exp(rng.normal(-s**2 / 2, s)) - 1 + mkt * (0.5 + vol_a)   # E[r] identical apart from beta*mkt (mean zero)
    score = -vol_a
    ics.append(sp(score, r))
    q = np.argsort(score); f = np.array_split(q, 5)
    spreads.append(r[f[4]].mean() - r[f[0]].mean())
ics = np.array(ics); spreads = np.array(spreads)
print("(1) low-vol score, equal expected returns: mean rank IC %.4f, sd %.3f, t over 89 dates %.2f; mean top-bottom fifth %.4f%%" % (
    ics.mean(), ics.std(), ics.mean() / (ics.std() / np.sqrt(89)), spreads.mean() * 100))

# (2) Saturation: how much of a latent ordering survives a clipped ramp
N = 200000
z = rng.normal(size=N)
for name, lo_share, hi_share in (("risk_reward US (76% at 0, 1% at 1)", 0.76, 0.01), ("liquidity US (44% at 1)", 0.0, 0.44),
                                 ("earnings_calendar US (93% at 1)", 0.0, 0.93), ("atr_risk KR (47% at 0)", 0.47, 0.0),
                                 ("trend_structure (7 steps)", None, None)):
    if lo_share is None:
        x = np.digitize(z, np.quantile(z, np.linspace(0, 1, 8)[1:-1])).astype(float)
    else:
        lo, hi = np.quantile(z, lo_share), np.quantile(z, 1 - hi_share) if hi_share else z.max()
        x = np.clip(z, lo, hi)
    idx = rng.choice(N, 20000, replace=False)
    print("(2) %-38s rank correlation with the unclipped ordering %.3f" % (name, sp(x[idx], z[idx])))

# (3) Paired comparison power: two scores with rank correlation rho, daily IC noise sd as implied by the recorded t values
def nw_t(x, lag):
    x = np.asarray(x); n = len(x); m = x.mean(); e = x - m
    v = (e @ e) / n
    for k in range(1, lag + 1):
        v += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return m / np.sqrt(max(v, 1e-18) / n)
def power(rho, d_ic, sd_month, n_days=240, h=20, bar=2.9, sims=4000):
    hit = 0
    sd_diff = sd_month * np.sqrt(2 * (1 - rho))        # sd of a 20-session IC difference
    for _ in range(sims):
        e = rng.normal(0, sd_diff / np.sqrt(h), n_days + h)      # daily shocks; an h-session outcome sums h of them
        c = np.cumsum(e); x = d_ic + (c[h:] - c[:-h])
        hit += nw_t(x, h) >= bar
    return hit / sims
for rho in (0.95, 0.90, 0.78, 0.50):
    row = ["rho %.2f:" % rho]
    for d in (0.01, 0.02, 0.04):
        row.append("dIC %.2f -> US %.0f%% / KR %.0f%%" % (d, 100 * power(rho, d, 0.198), 100 * power(rho, d, 0.100)))
    print("(3)", "  ".join(row))
print("(3) false positive at dIC 0: %.1f%%" % (100 * power(0.9, 0.0, 0.198)))

# ---- (4) 위험 주장과 수익 주장의 검정력
# Random numbers only: how often a 240-session record would tell a calmer top fifth from the whole scan (Pitman-Morgan test
# on daily returns of two correlated baskets), against how often it would tell a return difference of the size the backtest showed.

rng = np.random.default_rng(7)
def trial(ratio, corr, n=240, mean_gap_annual=0.0):
    s_all = 0.143 / np.sqrt(252); s_top = ratio * s_all
    a = rng.standard_t(5, n) / np.sqrt(5 / 3) * s_all
    e = rng.standard_t(5, n) / np.sqrt(5 / 3)
    t = corr * (s_top / s_all) * a + np.sqrt(1 - corr**2) * s_top * e + mean_gap_annual / 252
    u, v = t + a, t - a
    r = np.corrcoef(u, v)[0, 1]
    tv = r * np.sqrt((n - 2) / (1 - r * r))            # negative when the top basket is calmer
    d = t - a
    tm = d.mean() / (d.std(ddof=1) / np.sqrt(n))
    return tv, tm
for ratio in (1.0, 0.95, 0.90, 0.85):
    res = np.array([trial(ratio, 0.94) for _ in range(4000)])
    print("vol ratio %.2f: 'calmer' found (t <= -2.6) in %.0f%% of 240-session records" % (ratio, 100 * (res[:, 0] <= -2.6).mean()))
for gap in (0.0, 0.015, 0.033):
    res = np.array([trial(0.85, 0.94, mean_gap_annual=gap) for _ in range(4000)])
    print("return gap %.1f%%/yr: found (t >= 2.6) in %.0f%% of 240-session records" % (gap * 100, 100 * (res[:, 1] >= 2.6).mean()))
