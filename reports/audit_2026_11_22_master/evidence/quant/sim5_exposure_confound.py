"""SIM 5: exposure confound in the 'band return with 0 when empty' and 'two paper books' comparisons.  No selection skill anywhere.

(a) fund_period / score_split design (score_split.py:108-111 `_band` returns 0.0 on an empty band; fund_period.py:154-155,168):
    the market's daily return is i.i.d. N(m/252, (0.16)^2/252); every held stock earns the market (zero skill).  Arm T holds on every day;
    arm A is empty on a share `gap` of days, in runs of 20 sessions.  Daily value = 20-session forward return of what is held
    (minus the same cost on both when held), diff = T - A.  n = 240 days, Newey-West lag 20.  Pass = mean>0 & t>=3.0 & differing days>=120
    (fund_period) or t>=2.0 (score_split).  10,000 simulations per row.
(b) rank_book / turnover_book design (daily returns of two books, lag 20): book R holds a constant fraction less than book B (fewer entries),
    diff = -(d) * market daily return.  ADOPT(rank) = mean>0 & t>=2.0;  ADOPT(turnover) needs only mean>=0 once it is cheaper.
"""
import json, math
import numpy as np
from simlib import nw_t, selfcheck
selfcheck()
rng = np.random.default_rng(20261126)
SIMS, N, H = 10000, 240, 20
P = lambda x: round(float(np.mean(x)) * 100, 2)
print("## (a)")
for gap in (0.25, 0.5, 0.75):
    for m in (-0.20, 0.0, 0.10, 0.20, 0.30):
        r = m / 252 + 0.16 / math.sqrt(252) * rng.standard_normal((SIMS, N + H + 1))
        c = np.concatenate([np.zeros((SIMS, 1)), r.cumsum(axis=1)], axis=1)
        fwd = c[:, H + 1:H + 1 + N] - c[:, 1:N + 1]
        empty = np.zeros((SIMS, N), dtype=bool)
        blocks = N // 20
        k = int(round(gap * blocks))
        for s in range(SIMS):
            for b in rng.choice(blocks, size=k, replace=False):
                empty[s, b * 20:(b + 1) * 20] = True
        diff = np.where(empty, fwd, 0.0)             # T holds the market, A holds nothing on its empty days; equal on the others
        t = nw_t(diff, H); mean = diff.mean(axis=1); days = (diff != 0).sum(axis=1)
        print(json.dumps({"arm_A_empty_share": gap, "market_annual_drift": m, "P(TRAILING_BETTER: t>=3 & >=120 days)": P((t >= 3.0) & (mean > 0) & (days >= 120)),
                          "P(t>=3) without the day rule": P((t >= 3.0) & (mean > 0)), "P(SPLIT-style: t>=2.0)": P((t >= 2.0) & (mean > 0)), "P(t<=-2.0)": P(t <= -2.0)}))
print("## (b)")
for m in (-0.30, -0.15, 0.0, 0.15, 0.30):
    idx = m / 252 + 0.16 / math.sqrt(252) * rng.standard_normal((SIMS, N))
    d = -0.2 * idx                                   # the rule book is 20 points less invested, no other difference
    t = nw_t(d, 20)
    print(json.dumps({"market_annual_drift": m, "P(rank ADOPT: mean>0 & t>=2.0)": P((t >= 2.0) & (d.mean(axis=1) > 0)), "P(turnover ADOPT if cheaper: mean>=0)": P(d.mean(axis=1) >= 0)}))
