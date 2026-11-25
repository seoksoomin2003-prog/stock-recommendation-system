"""AGENT 6 - script 5.  Arithmetic on recorded figures only (reports/qsf/QSF_BACKTEST_CURRENT_{US,KR}.json) plus the null
quantiles of script 1.  No price, no return, no record is read."""
import json, math
from statistics import NormalDist
ND = NormalDist()
s1 = json.load(open("s01_out.json"))
bt = {m: json.load(open(f"../../qsf/QSF_BACKTEST_CURRENT_{m}.json")) for m in ("US", "KR")}

print("== 1. Interval of each rank correlation: IC +- crit x (IC/t).  crit = the 95% two-sided point of noise of the cell's own design (script 1), not 1.96")
cells = s1["bt1_cells"]
for c in cells:
    se = abs(c["ic"] / c["t"]); lo, hi = c["ic"] - c["crit95"] * se, c["ic"] + c["crit95"] * se
    lo2, hi2 = c["ic"] - 1.96 * se, c["ic"] + 1.96 * se
    c.update(se=se, lo=lo, hi=hi)
    print(f"{c['name']:14s} IC {c['ic']:+.4f}  t {c['t']:5.2f}  se {se:.4f}  crit {c['crit95']:.2f}  95%: [{lo:+.3f}, {hi:+.3f}]   (with 1.96: [{lo2:+.3f}, {hi2:+.3f}])  date-level sd(IC/t*sqrt(n)) {se*math.sqrt(c['n']):.3f}")

print("\n== 2. Multiple testing on the 12 rank cells of BT-1 (2 markets x 2 scores x 3 horizons; p of script 1's null; one-sided)")
ps = sorted(((c["p"], c["name"]) for c in cells))
m = len(ps)
print("   Holm (controls the chance of ANY false pass; valid under any dependence):")
alive = True
for i, (p, name) in enumerate(ps):
    thr = 0.05 / (m - i); ok = alive and p <= thr; alive = ok
    if i < 8: print(f"     {name:14s} p {p:.5f}  Holm threshold {thr:.5f}  -> {'passes' if ok else 'fails'}   | Bonferroni-adjusted p {min(1, p*m):.4f}")
print("   Benjamini-Hochberg at 5% and 10% (controls the share of false passes; valid under positive dependence):")
for q in (0.05, 0.10):
    k = max([i + 1 for i, (p, _) in enumerate(ps) if p <= q * (i + 1) / m] or [0])
    print(f"     q {q:.2f}: {k} cells pass ->", [n for _, n in ps[:k]])
# the same with the 12 account t values of the same file counted too (24 t values in BT-1): their one-sided p from the normal table
acc_t = [bt[mk]["strategies"][st]["accounts"]["accounts"][a]["excess_t"] for mk in ("US", "KR") for st in ("SWING", "LONG_TERM") for a in ("TOP_FIFTH", "BUY_BAND", "ALL_SCORED")]
ps24 = sorted(ps + [(1 - ND.cdf(t), "account") for t in acc_t]); m24 = len(ps24)
holm24 = 0
for i, (p, _) in enumerate(ps24):
    if p <= 0.05 / (m24 - i): holm24 += 1
    else: break
bh = lambda q: max([i + 1 for i, (p, _) in enumerate(ps24) if p <= q * (i + 1) / m24] or [0])
print(f"   counting all 24 t values of BT-1 (12 rank + 12 account-against-index): Holm passes {holm24} ({[n for _, n in ps24[:holm24]]}); BH 5% passes {bh(0.05)}; BH 10% passes {bh(0.10)}")
for extra, label in ((42, "x 42 (7 domain sets x 2 universes x 3 horizons seen before the Korean swing formula was chosen)"), (500, "x 500 (order of all t values on file for the two windows)")):
    print(f"   Korean swing 20-session cell, p {ps[0][0]:.5f} (simulation floor 1/60001; t distribution with 88 df gives about 8e-7): {label}: {min(1, 8e-7*extra):.5f} .. {min(1, ps[0][0]*extra):.5f}")

print("\n== 3. Accounts: excess over the index per 21-session period, interval = mean +- t(0.975, T-1) x mean/t ; tracking error; years to tell 3% a year")
def tcrit(df):      # two-sided 95% point of Student t, by a short series (enough at df ~ 88..151)
    z = 1.959964; return z + (z**3 + z) / (4 * df) + (5*z**5 + 16*z**3 + 3*z) / (96 * df * df)
acc_rows = []
for mk in ("US", "KR"):
    for st in ("SWING", "LONG_TERM"):
        a = bt[mk]["strategies"][st]["accounts"]["accounts"]; idx = a["INDEX"]
        for name in ("TOP_FIFTH", "BUY_BAND", "ALL_SCORED"):
            x = a[name]; T = x["periods"]; mean = x["excess_per_period_pct"]; t = x["excess_t"]; se = abs(mean / t); sd = se * math.sqrt(T)
            c = tcrit(T - 1); lo, hi = mean - c * se, mean + c * se
            te = sd * math.sqrt(12)
            yrs50 = (1.96 * te / 3.0) ** 2; yrs80 = ((1.96 + 0.8416) * te / 3.0) ** 2
            by = x["by_year"]; pos = sum(1 for v in by.values() if v > 0)
            acc_rows.append({"market": mk, "strategy": st, "account": name, "T": T, "mean": mean, "t": t, "lo": lo, "hi": hi, "te_annual": te, "yrs50": yrs50, "yrs80": yrs80,
                             "sharpe": x["sharpe"], "index_sharpe": idx["sharpe"], "pos_years": pos, "years": len(by), "worst_year": min(by.items(), key=lambda kv: kv[1])})
            print(f"{mk} {st[:5]:5s} {name:10s} T={T:3d} excess {mean:+.3f}%/period (t {t:+.2f}) 95% [{lo:+.2f}, {hi:+.2f}] = [{lo*12:+.1f}, {hi*12:+.1f}] %/yr | tracking error {te:.1f}%/yr | 3%/yr: {yrs50:.0f} yrs (50% power), {yrs80:.0f} yrs (80%) | years above index {pos}/{len(by)}, worst {min(by.items(), key=lambda kv: kv[1])[0]} {min(by.values()):+.1f}pp | Sharpe {x['sharpe']:.2f} vs index {idx['sharpe']:.2f}")

print("\n== 4. Sign test of the by-year excess (file values; years are not independent of the pooled t, shown as stability only)")
from math import comb
for r in acc_rows:
    if r["account"] == "TOP_FIFTH":
        n, k = r["years"], r["pos_years"]
        p_low = sum(comb(n, j) for j in range(0, k + 1)) / 2 ** n
        print(f"{r['market']} {r['strategy'][:5]:5s} top fifth: above the index in {k} of {n} calendar years; chance of {k} or fewer with a fair coin {p_low:.3f}")

print("\n== 5. Deflated Sharpe (Bailey & Lopez de Prado 2014).  Per-period Sharpe = annual / sqrt(12); T = periods on file.")
print("   SR0 = sqrt(V) * ((1-g) * Z(1-1/N) + g * Z(1-1/(N e))), g = 0.5772; V = variance of the trials' Sharpe estimates: NOT on file -> assumed 1/(T-1) (independent trials with no skill).")
print("   DSR = Phi((SR - SR0) * sqrt(T-1) / sqrt(1 - skew*SR + (kurt-1)/4*SR^2)).  Skewness and kurtosis are NOT on file -> shown for normal (0, 3) and for (-0.7, 6) ASSUMED.")
g = 0.5772156649
def sr0(T, N):
    return math.sqrt(1 / (T - 1)) * ((1 - g) * ND.inv_cdf(1 - 1 / N) + g * ND.inv_cdf(1 - 1 / (N * math.e)))
def dsr(sr, T, N, skew=0.0, kurt=3.0):
    base = 0.0 if N <= 1 else sr0(T, N)
    return ND.cdf((sr - base) * math.sqrt(T - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr * sr))
print("   (a) Sharpe against zero (what the file calls 'sharpe').  N = 1 is the plain probabilistic Sharpe.")
print(f"   {'account':28s} {'SR/yr':>6s} {'idx':>5s} | N=1   N=12  N=50  N=200 | N=50 with skew -0.7, kurt 6")
for r in acc_rows:
    if r["account"] == "ALL_SCORED": continue
    sr = r["sharpe"] / math.sqrt(12); T = r["T"]
    print(f"   {r['market']+' '+r['strategy'][:5]+' '+r['account']:28s} {r['sharpe']:6.2f} {r['index_sharpe']:5.2f} | {dsr(sr,T,1):.3f} {dsr(sr,T,12):.3f} {dsr(sr,T,50):.3f} {dsr(sr,T,200):.3f} | {dsr(sr,T,50,-0.7,6):.3f}")
for mk in ("US", "KR"):
    idx = bt[mk]["strategies"]["SWING"]["accounts"]["accounts"]["INDEX"]; sr = idx["sharpe"] / math.sqrt(12); T = idx["periods"]
    print(f"   {mk+' INDEX itself':28s} {idx['sharpe']:6.2f}       | {dsr(sr,T,1):.3f} {dsr(sr,T,12):.3f} {dsr(sr,T,50):.3f} {dsr(sr,T,200):.3f} | {dsr(sr,T,50,-0.7,6):.3f}")
print("   (b) The same on the excess over the index (information ratio per period = excess_t / sqrt(T)): the figure that answers 'did the score add anything'.")
print(f"   {'account':28s} {'IR/yr':>6s} | N=1   N=12  N=50  N=200")
for r in acc_rows:
    ir = r["t"] / math.sqrt(r["T"]); T = r["T"]
    print(f"   {r['market']+' '+r['strategy'][:5]+' '+r['account']:28s} {ir*math.sqrt(12):6.2f} | {dsr(ir,T,1):.3f} {dsr(ir,T,12):.3f} {dsr(ir,T,50):.3f} {dsr(ir,T,200):.3f}")
print(f"   expected best excess t among N no-skill accounts (T=152): N=12 {sr0(152,12)*math.sqrt(151):.2f}, N=50 {sr0(152,50)*math.sqrt(151):.2f}, N=200 {sr0(152,200)*math.sqrt(151):.2f}; the best on file is {max(r['t'] for r in acc_rows):+.2f}")

print("\n== 6. Years of record to establish RANK: z = (IC/s) * sqrt(periods), 12.5 separate 20-session periods a year; one-sided 1.25% (2.24) and power 50% / 80%")
print("   (asymptotic; the small-sample bars of the first years are higher, see script 2 for those)")
for label, s in (("KR swing, s 0.100", 0.100), ("KR swing, s 0.138", 0.138), ("US swing, s 0.198", 0.198)):
    row = []
    for ic in (0.03, 0.05, 0.10):
        y50 = (2.24 * s / ic) ** 2 / 12.5; y80 = ((2.24 + 0.8416) * s / ic) ** 2 / 12.5
        row.append(f"IC {ic:.2f}: {y50:.1f} / {y80:.1f} yrs")
    print(f"   {label}: " + " | ".join(row))
# long: 63-session periods, 4 a year; s from BT-1 63-session cells, corrected for the Bartlett weights (triangular overlap at 21-session steps: factor 2.333)
for mk in ("US", "KR"):
    c = [x for x in cells if x["market"] == mk and x["h"] == 63][0]
    s_lr = c["se"] * math.sqrt(c["n"]); s = s_lr / math.sqrt(2.3333)
    row = []
    for ic in (0.03, 0.05, 0.10):
        y50 = (2.24 * s / ic) ** 2 / 4.0; y80 = ((2.24 + 0.8416) * s / ic) ** 2 / 4.0
        row.append(f"IC {ic:.2f}: {y50:.1f} / {y80:.1f} yrs")
    print(f"   {mk} long 63 sessions, s {s:.3f} (file-implied {s_lr:.3f} / sqrt(2.33)): " + " | ".join(row))
json.dump({"cells": cells, "accounts": [{k: (list(v) if isinstance(v, tuple) else v) for k, v in r.items()} for r in acc_rows]}, open("s05_out.json", "w"), indent=1)
