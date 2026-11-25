"""Agent 06 re-check (2026-11-25).  Random numbers only: the pre-registered early readings (live_forward.EARLY, EARLY_T) and
the primary swing verdict, run through the program's own day statistics (validate.per_date), summary (live_forward.summarize),
conditions (live_forward.reading) and bars (calibrate.bar).  No price, record or return of any real stock is read.

World (second run): a daily style return G*x (G sd 0.0034) added so that the IC of separate 20-session dates has an sd near the
recorded 0.14-0.19; without it (first run, *_noStyle_out.txt) the IC is far steadier than recorded and power is overstated.
N stocks, a persistent latent score x (AR(1), phi 0.98: a one-day rank correlation near 0.98 as recorded for US swing),
shown score = 52 + 12x (about 5% at 70+), daily return = market + idiosyncratic (2%) + k * x of the day before.  k sets the
true effect; the realised mean IC at 5 and 20 sessions is printed from the simulation itself.  Index = the market part.
Costs as config.round_trip_cost.  US design (band of 70) and KR design (top fifth)."""
import sys, time
from pathlib import Path
import numpy as np
repo = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(repo))
from terminal.qsf import calibrate, config, live_forward as lf, validate

N, PHI = int(sys.argv[2]) if len(sys.argv) > 2 else 300, 0.98
T = 240 + 20 + 2

G = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0034   # daily return of the score's style (makes the daily IC swing like recorded IC: sd ~0.14-0.19)

def path(rng, k):
    x = np.empty((T, N)); x[0] = rng.standard_normal(N)
    for t in range(1, T):
        x[t] = PHI * x[t - 1] + np.sqrt(1 - PHI ** 2) * rng.standard_normal(N)
    m = rng.normal(0.0003, 0.01, T)
    r = m[:, None] + rng.normal(0, 0.02, (T, N))
    r[1:] += (k + rng.normal(0, G, T - 1))[:, None] * x[:-1]
    return x, r, m

def days(x, r, m, n, h, cost, top):
    rows = []
    c = np.vstack([np.zeros((1, N)), np.cumsum(r, axis=0)])
    cm = np.concatenate([[0.0], np.cumsum(m)])
    for d in range(n):
        ret = c[d + 1 + h] - c[d + 1]          # held from the next session for h sessions
        net = ret - cost
        sc = 52 + 12 * x[d]
        out = validate.per_date(sc, net, cost)
        if not out or out.get("ic") is None:
            continue
        idx = cm[d + 1 + h] - cm[d + 1]
        q = validate.rank(sc) / (len(sc) - 1)
        buy, tp = net[sc >= validate.BUY_SCORE], net[q >= 0.8]
        out.update(date=f"{d:04d}", universe_net=float(net.mean()), index=float(idx), universe_effect=float(net.mean() - idx), buy_index=None, top_index=None,
                   buy_net=float(buy.mean()) if len(buy) else None, top_net=float(tp.mean()) if len(tp) else None, versions=["sim"])
        rows.append(out)
    return rows

def judge(rows, h, nominal, top):
    s = lf.summarize(rows, h)
    s["t_bar"] = calibrate.bar(nominal, len(rows), h, 1, h)
    r = lf.reading(s, top)
    return s, r

def run(market, k, sims, rng):
    top = (market, "SWING") in lf.TOP_BAND
    cost = config.round_trip_cost(market)
    agg = {"e60": 0, "e120": 0, "e_any": 0, "e60_rank": 0, "e120_rank": 0, "against": 0, "p": 0, "p_rank": 0, "both": 0, "early_any_and_p": 0}
    cond60 = {}
    ic5, ic20, sd20 = [], [], []
    for _ in range(sims):
        x, r, m = path(rng, k)
        res = {}
        for n in (60, 120):
            rows = days(x, r, m, n, 5, cost, top)
            s, rd = judge(rows, 5, lf.EARLY_T, top)
            res[n] = rd["verdict"]
            agg[f"e{n}_rank"] += rd["verdict"] in ("RANK_ONLY", "WEAK_POSITIVE_EVIDENCE")
            agg[f"e{n}"] += rd["verdict"] == "WEAK_POSITIVE_EVIDENCE"
            agg["against"] += s["t"] is not None and s["t"] <= -s["t_bar"]
            if n == 60:
                ic5.append(s["ic"])
                for kk, v in {**rd["condition_a"], "money": rd["condition_b"]}.items():
                    cond60[kk] = cond60.get(kk, 0) + bool(v)
        rows = days(x, r, m, 240, 20, cost, top)
        s, rd = judge(rows, 20, validate.MIN_T, top)
        ic20.append(s["ic"]); sd20.append(np.std([d["ic"] for d in rows[::20]], ddof=1))
        p = rd["verdict"] == "WEAK_POSITIVE_EVIDENCE"
        agg["p"] += p; agg["p_rank"] += rd["verdict"] in ("RANK_ONLY", "WEAK_POSITIVE_EVIDENCE")
        e_any = "WEAK_POSITIVE_EVIDENCE" in res.values()
        agg["e_any"] += e_any; agg["early_any_and_p"] += e_any and p
    f = lambda v: f"{v / sims:6.1%}"
    print(f"{market} k={k:.5f} sims={sims}: mean IC 5d {np.mean(ic5):+.3f}, 20d {np.mean(ic20):+.3f} (sd of separate 20d IC {np.mean(sd20):.3f}) | early60 pass {f(agg['e60'])} rank-only-or-better {f(agg['e60_rank'])} | "
          f"early120 pass {f(agg['e120'])} rank {f(agg['e120_rank'])} | either early pass {f(agg['e_any'])} | AGAINST (any look) {f(agg['against'])} | "
          f"primary pass {f(agg['p'])} rank {f(agg['p_rank'])} | P(primary pass | early pass) {agg['early_any_and_p'] / max(1, agg['e_any']):.0%} (n={agg['e_any']})")
    print("      early60 single conditions met:", {kk: f"{v / sims:.0%}" for kk, v in cond60.items()})

if __name__ == "__main__":
    market = sys.argv[1]
    rng = np.random.default_rng(20261125)
    for k, sims in ((0.0, int(sys.argv[3]) if len(sys.argv) > 3 else 300), (0.0003, 200), (0.0006, 200), (0.0010, 200)):
        t0 = time.time(); run(market, k, sims, rng); print(f"      ({time.time() - t0:.0f} s)", flush=True)
