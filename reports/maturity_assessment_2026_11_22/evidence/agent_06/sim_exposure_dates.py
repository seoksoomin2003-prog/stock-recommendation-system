"""AGENT 6: (a) exposure confound of the self-applying rank book at its new bar; (b) earliest verdict dates. Random numbers and a calendar only."""
import math, sys
from pathlib import Path
import numpy as np
REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
from terminal.qsf import calibrate

def nw(x, lag):
    n = x.shape[1]; d = x - x.mean(axis=1, keepdims=True)
    v = np.einsum("ij,ij->i", d, d) / n
    for k in range(1, lag + 1):
        v += 2 * (1 - k / (lag + 1.0)) * np.einsum("ij,ij->i", d[:, k:], d[:, :-k]) / n
    return x.mean(axis=1) / np.sqrt(v / n)

bar = calibrate.bar(2.0, 240, 1, 1, 20)
print("(a) rank book RK-1: no selection skill at all; the rule book is invested 20 points less than the paper book; bar", bar)
print("    diff_t = -0.20 * market_t + noise_t ; market vol 18%/yr ; noise sd per day given")
rng = np.random.default_rng(606)
for drift in (-0.30, -0.15, 0.0, 0.15):
    for noise_sd in (0.001, 0.003):
        m = rng.standard_normal((20000, 240)) * (0.18 / math.sqrt(252)) + drift / 252
        diff = -0.20 * m + rng.standard_normal((20000, 240)) * noise_sd
        t = nw(diff, 20)
        print(f"    market {drift:+.0%}/yr, noise {noise_sd*100:.1f}%/day: ADOPT (mean>0 & t>={bar}) in {float(((diff.mean(axis=1) > 0) & (t >= bar)).mean())*100:.1f}%")

print("(b) earliest dates: sessions counted from 2026-11-23, weekdays minus exchange holidays I listed by hand (approximate beyond 2027)")
us_h = ["2026-11-26","2026-12-25","2027-01-01","2027-01-18","2027-02-15","2027-03-26","2027-05-31","2027-06-18","2027-07-05","2027-09-06","2027-11-25","2027-12-24",
        "2027-12-31","2028-01-17","2028-02-21","2028-04-14","2028-05-29","2028-06-19","2028-07-04","2028-09-04","2028-11-23","2028-12-25",
        "2029-01-01","2029-01-15","2029-02-19","2029-03-30","2029-05-28","2029-06-19","2029-07-04","2029-09-03","2029-11-22","2029-12-25",
        "2030-01-01","2030-01-21","2030-02-18","2030-04-19","2030-05-27","2030-06-19","2030-07-04"]
us_h = [d for d in us_h if d != "2027-12-31"]          # NYSE trades on 2027-12-31 (New Year's Day 2028 falls on a Saturday)
kr_h = ["2026-12-25","2026-12-31","2027-01-01","2027-02-05","2027-02-08","2027-03-01","2027-05-05","2027-05-13","2027-08-16","2027-09-14","2027-09-15","2027-09-16",
        "2027-10-04","2027-10-11","2027-12-27","2027-12-31",
        "2028-01-26","2028-01-27","2028-01-28","2028-03-01","2028-04-12","2028-05-02","2028-05-05","2028-06-06","2028-08-15","2028-10-02","2028-10-03","2028-10-04","2028-10-05","2028-10-09","2028-12-25","2028-12-29",
        "2029-01-01","2029-02-12","2029-02-13","2029-02-14","2029-03-01","2029-05-01","2029-05-07","2029-05-21","2029-06-06","2029-08-15","2029-09-21","2029-09-24","2029-10-03","2029-10-09","2029-12-25","2029-12-31",
        "2030-01-01","2030-02-04","2030-02-05","2030-03-01","2030-04-03","2030-05-01","2030-05-06","2030-05-09","2030-06-06","2030-06-12"]
for market, hol in (("US", us_h), ("KR", kr_h)):
    for name, need, h in (("SWING", 240, 20), ("LONG_TERM", 756, 63)):
        nth = need + h                                    # readings.wanted: recorded sessions before the daily job asks; the last one's bar closes the 240th hold
        day = np.busday_offset("2026-11-23", nth - 1, roll="forward", holidays=hol)
        print(f"    {market} {name}: session number {nth} is about {day} (if no session is ever missed and no formula change moves the start again)")
