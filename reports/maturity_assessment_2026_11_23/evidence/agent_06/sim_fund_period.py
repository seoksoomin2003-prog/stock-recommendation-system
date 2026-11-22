"""Agent 06, 2026-11-23.  RANDOM NUMBERS ONLY: made-up stocks, scores and returns.  Nothing of the project's records is read.

1. The Korean fund-period reading as it is read since 2026-11-22 (the day's top fifth of the actionable stocks, both scores,
   equal weight, 20 sessions, difference, Newey-West t with lag 20, calibrated bar, a difference on 120 days or more),
   on stocks whose scores have NO relation to returns.  The program's own functions are used for the arithmetic
   (score_split._band, fund_period.summarize / verdict).  How often does the reading say TRAILING_BETTER and switch the input?
2. How large a true advantage it takes to pass.
3. Power of the four primary live verdicts at the calibrated bars (t bar, mean IC 0.02, both halves positive only).
"""
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf import calibrate, fund_period, validate  # noqa: E402
from terminal.qsf.score_split import _band                 # noqa: E402

N, DAYS, H, COST = 300, 240, 20, 0.0053


def world(rng, market_drift=0.0, edge=0.0, fat=True):
    """One made-up year.  ``edge``: extra daily return of a stock per point its trailing score stands above its annual score."""
    T = DAYS + H + 1
    own = (rng.standard_t(5, size=(T, N)) / np.sqrt(5 / 3) if fat else rng.standard_normal((T, N))) * 0.022
    r = own + rng.standard_normal((T, 1)) * 0.011 + market_drift / 250.0
    annual = 50 + 8 * rng.standard_normal(N)
    delta = np.where(rng.random(N) < 0.6, 3.0 * rng.standard_normal(N), 0.0)          # 60% have a newer quarter; the rest: one figure for both
    able = rng.random(N) < 0.7
    path = []
    for d in range(T):                                                                 # scores first, so that an edge can be put into every later day's return
        fresh = rng.random(N) < 1 / 60.0                                               # a new filing: the trailing side is drawn again
        delta = np.where(fresh, np.where(rng.random(N) < 0.6, 3.0 * rng.standard_normal(N), 0.0), delta)
        annual = annual + 0.3 * rng.standard_normal(N)                                 # prices move the score a little every day
        able = np.where(rng.random(N) < 0.02, ~able, able)
        path.append((annual, delta, able))
        if edge and d + 1 < T:
            r[d + 1] += edge * delta                                                   # tomorrow's return leans on today's score difference
    logp = np.cumsum(np.log1p(r), axis=0)
    days = []
    for d in range(DAYS):
        annual, delta, able = path[d]
        ret = np.expm1(logp[d + H] - logp[d])                                          # close of d to close of d + 20 (the open is not modelled)
        a, t = _band(annual, able, ret, COST, True), _band(annual + delta, able, ret, COST, True)
        days.append({"session": f"{d:03d}", "annual": a, "trailing": t, "diff": t["ret"] - a["ret"], "ic_annual": None, "ic_trailing": None, "late": False})
    return days


def run(label, sims, seed, **kw):
    rng = np.random.default_rng(seed)
    ts, verdicts, diffdays, sd = [], [], [], []
    for _ in range(sims):
        s = fund_period.summarize(world(rng, **kw), H)
        ts.append(s["difference"]["t"])
        verdicts.append(fund_period.verdict(s["difference"]))
        diffdays.append(s["difference"]["days_with_difference"])
        sd.append(np.std([0]))
    ts = np.array(ts, dtype=float)
    bar = calibrate.bar(fund_period.MIN_T, DAYS, H, 1, H)
    print(f"{label:46s} sims {sims}: TRAILING_BETTER {np.mean([v == 'TRAILING_BETTER' for v in verdicts]) * 100:.2f}%  ANNUAL_BETTER {np.mean([v == 'ANNUAL_BETTER' for v in verdicts]) * 100:.2f}%  "
          f"t>=2 {np.mean(ts >= 2) * 100:.1f}%  t>=3 {np.mean(ts >= 3) * 100:.2f}%  t>=bar({bar}) {np.mean(ts >= bar) * 100:.2f}%  t sd {ts.std():.2f}  99% point {np.quantile(ts, 0.99):.2f}  "
          f"days with a difference: median {int(np.median(diffdays))}")
    return ts


if __name__ == "__main__":
    print("1. Korean fund-period reading (top fifth), scores unrelated to returns")
    run("flat market, fat-tailed stocks", 1500, 11)
    run("market falling 30% a year", 800, 12, market_drift=-0.30)
    run("market rising 30% a year", 800, 13, market_drift=0.30)
    print()
    print("2. what it takes to pass: a true edge per score point of difference (bp a day)")
    for edge in (0.5e-4, 1e-4, 2e-4):
        rng = np.random.default_rng(int(edge * 1e6))
        got, gain = [], []
        for _ in range(250):
            days = world(rng, edge=edge)
            s = fund_period.summarize(days, H)
            got.append(fund_period.verdict(s["difference"]) == "TRAILING_BETTER")
            gain.append(s["difference"]["mean"])
        print(f"  edge {edge * 1e4:.1f} bp/day/point: mean 20-session advantage of the trailing top fifth {np.mean(gain) * 100:+.2f}% (about {np.mean(gain) * 12.5 * 100:+.1f}% a year), passes {np.mean(got) * 100:.0f}%")
    print()
    print("3. power of the four primary verdicts at the calibrated bars (date-to-date sd of IC from reports/QSF_LIVE_FORWARD_POWER_2026_11_11.md)")
    rng = np.random.default_rng(3)
    for name, n, h, sd in (("KR swing", 240, 20, 0.138), ("US swing", 240, 20, 0.197), ("KR long", 756, 63, 0.107), ("US long", 756, 63, 0.140)):
        bar = calibrate.bar(validate.MIN_T, n, h, 1, h)
        sims = 6000 if n < 500 else 2500
        raw = rng.standard_normal((sims, n + h - 1))
        c = np.cumsum(raw, axis=1)
        noise = (c[:, h - 1:] - np.concatenate([np.zeros((sims, 1)), c[:, :-h]], axis=1)) / np.sqrt(h) * sd
        out = []
        for ic in (0.0, 0.03, 0.05, 0.10, 0.15):
            x = noise + ic
            t = calibrate.t_many(x, h)
            half = n // 2
            ok = (t >= bar) & (x.mean(axis=1) >= 0.02) & (x[:, :half].mean(axis=1) > 0) & (x[:, half:].mean(axis=1) > 0)
            out.append(f"IC {ic:.2f}: {ok.mean() * 100:5.1f}%")
        print(f"  {name}: bar {bar}  " + "  ".join(out))
