"""AGENT 6 cross-review of AGENT 3. Part A reads recorded scores and domain points only (no price, no return).
Parts B and C use random numbers only."""
import sys, math
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf.ledger import Ledger

print("A. US SWING: share of score variance by domain, each session recorded under QSF-1.4.1, and a bootstrap over stocks for 2026-11-20")
led = Ledger(REPO)
rng = np.random.default_rng(3)
for r in [x for x in led._live_rows() if x["market"] == "US" and x.get("model_version") == "QSF-1.4.1"]:
    rows = [s for s in led._load(r) if s["strategy"] == "SWING" and s.get("score") is not None and s["ticker"] != "SPY"]
    doms = [d for d in rows[0]["domains"] if not rows[0]["domains"][d].get("reference")]
    score = np.array([s["score"] for s in rows], dtype=float)
    pts = np.array([[(s["domains"].get(d) or {}).get("points") or 0.0 for d in doms] for s in rows], dtype=float)
    tot = pts.sum(axis=1)
    ok = tot > 0
    score, pts, tot = score[ok], pts[ok], tot[ok]
    part = pts * (score / tot)[:, None]                      # each domain's part of the score; the parts add up to the score
    def shares(idx):
        sc = score[idx]; v = sc.var()
        return [float(np.cov(part[idx, j], sc, bias=True)[0, 1] / v) for j in range(len(doms))]
    base = shares(np.arange(len(score)))
    line = f"  {r['session']} n={len(score)} sd={score.std():.1f} | " + ", ".join(f"{d} {x*100:.1f}%" for d, x in zip(doms, base))
    if r["session"] == "2026-11-20":
        bs = np.array([shares(rng.integers(0, len(score), len(score))) for _ in range(1000)])
        line += " | bootstrap 95%: " + ", ".join(f"{d} {np.percentile(bs[:, j], 2.5)*100:.1f}~{np.percentile(bs[:, j], 97.5)*100:.1f}%" for j, d in enumerate(doms))
    print(line)

print("B. A score with NO information: 16 independent random factors in [0,1], weights of the US swing size; ranks under weights moved +-20%")
w = np.array([10, 10, 5, 10, 5, 3, 2, 3, 2, 6, 5, 5, 4, 4, 3, 3], dtype=float)
def rk(x):
    return np.argsort(np.argsort(x))
rho = []
for _ in range(300):
    f = rng.random((503, 16))
    s0 = f @ w
    s1 = f @ (w * rng.uniform(0.8, 1.2, 16))
    rho.append(np.corrcoef(rk(s0), rk(s1))[0, 1])
print(f"  rank correlation: 5th percentile {np.percentile(rho, 5):.3f}, median {np.median(rho):.3f}  (a meaningless score is as 'robust')")

print("C. Scores that are pure noise around fixed levels: label changes at 70 with and without the 70/67 buffer, 5 sessions, 503 stocks")
print("   level ~ N(50.9, 11.3); daily move heavy-tailed with median |move| about 1.2 points (the sizes AGENT 3 reports for US swing)")
out, band = [], []
for _ in range(400):
    level = rng.normal(50.9, 11.3, 503)
    x = [level + rng.standard_t(3, 503) * 1.1]
    for _ in range(4):
        x.append(0.6 * (x[-1] - level) + level + rng.standard_t(3, 503) * 1.25)
    x = np.array(x)
    plain = int((np.diff((x >= 70).astype(int), axis=0) != 0).sum())
    state = x[0] >= 70; flips = 0
    for d in range(1, 5):
        new = np.where(state, x[d] >= 67, x[d] >= 70)
        flips += int((new != state).sum()); state = new
    out.append((plain, flips))
    b = np.digitize(x, [40, 55, 70, 80])
    band.append([(b[d] != b[d - 1]).mean() for d in range(1, 5)])
out, band = np.array(out), np.array(band)
print(f"  median |daily move| {np.median(np.abs(np.diff(x, axis=0))):.2f}; label changes plain {np.median(out[:,0]):.0f} -> buffered {np.median(out[:,1]):.0f} (cut {100*(1-out[:,1].sum()/out[:,0].sum()):.0f}%)")
print(f"  share of stocks changing band per day: mean {band.mean()*100:.1f}%, one 4-day week ranges 5th~95th percentile {np.percentile(band, 5)*100:.1f}~{np.percentile(band, 95)*100:.1f}%")
