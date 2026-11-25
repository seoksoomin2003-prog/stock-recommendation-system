"""Agent 8, second pass.  No return of any real stock is computed.
(A) Agent 6's made-up market (every stock the same expected return) with the score-to-volatility link MEASURED on the ledger
    instead of assumed 0.8: recorded Spearman(Korean swing score, hist_vol) per session under the current composition.
(B) Agent 7's forward power for near-identical alternatives: the same true difference (+0.009 IC, scores correlated 0.98), under
    two noise structures: the added part rides its own style factor as volatile as the base score's / the added part rides none.
(C) Agent 7's band persistence: stored historical US scores only (no price): share of the 70+ set, of the same-size top set and
    of the top fifth still inside 21 sessions later."""
import sys, json, math, gzip
import numpy as np
sys.path.insert(0, '.'); sys.path.insert(0, 'reports/score_reliability_audit_2026_11_25/scratch_08')
from load import sessions, snaps
from rk import spearmanr
from terminal.qsf import calibrate
rng = np.random.default_rng(8809)

print("(A) recorded link between the Korean swing score and volatility")
led, ss = sessions(); rhos = []
for d in [x for x in ss['KR'] if x >= '2026-11-11']:
    rows = [s for s in snaps(led, 'KR', d) if s['strategy'] == 'SWING' and s.get('score') is not None and s.get('confidence') != 'INSUFFICIENT']
    sc, hv = [], []
    for s in rows:
        f = next((x for x in s['factors'] if x['factor'] == 'atr_risk' and isinstance(x.get('raw'), dict)), None)
        if f and f['raw'].get('hist_vol') is not None: sc.append(s['score']); hv.append(f['raw']['hist_vol'])
    rhos.append(spearmanr(sc, hv)[0]); sdlog = float(np.std(np.log(hv)))
print("   Spearman(score, hist_vol) by session:", [round(x, 2) for x in rhos], "mean", round(float(np.mean(rhos)), 2), "| sd of log volatility across stocks (last session)", round(sdlog, 2))
def rank(a): return np.argsort(np.argsort(a, axis=-1), axis=-1).astype(float)
def world(noise_sd, REPS=300, D=89, N=280, lottery=True, sd_logv=0.45):
    v = np.exp(rng.normal(math.log(0.10), sd_logv, (REPS, 1, N)))
    score = -np.log(v) + rng.normal(0, noise_sd, (REPS, D, N))
    mkt = rng.normal(0.0, 0.06, (REPS, D, 1)); b = 0.5 + 5 * v
    r = np.exp(b * mkt - (b * 0.06) ** 2 / 2 - v ** 2 / 2 + v * rng.standard_normal((REPS, D, N))) - 1
    if lottery:
        p = np.clip(0.02 * v / 0.10, 0, 0.2); jump = rng.random((REPS, D, N)) < p
        r = (1 + r) * np.where(jump, 1.6, 1.0) / (1 + 0.6 * p) - 1
    ex = r - r.mean(axis=2, keepdims=True); rs, rr = rank(score), rank(ex)
    rs -= rs.mean(axis=2, keepdims=True); rr -= rr.mean(axis=2, keepdims=True)
    ic = (rs * rr).sum(axis=2) / np.sqrt((rs ** 2).sum(axis=2) * (rr ** 2).sum(axis=2))
    rv = rank(np.broadcast_to(-np.log(v), score.shape)); rv = rv - rv.mean(axis=2, keepdims=True)
    link = float(((rs * rv).sum(axis=2) / np.sqrt((rs ** 2).sum(axis=2) * (rv ** 2).sum(axis=2))).mean())
    t = ic.mean(axis=1) / (ic.std(axis=1, ddof=1) / math.sqrt(D))
    return link, float(ic.mean()), float(np.median(t)), float((ic > 0).mean())
for nsd in (0.33, 0.60, 0.90, 1.10, 1.50):
    link, ic, t, pos = world(nsd)
    print(f"   made-up market, score noise {nsd:.2f}: rank link score~calm {link:+.2f} | mean IC {ic:+.3f} | median t over 89 dates {t:.2f} | dates positive {pos*100:.0f}%   (file: IC +0.054, t 5.13, 72%)")

print("\n(B) power of a paired forward comparison, true difference about +0.009 (base IC 0.03, added part's own IC 0.05, scores correlated 0.98)")
def power(style_x, sd_base, reps=1500, N=300, D=240, h=20, bar=None):
    """Daily cross-sections of 20-session returns built as overlapping sums of daily pieces.  r = m*f + x*g + c_m*m + c_x*x + eps.
    f: style factor of the base score m (makes the base IC swing); g: style factor of the added part x (0 when it rides none)."""
    lam = 0.203
    bar = bar or calibrate.bar(2.0, D, h, 1, h)
    wins = 0; sds = []; sdb = []
    for _ in range(reps // 50):
        R = 50; T = D + h - 1
        m = rng.standard_normal((R, 1, N)); x = rng.standard_normal((R, 1, N))
        eps = rng.standard_normal((R, T, N))
        # per-day pieces: an IC of k on a 20-session return needs a slope of k*sqrt(20) spread over 20 days -> k/sqrt(20) a day against unit daily noise
        f = rng.standard_normal((R, T, 1)) * sd_base * math.sqrt(N) / math.sqrt(N)       # daily style return of m, in units of daily idiosyncratic sd
        g = rng.standard_normal((R, T, 1)) * (sd_base if style_x else 0.0)
        daily = eps + m * (f + 0.03 / math.sqrt(h)) + x * (g + 0.05 / math.sqrt(h))
        c = np.cumsum(daily, axis=1); r = c[:, h - 1:, :] - np.concatenate([np.zeros((R, 1, N)), c[:, :-h, :]], axis=1)
        a = np.broadcast_to(m, r.shape); b_ = np.broadcast_to((m + lam * x) / math.sqrt(1 + lam * lam), r.shape)
        def ic(s):
            return ((s - s.mean(2, keepdims=True)) * (r - r.mean(2, keepdims=True))).mean(2) / (s.std(2) * r.std(2))
        ia, ib = ic(a), ic(b_); diff = ib - ia
        t = calibrate.t_many(diff, h); half = D // 2
        ok = (t >= bar) & (diff[:, :half].mean(1) > 0) & (diff[:, half:].mean(1) > 0)
        wins += int(ok.sum()); sds.append(diff.std(axis=1).mean()); sdb.append(ia.std(axis=1).mean())
    return wins / reps, float(np.mean(sds)), float(np.mean(sdb)), bar
for label, sd_base in (("base IC swings like Korea swing (about 0.10 a day)", 0.10 / math.sqrt(20)), ("base IC swings like US swing (about 0.20 a day)", 0.20 / math.sqrt(20))):
    for style_x in (True, False):
        pw, sd_d, sd_b, bar = power(style_x, sd_base)
        print(f"   {label}; added part {'rides a style factor of its own' if style_x else 'rides no style factor'}: sd of daily base IC {sd_b:.3f}, sd of daily IC difference {sd_d:.4f}, passes (t>={bar}, both halves) {pw*100:.0f}%")

print("\n(C) persistence of bands 21 sessions later, stored US scores")
d = json.load(gzip.open('data/qsf/research/scores_current_us.json.gz', 'rt')); days = {}
for r in d['records']: days.setdefault(r['i'], []).append(r)
keys = sorted(days)
for strat in ('SWING', 'LONG_TERM'):
    k70, ksame, k20, n70 = [], [], [], []
    for a, b in zip(keys[:-1], keys[1:]):
        A = {r['t']: r[strat] for r in days[a] if r.get(strat) is not None}; B = {r['t']: r[strat] for r in days[b] if r.get(strat) is not None}
        com = [t for t in A if t in B]
        if len(com) < 100: continue
        oa = sorted(com, key=lambda t: -A[t]); ob = sorted(com, key=lambda t: -B[t])
        s70 = {t for t in com if A[t] >= 70}; n = len(s70); n70.append(n)
        if n >= 5:
            k70.append(len(s70 & {t for t in com if B[t] >= 70}) / n)
            ksame.append(len(set(oa[:n]) & set(ob[:n])) / n)
        q = len(com) // 5; k20.append(len(set(oa[:q]) & set(ob[:q])) / q)
    print(f"   US {strat}: still inside after 21 sessions: 70+ {np.mean(k70)*100:.0f}% | same-size top set {np.mean(ksame)*100:.0f}% | top fifth {np.mean(k20)*100:.0f}%;  size of the 70+ set: median {int(np.median(n70))}, min {min(n70)}, max {max(n70)}; days with fewer than 5: {sum(1 for x in n70 if x < 5)}")
