"""AGENT 6 - script 3.  The swing verdict with ALL its conditions (five rank conditions + the money condition), read at 240
sessions and again at 480/720/960 as the program will.  Random numbers only.  Seed 60609.  A reduced-form model: every figure
the verdict reads is simulated as a daily series of overlapping 20-session values.

  IC_t      = mu + s * X1_t                               X*: independent unit-variance series, each the sum of 20 daily shocks / sqrt(20)
  spread_t  = B_s * IC_t + n_s * X2_t - cost              top fifth - bottom fifth, net of one round trip   (validate.per_date)
  band_t    = B_b * IC_t + n_b * X3_t                     band mean - mean of every scored stock (cost cancels) (buy_excess / top_score_effect)
  univ_t    = m_u - cost + s_u * X4_t                     every scored stock at equal weight, net of cost, - index
  money     : mean(band_t + univ_t) > 0 in BOTH halves    (condition B)

File values (arithmetic on BT-1): s = IC/t*sqrt(n) -> KR 0.100, US 0.198;  s_u = |excess/excess_t|*sqrt(periods) of ALL_SCORED ->
US 1.81% per 21 sessions, KR 3.72% (x sqrt(20/21));  cost US 0.402%, KR 0.53%;  m_u: 0 ("U0") or BT-1's ALL_SCORED excess per period
(US -0.157%, KR -0.494%; the Korean one is mixed with index differences, see the errata) ("U1").
ASSUMPTIONS (not on file):
  mapping "G": B_s = 17.5% per unit of IC in Korea (file: risk-only score 2012-2019, IC 0.137 with top +0.9% / bottom -1.5%,
     QSF_KR_TECH_EARLY_RESULTS.md) and 14% in the US (assumed: an effective cross-sectional sd of 5% x 2.8); B_b = B_s/2 (Korea, top fifth)
     and 0.59 x B_s (US, the top 12% that score 70+).
  mapping "Z" (Korea only): B_s = B_b = 0: the rank correlation is real but the means are equal, as in BT-1's Korean swing table.
  noise: n_s, n_b such that the day-to-day correlation of IC with spread / band is 0.8 under "G"; the same noise under "Z".
Results are orders of magnitude.  Under mu = 0 they depend little on the assumptions.
"""
import math, json
import numpy as np
SEED, BLOCK, H = 60609, 2500, 20
BARS = {240: 3.33, 480: 3.66, 720: 3.52, 960: 3.44}
MARKETS = {"KR": {"s": 0.100, "cost": 0.0053, "s_u": 0.0372 * math.sqrt(20 / 21), "m_u1": -0.00494 * 20 / 21, "B_s": 0.175, "k_b": 0.5},
           "US": {"s": 0.198, "cost": 0.00402, "s_u": 0.0181 * math.sqrt(20 / 21), "m_u1": -0.00157 * 20 / 21, "B_s": 0.14, "k_b": 0.59}}


def nw_t(x, lag):
    n = x.shape[1]; e = x - x.mean(axis=1, keepdims=True)
    lrv = np.einsum("ij,ij->i", e, e) / n
    for k in range(1, min(lag, n - 1) + 1):
        lrv += 2.0 * (1.0 - k / (lag + 1.0)) * np.einsum("ij,ij->i", e[:, k:], e[:, :-k]) / n
    return x.mean(axis=1) / np.sqrt(lrv / n)


def ma(rng, rows, n):
    cs = np.cumsum(rng.standard_normal((rows, n + H)), axis=1)
    return (cs[:, H:] - cs[:, :-H]) / math.sqrt(H)


def both(x):
    m = x.shape[1] // 2
    return (x[:, :m].mean(axis=1) > 0) & (x[:, m:].mean(axis=1) > 0)


def run(market, mu, mapping="G", universe="U0", sims=20000, s=None):
    p = MARKETS[market]; s = p["s"] if s is None else s
    B_s = p["B_s"] if mapping == "G" else 0.0
    B_b = B_s * p["k_b"]
    n_s = 0.75 * p["B_s"] * s; n_b = 0.75 * p["B_s"] * p["k_b"] * s          # the same noise under both mappings
    m_u = 0.0 if universe == "U0" else p["m_u1"]
    rng = np.random.default_rng([SEED, {"KR": 1, "US": 2}[market] * 100 + {"G": 1, "Z": 2}[mapping] * 10 + {"U0": 1, "U1": 2}[universe], int(round(mu * 1e4)), int(round(s * 1e4))])
    acc = {n: {"A": [], "B": [], "AB": [], "t": [], "ic": [], "ich": [], "sph": [], "band": []} for n in BARS}
    for done in range(0, sims, BLOCK):
        ic = mu + s * ma(rng, BLOCK, 960)
        spread = B_s * ic + n_s * ma(rng, BLOCK, 960) - p["cost"]
        band = B_b * ic + n_b * ma(rng, BLOCK, 960)
        univ = m_u - p["cost"] + p["s_u"] * ma(rng, BLOCK, 960)
        for n, bar in BARS.items():
            x = ic[:, :n]
            c_t = nw_t(x, H) >= bar; c_ic = x.mean(axis=1) >= 0.02; c_ich = both(x); c_sp = both(spread[:, :n]); c_band = band[:, :n].mean(axis=1) > 0
            A = c_t & c_ic & c_ich & c_sp & c_band
            Bm = both(band[:, :n] + univ[:, :n])
            for k, v in (("A", A), ("B", Bm), ("AB", A & Bm), ("t", c_t), ("ic", c_ic), ("ich", c_ich), ("sph", c_sp), ("band", c_band)):
                acc[n][k].append(v)
    r = {n: {k: np.concatenate(v) for k, v in d.items()} for n, d in acc.items()}
    cum_A = np.zeros(sims, dtype=bool); cum_AB = np.zeros(sims, dtype=bool); out = {}
    for n in BARS:
        cum_A |= r[n]["A"]; cum_AB |= r[n]["AB"]
        out[n] = {"A": float(r[n]["A"].mean()), "B": float(r[n]["B"].mean()), "AB": float(r[n]["AB"].mean()), "cum_A": float(cum_A.mean()), "cum_AB": float(cum_AB.mean()),
                  **{k: float(r[n][k].mean()) for k in ("t", "ic", "ich", "sph", "band")}}
    return out


f = lambda v: f"{100 * v:5.1f}%"
res = {}
print("columns: [at 240] t bar | spread both halves | rank conditions A | money B | A and B (the pass)  ||  A and B by 480 | by 720 | by 960   (rank A by 960)")
for market in ("KR", "US"):
    for mapping in (("G", "Z") if market == "KR" else ("G",)):
        for universe in ("U0", "U1"):
            for mu in (0.0, 0.03, 0.05, 0.10):
                o = run(market, mu, mapping, universe, sims=100000 if mu == 0 else 20000)
                res[f"{market}|{mapping}|{universe}|{mu}"] = o
                a = o[240]
                print(f"{market} map {mapping} {universe} true IC {mu:.2f}: {f(a['t'])} | {f(a['sph'])} | {f(a['A'])} | {f(a['B'])} | {f(a['AB'])}  || {f(o[480]['cum_AB'])} | {f(o[720]['cum_AB'])} | {f(o[960]['cum_AB'])}   ({f(o[960]['cum_A'])})")
print("\nKorea with the date-to-date IC sd of the power note (0.138) instead of BT-1's 0.100, mapping G, U0:")
for mu in (0.0, 0.03, 0.05, 0.10):
    o = run("KR", mu, "G", "U0", sims=20000, s=0.138); res[f"KR|G|U0|{mu}|s0.138"] = o; a = o[240]
    print(f"KR s=0.138 true IC {mu:.2f}: {f(a['t'])} | {f(a['sph'])} | {f(a['A'])} | {f(a['B'])} | {f(a['AB'])}  || {f(o[480]['cum_AB'])} | {f(o[720]['cum_AB'])} | {f(o[960]['cum_AB'])}   ({f(o[960]['cum_A'])})")
json.dump(res, open("s03_out.json", "w"), indent=1)
