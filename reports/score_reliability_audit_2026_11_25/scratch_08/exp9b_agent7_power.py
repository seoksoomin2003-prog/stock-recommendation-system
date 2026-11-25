"""Agent 8, second pass on Agent 7's forward power (6-30%).  Random numbers only.  Seed 8810.
A made-up market: 300 stocks, 240 daily cross-sections of overlapping 20-session returns.
  daily return_i = eps_i + m_i * (f_t + 0.03/sqrt(20)) + x_i * (g_t + 0.05/sqrt(20))
  base score = m (true IC 0.03);  alternative = (m + 0.203 x) / norm  (rank link 0.98, true IC about 0.039: difference +0.009)
  f_t: the style return of m, daily sd chosen so the base score's daily IC swings by about 0.10 (Korea swing) or 0.20 (US swing)
  g_t: the style return of the added part x: (i) as volatile as f, (ii) half, (iii) none (the added part is stock-specific)
Agent 7 assumed the two scores' IC noise co-moves by the scores' rank link, i.e. sd(diff) = sd(base IC) * sqrt(2 * (1 - 0.98))."""
import sys, math
import numpy as np
sys.path.insert(0, '.')
from terminal.qsf import calibrate
rng = np.random.default_rng(8810)
N, D, H, LAM = 300, 240, 20, 0.203
BAR = calibrate.bar(2.0, D, H, 1, H)
def run(sd_f, share_g, reps=1200, R=40):
    wins = 0; sd_d = []; sd_b = []; md = []
    for _ in range(reps // R):
        T = D + H - 1
        m = rng.standard_normal((R, 1, N)); x = rng.standard_normal((R, 1, N))
        f = rng.standard_normal((R, T, 1)) * sd_f; g = rng.standard_normal((R, T, 1)) * sd_f * share_g
        daily = rng.standard_normal((R, T, N)) + m * (f + 0.03 / math.sqrt(H)) + x * (g + 0.05 / math.sqrt(H))
        c = np.cumsum(daily, axis=1); r = c[:, H - 1:, :] - np.concatenate([np.zeros((R, 1, N)), c[:, :-H, :]], axis=1)
        rc = r - r.mean(2, keepdims=True); rs = r.std(2)
        alt = (m + LAM * x) / math.sqrt(1 + LAM * LAM)
        ia = (m * rc).mean(2) / (m.std(2) * rs); ib = (alt * rc).mean(2) / (alt.std(2) * rs)
        diff = ib - ia; t = calibrate.t_many(diff, H)
        ok = (t >= BAR) & (diff[:, :D // 2].mean(1) > 0) & (diff[:, D // 2:].mean(1) > 0)
        wins += int(ok.sum()); sd_d.append(diff.std(1).mean()); sd_b.append(ia.std(1).mean()); md.append(diff.mean())
    return wins / reps, float(np.mean(sd_b)), float(np.mean(sd_d)), float(np.mean(md))
print("bar", BAR)
for label, sd_f in (("Korea-swing-like", 0.105), ("US-swing-like", 0.23)):
    for share in (1.0, 0.5, 0.0):
        pw, sb, sd, md = run(sd_f, share)
        print(f"  {label:17s} added part's style return = {share:.1f} x the base's: sd of daily base IC {sb:.3f} | sd of daily IC difference {sd:.4f} (Agent 7's assumption gives {sb*math.sqrt(2*0.02):.4f}) | mean difference {md:+.4f} | passes {pw*100:.0f}%")
