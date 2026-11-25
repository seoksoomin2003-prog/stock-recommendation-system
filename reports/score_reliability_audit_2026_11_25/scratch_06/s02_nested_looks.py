"""AGENT 6 - script 2.  The swing family of one market as ONE simulated record: early 60/120 (5-session outcome), verdict 240,
continuation 480/720/960 (20-session outcome), all read from the same daily shocks, as the program will read one ledger.
Random numbers only.  Seed 60607.

Model: daily contribution c_d = mu/20 + (s/sqrt(20)) * e_d ; a session's h-session IC = sum of the next h contributions.
  => mean 20-session IC = mu, its date-to-date sd = s (file values: KR 0.100 from BT-1 = IC/t*sqrt(n); KR 0.138 and US 0.197
     from QSF_LIVE_FORWARD_POWER_2026_11_11.md; US 0.198 from BT-1).
  A rank correlation has no scale, so an h-session IC is (sum of h daily pay-offs) / sqrt(h): its date-to-date sd does not grow
  with h (file: KR 5 sessions 0.118 vs 20 sessions 0.100; US 0.239 vs 0.198) and its mean grows with sqrt(h) when the score pays
  evenly.  So the 5-session IC here = 2 x (sum of 5 contributions): mean mu/2, sd s.  ASSUMPTION "even".  A second run gives the
  5-session IC the same mean as the 20-session one ("front": the pay-off comes in the first week), which the Korean BT-1 table
  suggests (0.050 at 5 sessions, 0.054 at 20).  (First run of this script scaled the 5-session IC wrongly; corrected, kept in git-less scratch as s02_out_v1.txt.)
Only the t condition and the two IC conditions (mean >= 0.02, both halves > 0) are checked here; spread, band and money
conditions are in script 3.  So "pass" here is an UPPER bound of the verdict's pass rate.
"""
import math, sys, json
import numpy as np

SEED, BLOCK = 60607, 2500
BARS = {"early60": 4.29, "early120": 3.76, "v240": 3.33, "c480": 3.66, "c720": 3.52, "c960": 3.44}   # the program's own bars (script 1, column "program")
H = 20


def nw_t(x, lag):
    n = x.shape[1]
    e = x - x.mean(axis=1, keepdims=True)
    lrv = np.einsum("ij,ij->i", e, e) / n
    for k in range(1, min(lag, n - 1) + 1):
        lrv += 2.0 * (1.0 - k / (lag + 1.0)) * np.einsum("ij,ij->i", e[:, k:], e[:, :-k]) / n
    return x.mean(axis=1) / np.sqrt(lrv / n)


def shocks(rng, rows, n, kind):
    """Daily shocks with unit variance.  kind: iid | ar10 | ar20 | t4 | volcluster | slow05 | slow15"""
    if kind in ("slow05", "slow15"):   # a slow part (daily AR 0.98, half-life 34 sessions) carrying 5% / 15% of the daily variance: pay-offs that trend for months
        w = 0.05 if kind == "slow05" else 0.15
        z = rng.standard_normal((rows, n + 200)); slow = np.empty_like(z); slow[:, 0] = z[:, 0]
        for j in range(1, z.shape[1]):
            slow[:, j] = 0.98 * slow[:, j - 1] + math.sqrt(1 - 0.98 ** 2) * z[:, j]
        return math.sqrt(1 - w) * rng.standard_normal((rows, n)) + math.sqrt(w) * slow[:, 200:]
    if kind == "iid":
        return rng.standard_normal((rows, n))
    if kind in ("ar10", "ar20"):
        phi = 0.10 if kind == "ar10" else 0.20
        z = rng.standard_normal((rows, n + 50))
        out = np.empty_like(z); out[:, 0] = z[:, 0]
        for j in range(1, z.shape[1]):
            out[:, j] = phi * out[:, j - 1] + math.sqrt(1 - phi * phi) * z[:, j]
        return out[:, 50:]
    if kind == "t4":
        return rng.standard_t(4, (rows, n)) / math.sqrt(2.0)
    if kind == "volcluster":            # two volatility states (ratio 3), mean stay 60 sessions; unit variance overall
        st = np.zeros((rows, n), dtype=bool); cur = rng.random(rows) < 0.25
        flip = rng.random((rows, n))
        for j in range(n):
            cur = np.where(flip[:, j] < 1 / 60, rng.random(rows) < 0.25, cur); st[:, j] = cur
        sd = np.where(st, 3.0, 1.0); sd = sd / math.sqrt(0.25 * 9 + 0.75)
        return rng.standard_normal((rows, n)) * sd
    raise ValueError(kind)


def halves_ok(x):
    m = x.shape[1] // 2
    return (x[:, :m].mean(axis=1) > 0) & (x[:, m:].mean(axis=1) > 0)


def run(mu, s, kind="iid", sims=40000, early_mean="even", seed_extra=0):
    rng = np.random.default_rng([SEED, int(round(mu * 1e4)), int(round(s * 1e4)), seed_extra, len(kind)])
    n_days = 960 + H
    res = {k: [] for k in ("t60", "t120", "t240", "t480", "t720", "t960", "p60", "p120", "p240", "p480", "p720", "p960", "plain240", "against60", "against120")}
    for done in range(0, sims, BLOCK):
        rows = min(BLOCK, sims - done)
        e = shocks(rng, rows, n_days, kind)
        c = mu / H + s / math.sqrt(H) * e                                    # daily contributions
        cs = np.cumsum(c, axis=1)
        x20 = cs[:, H:] - cs[:, :-H]                                           # session j: sum of contributions j+1..j+20  (960 values)
        x5 = 2.0 * (cs[:, 5:965] - cs[:, :960])                                # mean mu/2, sd s
        if early_mean == "front":                                              # 5-session IC has the full mean mu (noise unchanged)
            x5 = x5 + mu / 2
        for n, key, x, lag in ((60, "60", x5, 5), (120, "120", x5, 5), (240, "240", x20, H), (480, "480", x20, H), (720, "720", x20, H), (960, "960", x20, H)):
            xs = x[:, :n]
            t = nw_t(xs, lag)
            res["t" + key].append(t)
            bar = BARS[{"60": "early60", "120": "early120", "240": "v240", "480": "c480", "720": "c720", "960": "c960"}[key]]
            res["p" + key].append((t >= bar) & (xs.mean(axis=1) >= 0.02) & halves_ok(xs))
            if key in ("60", "120"):
                res["against" + key].append(t <= -bar)
        sep = x20[:, :240:H]                                                   # the 12 separate samples of the old way
        res["plain240"].append(sep.mean(axis=1) / (sep.std(axis=1, ddof=1) / math.sqrt(sep.shape[1])))
        res.setdefault("_a", []).append(x20[:, 0] - mu); res.setdefault("_b", []).append(x20[:, H] - mu)
    a, b = np.concatenate(res.pop("_a")), np.concatenate(res.pop("_b"))
    got = {k: np.concatenate(v) for k, v in res.items()}
    got["rho_sep"] = float(np.corrcoef(a, b)[0, 1])
    return got


def pct(x):
    return f"{100 * float(np.mean(x)):.2f}%"


out = {}
print("== A. pure noise (mu = 0): how often each look clears its t bar, and how often ANY look does (nested looks, one record)")
for kind in ("iid", "ar10", "ar20", "t4", "volcluster", "slow05", "slow15"):
    r = run(0.0, 0.10, kind, sims=200000 if kind == "iid" else 40000)
    t = {k: r["t" + k] for k in ("60", "120", "240", "480", "720", "960")}
    hit = {"60": t["60"] >= BARS["early60"], "120": t["120"] >= BARS["early120"], "240": t["240"] >= BARS["v240"], "480": t["480"] >= BARS["c480"],
           "720": t["720"] >= BARS["c720"], "960": t["960"] >= BARS["c960"]}
    cont_any = hit["480"] | hit["720"] | hit["960"]
    swing_any = hit["240"] | cont_any
    all_any = swing_any | hit["60"] | hit["120"]
    row = {"t_only": {k: float(v.mean()) for k, v in hit.items()}, "continuation_any": float(cont_any.mean()), "continuation_any_given_240_failed": float(cont_any[~hit["240"]].mean()),
           "verdict_or_continuation": float(swing_any.mean()), "any_of_six": float(all_any.mean()), "sum_of_three_cont": float(sum(hit[k].mean() for k in ("480", "720", "960"))),
           "early_any": float((hit["60"] | hit["120"]).mean()), "early_against_any": float((r["against60"] | r["against120"]).mean()),
           "with_ic_conditions": {k: float(r["p" + k].mean()) for k in ("60", "120", "240", "480", "720", "960")},
           "p_t240_ge_2.24": float((t["240"] >= 2.24).mean())}
    out["null_" + kind] = row
    print(f"\n-- daily shocks: {kind}  (sims {len(t['240'])})   correlation of one separate 20-session IC with the next: {r['rho_sep']:+.3f}")
    print("   t >= bar  :", {k: pct(v) for k, v in hit.items()}, "   [t240 >= 2.24 (table value): " + pct(t["240"] >= 2.24) + "]")
    print("   three continuation looks, any:", pct(cont_any), "| sum of the three:", f"{100*row['sum_of_three_cont']:.2f}%", "| any, given the 240 verdict failed:", pct(cont_any[~hit['240']]))
    print("   verdict 240 or any continuation:", pct(swing_any), "| any of the six looks:", pct(all_any), "| early any:", pct(hit['60'] | hit['120']), "| EARLY_AGAINST any:", pct(r['against60'] | r['against120']))
    print("   with the two IC conditions too:", {k: pct(r['p' + k]) for k in ("60", "120", "240", "480", "720", "960")})

print("\n== B. power of the rank side (t bar + mean IC >= 0.02 + both halves > 0): upper bound of the verdict's pass rate")
print("   columns: verdict at 240 | passed by 480 | by 720 | by 960 (cumulative, as the program reads) | old way: 12 separate samples, plain t >= its own 1.25% bar")
import statistics
plain_bar = None
r0 = run(0.0, 0.10, "iid", sims=200000, seed_extra=7)
plain_bar = float(np.quantile(r0["plain240"], 1 - 0.0125))
print(f"   (plain t of 12 separate samples: noise reaches {plain_bar:.2f} with chance 1.25%; t-table with 11 df says 2.59)")
out["plain_bar_12"] = plain_bar
for market, s in (("KR s=0.100 (BT-1 today)", 0.100), ("KR s=0.138 (power note)", 0.138), ("US s=0.198 (BT-1 today)", 0.198)):
    for mu in (0.03, 0.05, 0.10):
        r = run(mu, s, "iid", sims=40000)
        p240 = r["p240"]; by480 = p240 | r["p480"]; by720 = by480 | r["p720"]; by960 = by720 | r["p960"]
        tonly = r["t240"] >= BARS["v240"]
        old = r["plain240"] >= plain_bar
        out[f"power|{market}|{mu}"] = {"p240": float(p240.mean()), "by480": float(by480.mean()), "by720": float(by720.mean()), "by960": float(by960.mean()), "t_only_240": float(tonly.mean()),
                                         "old_way_12": float(old.mean()), "early60": float(r["p60"].mean()), "early120": float(r["p120"].mean()), "median_t240": float(np.median(r["t240"])),
                                         "median_plain": float(np.median(r["plain240"]))}
        print(f"   {market:26s} true IC {mu:.2f}: {pct(p240):>7s} | {pct(by480):>7s} | {pct(by720):>7s} | {pct(by960):>7s} | old way {pct(old):>7s} | early60 {pct(r['p60'])}, early120 {pct(r['p120'])} | median t: daily {np.median(r['t240']):.2f}, separate {np.median(r['plain240']):.2f}")

print("\n== C. early readings if the 5-session IC is as large as the 20-session one (front-loaded pay-off)")
for market, s in (("KR s=0.100", 0.100), ("US s=0.198", 0.198)):
    for mu in (0.03, 0.05, 0.10):
        r = run(mu, s, "iid", sims=40000, early_mean="front", seed_extra=3)
        out[f"early_front|{market}|{mu}"] = {"early60": float(r["p60"].mean()), "early120": float(r["p120"].mean())}
        print(f"   {market:12s} true IC {mu:.2f}: early60 {pct(r['p60'])}, early120 {pct(r['p120'])}")
json.dump(out, open("s02_out.json", "w"), indent=1)
