# Random numbers only. No prices, no ledger, no records.
import numpy as np
from statistics import NormalDist
rng = np.random.default_rng(20261125)
N = 200_000
nd = NormalDist()

# (1) family of reference readings: K null readings, each "notable" with marginal rate p (one or both sides),
#     sharing a common factor (same year, same stocks) with correlation rho.
def any_notable(K, p, rho, two_sided):
    z = np.sqrt(rho) * rng.standard_normal((N, 1)) + np.sqrt(1 - rho) * rng.standard_normal((N, K))
    if two_sided:
        c = nd.inv_cdf(1 - p / 2); hit = np.abs(z) > c
    else:
        c = nd.inv_cdf(1 - p); hit = z > c
    return hit.any(axis=1).mean(), hit.sum(axis=1).mean()

print("reference readings with a verdict: K=26 (36 minus 4 primary, minus 2 turnover books, minus 4 figures-only)")
for p, two in ((0.0125, False), (0.023, False), (0.046, True)):
    for rho in (0.0, 0.3, 0.6):
        a, m = any_notable(26, p, rho, two)
        print(f"  per-reading chance {p:.4f} {'two-sided' if two else 'one-sided'} rho={rho}: P(at least one notable)={a:.3f}, mean count={m:.2f}")

# (2) turnover book: protocol says its adopt condition is met ~50% of the time with no effect; two markets
print("turnover book, two markets, 50% each, independent:", 1 - 0.5 ** 2)

# (3) what the primary swing verdict can tell: Bayes with the pass rates recorded in RECHECK_AGENT_06 section 3.3
#     noise: 1.2-1.4% pass; IC 0.05: 8.5-9%; IC 0.10: ~52%
for prior in (0.1, 0.2, 0.4):
    for name, pw in (("IC0.05", 0.09), ("IC0.10", 0.52)):
        a = 0.013
        post_pass = prior * pw / (prior * pw + (1 - prior) * a)
        post_fail = prior * (1 - pw) / (prior * (1 - pw) + (1 - prior) * (1 - a))
        print(f"  prior {prior:.0%} that true effect is {name}: after PASS {post_pass:.0%}, after NO_EVIDENCE {post_fail:.0%}, P(NO_EVIDENCE)={(prior*(1-pw)+(1-prior)*(1-a)):.0%}")

# (4) winner's curse: pick the best of K null challengers by its 1-year t, then look at the next independent year
K = 14
z1 = rng.standard_normal((N, K)); z2 = rng.standard_normal((N, K))
best = z1.argmax(axis=1)
print("best of 14 null challengers: mean first-year z", z1.max(axis=1).mean().round(2), " next-year z of the same one", z2[np.arange(N), best].mean().round(3),
      " P(best z > 2.0) =", (z1.max(axis=1) > 2.0).mean().round(3))

# (5) minimal alternative: one pooled reading. Two markets' primary swing t pooled (t_us + t_kr)/sqrt(2) at the same calibrated bar,
#     vs "either market passes".  Normal approximation; per-market noncentrality d.
bar = 3.3   # calibrated bar cited in the forward protocol (table value 2.24)
sd = bar / nd.inv_cdf(1 - 0.0125)          # scale so that the null pass rate is 1.25% at the calibrated bar
for d in (0.0, 1.0, 1.5, 2.0, 3.0):
    t = d * sd + sd * rng.standard_normal((N, 2))
    either = (t > bar).any(axis=1).mean(); pooled = (t.sum(axis=1) / np.sqrt(2) > bar).mean()
    print(f"  per-market effect {d:.1f} sd: P(either market passes t bar)={either:.3f}  P(pooled passes)={pooled:.3f}")
