# Random numbers only: what a 2-ATR stop / 3-ATR target swing trade earns when the score adds NO direction (zero drift),
# and how much drift per trade it would need to pay the round-trip cost.  No prices, no records.
import numpy as np
rng = np.random.default_rng(20261125)
N, T = 200_000, 30                      # trades, sessions to the time stop (config.SWING time_stop = 30)
def run(sigma, cost, edge_per_day=0.0, atr_mult=1.4, stop=2.0, target=3.0):
    atr = atr_mult * sigma              # ASSUMPTION: ATR = 1.4 x daily close-to-close sd
    r = rng.normal(edge_per_day, sigma, size=(N, T))
    path = np.cumsum(r, axis=1)         # log return path, closes only (the program's stops are read on closes)
    hit_s = path <= -stop * atr
    hit_t = path >= target * atr
    first_s = np.where(hit_s.any(1), hit_s.argmax(1), T)
    first_t = np.where(hit_t.any(1), hit_t.argmax(1), T)
    end = np.minimum(np.minimum(first_s, first_t), T - 1)
    gross = path[np.arange(N), end]
    days = end + 1
    return dict(stop=float((first_s < first_t).mean()), target=float((first_t < first_s).mean()), time=float(((first_s == T) & (first_t == T)).mean()),
                gross=float(gross.mean() * 100), net=float((gross.mean() - cost) * 100), days=float(days.mean()), risk_unit=float(stop * atr * 100))
for name, sigma, cost in (("US", 0.0162, 0.00402), ("KR", 0.0245, 0.0053)):
    base = run(sigma, cost)
    print(name, {k: round(v, 3) for k, v in base.items()}, "net in R:", round(base["net"] / base["risk_unit"], 3),
          "trades/yr per slot:", round(252 / base["days"], 1), "cost/yr per always-full slot %:", round(252 / base["days"] * cost * 100, 1))
    for e in (0.0002, 0.0004, 0.0006, 0.0008):
        o = run(sigma, cost, e)
        print("   drift/day %.2f%% -> net/trade %+.3f%%  (stop %.0f%% target %.0f%% time %.0f%%, %.1f days)" % (e * 100, o["net"], o["stop"] * 100, o["target"] * 100, o["time"] * 100, o["days"]))
