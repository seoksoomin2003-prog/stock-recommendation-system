"""Agent 06 cross review.  Random numbers only.  Is the +-20% weight-perturbation rank stability a property of the weights alone?
Independent uniform factors, the US swing weights (scored factors), 504 rows, 300 draws: 5th percentile of the rank correlation.
Then the same with positively correlated factors (one common component), to show correlation alone raises stability."""
import sys
from pathlib import Path
import numpy as np
repo = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(repo))
from terminal.qsf import config
p = config.profile_for("US", "SWING")
w = np.array([float(v) for d in p["domains"].values() for v in d.values()])

print("factors", len(w), "weights", w.tolist())
rng = np.random.default_rng(3)
def rk(x): return np.argsort(np.argsort(x)).astype(float)
def sp(a, b): return float(np.corrcoef(rk(a), rk(b))[0, 1])
for label, common in (("independent", 0.0), ("common component 0.6", 0.6)):
    for lo, hi in ((0.8, 1.2), (0.5, 1.5)):
        res = []
        for rep in range(20):
            z = rng.random((504, 1))
            N = (1 - common) * rng.random((504, len(w))) + common * z
            S0 = N @ w
            r = [sp(S0, N @ (w * rng.uniform(lo, hi, len(w)))) for _ in range(300)]
            res.append(np.percentile(r, 5))
        print(f"{label:22s} +-{int((hi-1)*100)}%: rho p5 mean over 20 matrices {np.mean(res):.3f}")
