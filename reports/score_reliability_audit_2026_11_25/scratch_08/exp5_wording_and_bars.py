"""Agent 8: (1) wording.earned on a hand-written file in a TEMP folder outside the repository (nothing of the system is touched);
(2) the continuation bars recomputed with calibrate.bar (random numbers only); (3) how often noise that is NOT the calibration's
i.i.d. normal passes the calibrated bar: fat tails + volatility clustering + mild day-to-day persistence (assumptions in the code).
(4) chance that the money condition (band - index > 0 in both halves) is met with no score effect, for a given universe drift."""
import sys, json, tempfile, os
from pathlib import Path
import numpy as np
sys.path.insert(0, '.')
from terminal.qsf import wording, calibrate, engine, config

# (1)
tmp = Path(tempfile.mkdtemp(prefix="agent08_"))
(tmp / "reports" / "qsf").mkdir(parents=True)
print("earned before any file:", wording.earned(tmp, "US", "SWING"))
(tmp / "reports" / "qsf" / "QSF_LIVE_FORWARD_US_SWING.json").write_text(json.dumps({"verdict": "WEAK_POSITIVE_EVIDENCE"}))
print("earned with a hand-written 1-key file:", wording.earned(tmp, "US", "SWING"))
res = wording.restore({"band": "BUY_CANDIDATE", "band_label": "상위 구간", "action": "BUY", "action_label": "상위 구간"}, tmp, "US", "SWING")
print("restored card words:", res["band_label"], "/", res["action_label"])
(tmp / "reports" / "qsf" / "QSF_LIVE_FORWARD_CONT_KR_SWING_480.json").write_text(json.dumps({"verdict": "WEAK_POSITIVE_EVIDENCE", "model_version": "QSF-0.0.0", "market": "US", "strategy": "LONG_TERM", "status": "DRAFT"}))
print("earned from a continuation file alone, with a wrong market/strategy/version/status inside and no first verdict:", wording.earned(tmp, "KR", "SWING"))
print("config.MODEL_VERSION now:", config.MODEL_VERSION, "- earned() takes no version argument:", wording.earned.__code__.co_varnames[:3])

# (2)
for n in (240, 480, 720, 960):
    nominal = 2.24 if n == 240 else 2.64
    print(f"bar n={n} nominal {nominal}: {calibrate.bar(nominal, n, 20, 1, 20)}   one-sided chance of nominal: {calibrate.tail(nominal)*100:.2f}%")

# (3) non-ideal noise.  daily "IC innovation" e_t: Student-t(4) scaled, GARCH(1,1)-like variance (a=0.10, b=0.85), plus AR(1) 0.10 in the daily innovation
def rough(rng, rows, n, h, ar=0.10, a=0.10, b=0.85, df=4):
    T = n - 1 + h
    z = rng.standard_t(df, size=(rows, T)) / np.sqrt(df / (df - 2))
    e = np.empty_like(z); v = np.ones(rows); prev = np.zeros(rows)
    for t in range(T):
        x = np.sqrt(v) * z[:, t]
        e[:, t] = ar * prev + x
        v = (1 - a - b) + a * x * x + b * v
        prev = e[:, t]
    c = np.cumsum(e, axis=1)
    sums = c[:, h - 1:] - np.concatenate([np.zeros((rows, 1)), c[:, :-h]], axis=1)
    return sums[:, :n]
rng = np.random.default_rng(808)
for n, nominal in ((240, 2.24), (480, 2.64), (960, 2.64)):
    bar = calibrate.bar(nominal, n, 20, 1, 20)
    for label, kw in (("fat tails + vol clustering, no persistence", dict(ar=0.0)), ("the same + AR(1) 0.10 in daily IC innovations", dict(ar=0.10)), ("the same + AR(1) 0.20", dict(ar=0.20))):
        t = np.concatenate([calibrate.t_many(rough(rng, 4000, n, 20, **kw), 20) for _ in range(5)])
        print(f"  n={n} bar {bar}: noise passes {np.mean(t >= bar)*100:.2f}% (target {calibrate.tail(nominal)*100:.2f}%)  [{label}]")

# (4) money condition with no score effect: band-index per day = drift + noise; both half-means > 0?
# assumption: 240 daily values of overlapping 20-session excess, sd of a 20-session excess 3% (band of ~50 names vs a cap-weighted index), drift per 20 sessions as given
rng = np.random.default_rng(809)
for drift in (-0.004, -0.002, 0.0, 0.002, 0.004):
    x = calibrate.noise(rng, 20000, 240, 20, 1) / np.sqrt(20) * 0.03 + drift
    ok = (x[:, :120].mean(1) > 0) & (x[:, 120:].mean(1) > 0)
    print(f"  money condition met with zero score effect, universe drift {drift*100:+.1f}% per 20 sessions: {ok.mean()*100:.1f}%")
import shutil; shutil.rmtree(tmp)
