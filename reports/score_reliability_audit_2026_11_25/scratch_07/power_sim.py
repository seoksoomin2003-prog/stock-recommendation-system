"""AGENT 7: how much forward record a paired comparison (alternative minus live, daily rank-correlation difference) needs.
RANDOM NUMBERS ONLY.  Assumptions, all stated in the report:
 1. the daily rank correlation (IC) of a score with the h-session return is noisy with standard deviation SIGMA (taken as arithmetic
    on recorded files: sd ~ IC / t * sqrt(dates) of BT-1's primary horizon row; it ignores the Newey-West correction);
 2. the IC noise of two scores is correlated as their ranks are (RHO), so the noise of the difference has sd SIGMA*sqrt(2(1-RHO));
 3. values overlap as daily h-session returns do (calibrate.noise), one value every 5 sessions, Newey-West lag ceil(h/5);
 4. pass = mean > 0, t >= calibrate.bar(2.0, n, h, 5, lag), and both halves positive (the challengers' paired rule).
No price, return or record is read."""
import json, math, sys
import numpy as np
sys.path.insert(0, ".")
from terminal.qsf import calibrate

SIGMA = {"US_SWING": 0.199, "KR_SWING": 0.099, "US_LONG_TERM": 0.142, "KR_LONG_TERM": 0.182}      # (b) arithmetic on BT-1 rows: 20d swing, 63d long
H = {"SWING": 20, "LONG_TERM": 63}
RHO = {"A/C2/B2-like (rho 0.98)": 0.98, "equal weights (rho 0.92)": 0.92, "bundles, long (rho 0.84)": 0.84, "bundles, US swing (rho 0.50)": 0.50}
SIMS = 20000
rng = np.random.default_rng(20261125)
out = {}


def power(delta, sd, n_sessions, h, sims=SIMS):
    step = 5
    n = n_sessions // step
    lag = max(1, math.ceil(h / step))
    bar = calibrate.bar(2.0, n, h, step, lag)
    z = calibrate.noise(rng, sims, n, h, step) / math.sqrt(h)        # unit sd values with the overlap of h-session returns
    x = delta + sd * z
    t = calibrate.t_many(x, lag)
    half = n // 2
    ok = (x.mean(axis=1) > 0) & (t >= bar) & (x[:, :half].mean(axis=1) > 0) & (x[:, half:].mean(axis=1) > 0)
    return float(ok.mean()), bar, n


def plausible(rho, ic_live, ic_other):
    """the IC of alt = rho*live + sqrt(1-rho^2)*other, minus the live IC."""
    return (rho - 1) * ic_live + math.sqrt(1 - rho * rho) * ic_other


for prof, sigma in SIGMA.items():
    h = H["SWING" if "SWING" in prof else "LONG_TERM"]
    base = 240 if h == 20 else 756
    res = {}
    for name, rho in RHO.items():
        sd = sigma * math.sqrt(2 * (1 - rho))
        gap = plausible(rho, 0.03, 0.05)        # generous: the part the alternative adds is as good as IC 0.05, the live score 0.03
        row = {"rho": rho, "sd_of_difference": sd, "generous_true_gap": gap, "power": {}}
        for mult in (1, 2, 4, 8):
            p, bar, n = power(gap, sd, base * mult, h)
            row["power"][str(base * mult)] = {"power": p, "bar": bar, "values": n}
        p0, bar, n = power(0.0, sd, base, h)
        row["false_pass_at_zero_gap"] = p0
        # the true gap that would be found half the time at the registered length
        lo, hi = 0.0, 0.2
        for _ in range(12):
            mid = (lo + hi) / 2
            if power(mid, sd, base, h, 4000)[0] < 0.5:
                lo = mid
            else:
                hi = mid
        row["gap_found_half_the_time_at_registered_length"] = hi
        res[name] = row
    out[prof] = {"sigma_ic": sigma, "h": h, "registered_sessions": base, "by_alternative": res}
    print("==", prof, "sigma", sigma, "h", h, "registered sessions", base)
    for name, r in res.items():
        print(f"  {name:30s} sd(diff) {r['sd_of_difference']:.4f}  generous gap {r['generous_true_gap']:+.4f}  power " +
              "  ".join(f"{k}: {v['power']*100:.0f}% (bar {v['bar']})" for k, v in r["power"].items()) +
              f"  | false pass {r['false_pass_at_zero_gap']*100:.1f}%  | gap needed for 50%: {r['gap_found_half_the_time_at_registered_length']:.3f}")

# several alternatives read at once: the chance that at least one passes with no true gap (paired rule, independent readings assumed)
fam = {}
for k in (1, 4, 7, 14):
    p1 = out["US_SWING"]["by_alternative"]["equal weights (rho 0.92)"]["false_pass_at_zero_gap"]
    fam[k] = 1 - (1 - p1) ** k
out["family"] = fam
print("family-wise false pass (independent readings, US swing design):", {k: round(v, 3) for k, v in fam.items()})
json.dump(out, open("reports/score_reliability_audit_2026_11_25/scratch_07/power_sim.json", "w"), indent=1)
