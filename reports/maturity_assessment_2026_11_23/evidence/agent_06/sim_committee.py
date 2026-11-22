"""Agent 06, 2026-11-23.  RANDOM NUMBERS ONLY (made-up prices): no ledger, no forward record, no real price is read.

The paper arithmetic of terminal/committee/record.performance under the one-day lag, with weights that drift with prices.

A made-up portfolio is decided once (after the close of session 0) and never traded again.  Its recorded weights follow prices
exactly as portfolios.py records them (portfolios.drift from one record to the next).  The program's own performance() is run on
that record and compared with what the stated convention means: bought at the close of session 1 at the recorded weights of
session 0, then simply held (no trade, so no cost after the first purchase).
"""
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.committee import portfolios, record  # noqa: E402  (pure functions; nothing is read or written)

N, T, COST = 10, 244, 0.002          # ten holdings, 242 records + margin, one-way cost 0.2%
KEY = "COMMITTEE"


def paths(rng, rho, sigma=0.022, market=0.011):
    """Daily returns: a market part plus each stock's own part, whose own part carries over with ``rho`` (negative: next-day reversal)."""
    own = rng.standard_normal((T, N)) * sigma
    for d in range(1, T):
        own[d] += rho * own[d - 1]
    r = own + rng.standard_normal((T, 1)) * market
    return np.vstack([np.ones(N) * 100.0, 100.0 * np.cumprod(1.0 + r, axis=0)])        # prices of sessions 0..T


def one(rng, rho, trade_day=None):
    px = paths(rng, rho)
    names = [f"S{j}" for j in range(N)]
    sessions = [f"D{d:03d}" for d in range(T + 1)]
    at = {s: d for d, s in enumerate(sessions)}
    price = lambda t, s: float(px[at[s], int(t[1:])])          # noqa: E731
    w = {t: 0.08 for t in names}                               # 80% invested, 20% cash
    rows = []
    for d, s in enumerate(sessions):
        if d:
            w = portfolios.drift(w, lambda t, a=d - 1, b=d: px[b, int(t[1:])] / px[a, int(t[1:])] - 1.0)
        if trade_day is not None and d == trade_day:           # a decision: S0 is sold whole and the proceeds stay in cash
            w = {t: v for t, v in w.items() if t != "S0"}
        rows.append({"session": s, "portfolios": {KEY: {"cash": round(1.0 - sum(w.values()), 4), "holdings": dict(w)}}})
    rows = rows[:242]
    perf = record.performance(rows, price, lambda s: 100.0, COST, keep_daily=True)["portfolios"][KEY]
    daily = np.array(perf["daily"])
    # the stated convention, held honestly: bought at the close of session 1 at the weights recorded for session 0, never traded
    shares = np.array([0.08 / px[1, j] for j in range(N)])
    cash = 0.20
    value = np.array([cash + float(shares @ px[d]) for d in range(1, 242)])            # closes of sessions 1..241
    true = value[1:] / value[:-1] - 1.0
    true[0] -= 0.80 * COST
    # the trades the program's return series silently assumes: at the close of D+2 the book must hold the weights recorded for D+1
    hidden = []
    for i in range(1, len(rows) - 2):
        before = portfolios.drift(rows[i - 1]["portfolios"][KEY]["holdings"], lambda t, a=i + 0, b=i + 1: px[b, int(t[1:])] / px[a, int(t[1:])] - 1.0)
        after = rows[i]["portfolios"][KEY]["holdings"]
        hidden.append(sum(abs(after.get(t, 0.0) - before.get(t, 0.0)) for t in set(after) | set(before)))
    return {"prog_total": float(np.prod(1 + daily) - 1), "true_total": float(np.prod(1 + true) - 1), "gap_daily": float(np.mean(daily - true)),
            "cost_total": perf["cost_total"], "turnover": perf["turnover_per_day"], "hidden_turnover": float(np.mean(hidden)), "days": len(daily)}


def run(rho, sims=300, seed=1):
    rng = np.random.default_rng([seed, int(abs(rho) * 1000), int(rho < 0)])
    got = [one(rng, rho) for _ in range(sims)]
    gap = np.array([g["gap_daily"] for g in got])
    tot = np.array([g["prog_total"] - g["true_total"] for g in got])
    return {"rho": rho, "days": got[0]["days"], "mean_gap_bp_per_day": gap.mean() * 1e4, "se_bp": gap.std(ddof=1) / np.sqrt(sims) * 1e4,
            "gap_240d_pct": tot.mean() * 100, "gap_240d_se": tot.std(ddof=1) / np.sqrt(sims) * 100, "gap_240d_sd_between_paths": tot.std(ddof=1) * 100,
            "booked_cost_pct": np.mean([g["cost_total"] for g in got]) * 100, "booked_turnover_per_day_pct": np.mean([g["turnover"] for g in got]) * 100,
            "hidden_turnover_per_day_pct": np.mean([g["hidden_turnover"] for g in got]) * 100}


if __name__ == "__main__":
    print("A portfolio decided once and never traded again; 240 paper days; program's performance() against the convention held honestly.")
    print("rho = how much of a stock's own daily move carries into the next day (negative: reversal).")
    for rho in (0.0, -0.05, -0.10, 0.05):
        r = run(rho)
        print(f"rho {rho:+.2f}: program minus honest, per day {r['mean_gap_bp_per_day']:+.3f} bp (se {r['se_bp']:.3f}); over 240 days {r['gap_240d_pct']:+.3f}% (se {r['gap_240d_se']:.3f}, "
              f"sd between paths {r['gap_240d_sd_between_paths']:.2f}%); booked cost {r['booked_cost_pct']:.3f}% (first purchase 0.160%), booked turnover/day {r['booked_turnover_per_day_pct']:.3f}%, "
              f"turnover the return series assumes but does not book {r['hidden_turnover_per_day_pct']:.2f}%/day = {r['hidden_turnover_per_day_pct'] * COST * 240:.2f}% of cost over 240 days")
    rng = np.random.default_rng(77)
    g = one(rng, 0.0, trade_day=100)
    print(f"sanity, one sale of a ~8% holding on day 100: booked cost {g['cost_total'] * 100:.4f}% (first purchase 0.1600% + sale about 0.016%)")
