# portfolio_risk.analyse on RANDOM series (no real prices): do the figures add up?
import numpy as np, math
from datetime import date, timedelta
from terminal import portfolio_risk as pr
rng = np.random.default_rng(7); n = 260
days = [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(n)]
m = rng.normal(0, 0.01, n)
def bars(r): 
    p = 100 * np.cumprod(1 + r); return [{"date": d, "close": float(x)} for d, x in zip(days, p)]
ra, rb = 1.5 * m + rng.normal(0, 0.005, n), 0.5 * m + rng.normal(0, 0.02, n)
out = pr.analyse({"A": 0.3, "B": 0.2}, {"A": bars(ra), "B": bars(rb)}, bars(m), 1000.0)
print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items() if k not in ("holdings", "correlation")})
print("risk shares sum:", round(sum(h["risk_share"] for h in out["holdings"]), 6), [(h["ticker"], round(h["beta"], 2), round(h["risk_share"], 3)) for h in out["holdings"]])
print("beta check (0.3*1.5+0.2*0.5=0.55 expected approx):", round(out["beta"], 3), "| es95 >= var95:", out["es95"] >= out["var95"])
