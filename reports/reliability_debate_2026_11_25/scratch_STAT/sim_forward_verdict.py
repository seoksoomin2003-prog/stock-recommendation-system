"""STAT seat, random numbers only.  What the pre-registered live verdict (240 sessions, 20-session outcomes) and the two early
readings (60 and 120 sessions, 5-session outcomes) can tell, with ALL their conditions, on made-up markets.

Made-up market: N stocks, daily returns = market + risk-trait factor + size factor + (true signal) + own noise.  The index is
weighted by size; the scanned universe is counted at equal weight, as the verdict does.  The score = part risk trait + part a
slowly changing signal.  Sizes of the made-up pieces are set so that two published figures are matched and nothing else is fitted:
  - the day-to-day scatter of the 20-session IC: KR 0.138, US 0.197 (reports/QSF_LIVE_FORWARD_POWER_2026_11_11.md)
  - the scatter of (equal-weight universe - index) per 21 sessions: US 1.8%, KR 3.7% (BT-1 files: ALL_SCORED excess / its t * sqrt(periods))
The conditions are the code's (terminal/qsf/live_forward.py, validate.verdict): IC >= 0.02, NW t >= calibrated bar, IC > 0 in both
halves, top-bottom spread after one round trip > 0 in both halves, band above universe; money: band above the index in both halves.
Band: KR the day's top fifth (as registered); US the top 12% of the day (BT-1: 57 of 463 names at 70 or more).
No price, return or record is read.
"""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from terminal.qsf import calibrate as cal

MARKETS = {"KR": dict(N=280, sd=0.022, f=0.0072, g=0.0053, cap=1.6, cost=0.0053, band=0.20, drift=0.0049),
           "US": dict(N=460, sd=0.016, f=0.0088, g=0.0024, cap=1.5, cost=0.00402, band=0.124, drift=0.00157)}
C, PHI, T, H = 0.5, 0.98, 240, 20
BAR = cal.bar(2.24, T, H, 1, H)
EARLY = {60: cal.bar(2.75, 60, 5, 1, 5), 120: cal.bar(2.75, 120, 5, 1, 5)}


def rank(a):
    return np.argsort(np.argsort(a, axis=-1), axis=-1).astype(float)


def nw_t(x, lag):
    return float(cal.t_many(np.asarray(x)[None, :], lag)[0])


def world(rng, p, a):
    """Scores (days x N), daily stock returns, daily index returns."""
    n, days = p["N"], T + H + 1
    b, z = rng.standard_normal(n), rng.standard_normal(n)
    w = np.exp(p["cap"] * z); w /= w.sum()
    u = np.empty((days, n)); u[0] = rng.standard_normal(n)
    e = rng.standard_normal((days, n)) * np.sqrt(1 - PHI ** 2)
    for d in range(1, days):
        u[d] = PHI * u[d - 1] + e[d]
    score = C * b + np.sqrt(1 - C ** 2) * u
    r = (rng.standard_normal((days, 1)) * 0.01 + rng.standard_normal((days, 1)) * p["f"] * b + rng.standard_normal((days, 1)) * p["g"] * z
         + a * p["sd"] * u + p["sd"] * rng.standard_normal((days, n)))
    return score, r, r @ w


def stats(score, r, index, p, h, days):
    """Per-day figures of the first ``days`` sessions with an h-session outcome from the next session."""
    c = np.vstack([np.zeros((1, r.shape[1])), np.cumsum(r, 0)]); ci = np.concatenate([[0.0], np.cumsum(index)])
    fwd = c[1 + h:1 + h + days] - c[1:1 + days]                      # sessions d+1 .. d+h
    idx = ci[1 + h:1 + h + days] - ci[1:1 + days]
    s = score[:days]
    net = fwd - p["cost"]
    ex = net - net.mean(1, keepdims=True)
    rs, rr = rank(s), rank(ex)
    rs0, rr0 = rs - rs.mean(1, keepdims=True), rr - rr.mean(1, keepdims=True)
    ic = (rs0 * rr0).sum(1) / np.sqrt((rs0 ** 2).sum(1) * (rr0 ** 2).sum(1))
    q = rs / (s.shape[1] - 1)
    top, bot, band = q >= 0.8, q <= 0.2, q >= 1 - p["band"]
    m = lambda mask, x: (x * mask).sum(1) / mask.sum(1)              # noqa: E731
    return dict(ic=ic, spread=m(top, ex) - m(bot, ex) - p["cost"], band_ex=m(band, ex), band_net=m(band, net), uni=net.mean(1), idx=idx)


def read(st, bar, lag, drift_per_session, h):
    n = len(st["ic"]); half = n // 2
    t = nw_t(st["ic"], lag)
    a = (st["ic"].mean() >= 0.02 and t >= bar and st["ic"][:half].mean() > 0 and st["ic"][half:].mean() > 0
         and st["spread"][:half].mean() > 0 and st["spread"][half:].mean() > 0 and st["band_ex"].mean() > 0)
    vs_index = st["band_net"] - (st["idx"] + drift_per_session * h)   # drift: the index's extra return over the equal-weight universe
    b = vs_index[:half].mean() > 0 and vs_index[half:].mean() > 0
    b_score = st["band_ex"][:half].mean() > 0 and st["band_ex"][half:].mean() > 0
    return dict(t=t, a=a, b=b, b_score=b_score, t_score=nw_t(st["band_ex"], lag), against=t <= -bar)


def calibrate_a(rng, p, target):
    if target == 0:
        return 0.0
    q = dict(p, f=0.0, g=0.0)                                        # pilots without the two common factors: the mean IC is found with far less noise
    got = np.mean([stats(*world(rng, q, 0.02), q, H, T)["ic"].mean() for _ in range(40)])
    return 0.02 * target / got


def main(sims=500):
    rng = np.random.default_rng(20261125)
    print(f"primary bar {BAR}, early bars {EARLY}; {sims} made-up years per line")
    for mk, p in MARKETS.items():
        print(f"\n== {mk}: {p['N']} stocks, band = top {p['band']:.0%}, round trip {p['cost']:.2%}")
        for target in (0.0, 0.03, 0.05, 0.10, -0.05):
            a = calibrate_a(rng, p, abs(target)) * (1 if target >= 0 else -1)
            rows, early, check = [], {60: [], 120: []}, []
            for _ in range(sims):
                score, r, index = world(rng, p, a)
                st = stats(score, r, index, p, H, T)
                flat, lag_ = read(st, BAR, H, 0.0, H), read(st, BAR, H, p["drift"] / 21, H)
                rows.append((st["ic"].mean(), st["ic"].std(), flat["a"], flat["b"], lag_["b"], flat["b_score"], flat["t_score"] >= BAR, flat["a"] and flat["b"], flat["a"] and lag_["b"],
                             (st["band_net"] - st["idx"]).mean(), st["band_ex"].mean()))
                check.append(np.std((st["uni"] - st["idx"])[::H]))
                s5 = {n: stats(score, r, index, p, 5, n) for n in (60, 120)}
                for n in (60, 120):
                    e = read(s5[n], EARLY[n], 5, 0.0, 5)
                    early[n].append((s5[n]["ic"].mean(), e["a"], e["against"], e["t"] >= EARLY[n]))
            x = np.array(rows, dtype=float).mean(0)
            print(f"true 20-session IC {x[0]:+.3f} (day scatter {x[1]:.3f}; universe-index scatter per 20 sessions {np.mean(check) * 100:.1f}%) | "
                  f"rank conditions A {x[2]:.1%} | money B {x[3]:.1%} (index ahead as in BT-1: {x[4]:.1%}) | A and B {x[7]:.1%} ({x[8]:.1%}) | "
                  f"band above universe in both halves {x[5]:.1%} | t of (band - universe) over the bar {x[6]:.1%} | band-index {x[9] * 100:+.2f}%, band-universe {x[10] * 100:+.2f}% per 20 sessions")
            for n in (60, 120):
                y = np.array(early[n], dtype=float).mean(0)
                print(f"      early {n}: 5-session IC {y[0]:+.3f} | t over the bar {y[3]:.1%} | all rank conditions {y[1]:.1%} | EARLY_AGAINST {y[2]:.1%}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 500)
