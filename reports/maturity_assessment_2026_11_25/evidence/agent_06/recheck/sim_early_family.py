"""Agent 06 re-check.  Random numbers only.  The t condition alone (upper bound for chance passes; the other conditions only
remove passes).  Daily noise u feeds both the 5-session values (early looks: first 60 and first 120, bars from calibrate.bar at
nominal 2.5) and the 20-session values (primary: 240, bar at nominal 2.24), as the same days would in the ledger."""
import sys, math
from pathlib import Path
import numpy as np
repo = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(repo))
from terminal.qsf import calibrate as c
from terminal.qsf import live_forward as lf, validate
b60, b120, bp = c.bar(lf.EARLY_T, 60, 5, 1, 5), c.bar(lf.EARLY_T, 120, 5, 1, 5), c.bar(validate.MIN_T, 240, 20, 1, 20)
print("bars", b60, b120, bp)
rng = np.random.default_rng(11)
S = 100000
hits = {"60": 0, "120": 0, "either": 0, "primary": 0, "against_either": 0, "early_and_primary": 0}
done = 0
while done < S:
    k = 5000
    u = rng.standard_normal((k, 262))
    cs = np.concatenate([np.zeros((k, 1)), np.cumsum(u, axis=1)], axis=1)
    v5 = (cs[:, 6:6 + 120] - cs[:, 1:1 + 120]) / math.sqrt(5)
    v20 = (cs[:, 21:21 + 240] - cs[:, 1:1 + 240]) / math.sqrt(20)
    t60, t120, tp = c.t_many(v5[:, :60], 5), c.t_many(v5, 5), c.t_many(v20, 20)
    a, b, p = t60 >= b60, t120 >= b120, tp >= bp
    hits["60"] += a.sum(); hits["120"] += b.sum(); hits["either"] += (a | b).sum(); hits["primary"] += p.sum()
    hits["against_either"] += ((t60 <= -b60) | (t120 <= -b120)).sum(); hits["early_and_primary"] += ((a | b) & p).sum()
    done += k
r = {kk: v / S for kk, v in hits.items()}
print({kk: f"{v:.3%}" for kk, v in r.items()})
e = r["either"]
print(f"two markets, four looks (markets independent): any early pass by chance {1 - (1 - e) ** 2:.3%}; any early AGAINST by chance {1 - (1 - r['against_either']) ** 2:.3%}")
print(f"one primary verdict {r['primary']:.3%}; P(primary passes | an early look passed) under noise {r['early_and_primary'] / max(e, 1e-12):.1%}")
