"""AGENT 6 - script 6.  (a) the long verdict (756 sessions of 63-session returns): chance pass and rank-side power, random numbers
only, seed 60611;  (b) the family of 42 scheduled readings: arithmetic on each reading's own chance of clearing its t bar;
(c) my own count of the t values on file.  No price, no return, no record is read."""
import math, json, glob, os
import numpy as np
SEED, BLOCK = 60611, 1000

def nw_t(x, lag):
    n = x.shape[1]; e = x - x.mean(axis=1, keepdims=True)
    lrv = np.einsum("ij,ij->i", e, e) / n
    for k in range(1, min(lag, n - 1) + 1):
        lrv += 2.0 * (1.0 - k / (lag + 1.0)) * np.einsum("ij,ij->i", e[:, k:], e[:, :-k]) / n
    return x.mean(axis=1) / np.sqrt(lrv / n)

print("== (a) long verdict: 756 daily values of 63-session ICs, lag 63, bar 3.35; rank side only (t, mean IC >= 0.02, both halves > 0)")
H, N, BAR = 63, 756, 3.35
out = {}
for label, s in (("KR long, s 0.120 (BT-1 63-session cell / sqrt(2.33))", 0.120), ("KR long, s 0.107 (power note)", 0.107), ("US long, s 0.092 (BT-1 / sqrt(2.33))", 0.092), ("US long, s 0.140 (power note)", 0.140)):
    row = []
    for mu in (0.0, 0.03, 0.05, 0.057, 0.10):
        rng = np.random.default_rng([SEED, int(s * 1000), int(mu * 1000)]); hit = []
        for _ in range(0, 12000, BLOCK):
            cs = np.cumsum(mu / H + s / math.sqrt(H) * rng.standard_normal((BLOCK, N + H)), axis=1); x = cs[:, H:] - cs[:, :-H]
            m = N // 2
            hit.append((nw_t(x, H) >= BAR) & (x.mean(axis=1) >= 0.02) & (x[:, :m].mean(axis=1) > 0) & (x[:, m:].mean(axis=1) > 0))
        p = float(np.concatenate(hit).mean()); row.append((mu, p)); out[f"{label}|{mu}"] = p
    print(f"   {label}: " + " | ".join(f"IC {mu:.3f}: {100*p:.1f}%" for mu, p in row))

print("\n== (b) the 42 scheduled readings (terminal/qsf/readings.py REGISTRY 36 + three books x two markets): chance of clearing the t bar on noise")
print("   one-sided chance per reading = the normal-table tail of its nominal bar, which the calibrated bar restores (script 1); extra conditions only lower it")
fam = [  # (group, count, chance of a 'pass'-type result each, chance of an opposite-direction flag each, note)
    ("live verdict (4)", 4, 0.0125, 0.0, "t bar only; with all conditions 0.1-0.6% (script 3)"),
    ("early readings (4)", 4, 0.0030, 0.0030, "EARLY_AGAINST on the other side"),
    ("continuation (6 = 2 markets x 3 nested looks)", 2, 0.0084, 0.0, "per market, the three nested looks together (script 2)"),
    ("Korean avoid marks (1)", 1, 0.0125, 0.0, "T1 = 2.24"),
    ("score split (2)", 2, 0.02275, 0.02275, "either score 'better'"),
    ("fund period (2)", 2, 0.00135, 0.00135, "bar 3.0"),
    ("regime weights (2)", 2, 0.0, 0.0, "figures only"),
    ("US challenger (2)", 2, 0.02275, 0.0, ""),
    ("Korean price / fund / events records (3)", 3, 0.0125, 0.0, "bar 2.24"),
    ("Korean cap universe (1)", 1, 0.02275, 0.0, ""),
    ("Korean traded universe (1)", 1, 0.02275, 0.02275, "FORMER_BETTER / SWITCH_SUPPORTED"),
    ("Korean swing challenger (1)", 1, 0.02275, 0.0, "12 separate samples"),
    ("Korean prior swing formula (1)", 1, 0.02275, 0.02275, "PRIOR_BETTER / DECISION_SUPPORTED"),
    ("Korean bundle challenger (2)", 2, 0.02275, 0.02275, "CHALLENGER_BETTER / LIVE_BETTER"),
    ("Korean own method (2)", 2, 0.0, 0.0, "NO_PRIMARY: figures only"),
    ("committee paper portfolios (2 x 6 portfolios)", 2, 1 - (1 - 0.00135) ** 6, 1 - (1 - 0.00135) ** 6, "any of six, bar 3.0"),
    ("rank rules book (2)", 2, 0.02275, 0.0, "ADOPT"),
    ("entry rules book (2)", 2, 0.02275, 0.02275, "either book 'better'"),
    ("turnover rules book (2)", 2, 0.50, 0.0, "cost lower and mean difference >= 0: no t bar")]
def any_of(rows, both):
    q = 1.0
    for _, n, a, b, _ in rows:
        q *= (1 - (a + (b if both else 0))) ** n
    return 1 - q
tot = sum(n if "continuation" not in g else 6 for g, n, *_ in fam)
print(f"   readings counted: {tot}")
for g, n, a, b, note in fam:
    print(f"   {g:48s} pass-type {100*a:5.2f}% each | opposite flag {100*b:5.2f}% each | {note}")
notified = fam[:4]; filed_no_turn = fam[4:-1]
print(f"   15 notified readings: any pass-type by chance {100*any_of(notified, False):.1f}% (with EARLY_AGAINST {100*any_of(notified, True):.1f}%)")
print(f"   the four live verdicts alone: {100*any_of(fam[:1], False):.1f}% on the t bar; with every condition about 4 x 0.1..0.6% = 0.4..2.4%")
print(f"   25 filed readings without the turnover book: any pass-type {100*any_of(filed_no_turn, False):.1f}% | any flag either way {100*any_of(filed_no_turn, True):.1f}%")
print(f"   40 readings without the turnover book: any pass-type {100*any_of(fam[:-1], False):.1f}% | any flag either way {100*any_of(fam[:-1], True):.1f}%")
print(f"   all 42: any pass-type {100*any_of(fam, False):.1f}%   (the two turnover readings alone: {100*(1-0.25):.0f}%)")
print("   These treat the readings as independent.  They are not (one year, the same scores): fewer years have any false pass, and the years that have one tend to have several.")

print("\n== (c) t values on file in reports/qsf/*.json (own count; 'checks' blocks and the *_RUN1 copies left out)")
def walk(o, path, acc):
    if isinstance(o, dict):
        if "t" in o and isinstance(o.get("t"), (int, float)) and not isinstance(o.get("t"), bool) and not path.endswith("/checks"):
            acc.append((path, o["t"]))
        for k, v in o.items(): walk(v, path + "/" + str(k), acc)
    elif isinstance(o, list):
        for i, v in enumerate(o[:1000]): walk(v, path + f"[{i}]", acc)
groups = {"US": 0, "KR": 0}; big = {"US": 0, "KR": 0}; files = {"US": 0, "KR": 0}
for f in sorted(glob.glob("../../qsf/*.json")):
    name = os.path.basename(f)
    if "RUN1" in name or name.startswith("frozen"): continue
    try: d = json.load(open(f))
    except Exception: continue
    acc = []; walk(d, "", acc)
    if not acc: continue
    mk = "KR" if "_KR" in name else "US"
    groups[mk] += len(acc); big[mk] += sum(1 for _, t in acc if abs(t) >= 2.24); files[mk] += 1
    print(f"   {name:36s} {mk}  t values {len(acc):4d}   |t| >= 2.24: {sum(1 for _, t in acc if abs(t) >= 2.24):3d}")
print("   totals:", groups, "| |t| >= 2.24:", big, "| files:", files)
for mk in groups:
    n = groups[mk]
    print(f"   {mk}: if all {n} were independent noise, expected |t| >= 2.24 by the table: {n*0.025:.0f}; one or more of them above 3.0 one-sided: {100*(1-(1-0.00135)**n):.0f}%")
json.dump(out, open("s06_out.json", "w"), indent=1)
