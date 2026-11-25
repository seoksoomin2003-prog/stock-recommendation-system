"""Experiment 7 (detail): which factor is behind the large one-day score moves, same-version day pairs.  Scores and factor rows only."""
import collections
from common import *
res = {}
for market in ("US", "KR"):
    ss = sessions(market)
    for strat in ("SWING", "LONG_TERM"):
        big = collections.Counter(); n_big = n_all = 0; status_flip = 0; share_of_abs = collections.Counter(); tot_abs = 0.0
        for (s0, v0), (s1, v1) in zip(ss, ss[1:]):
            if v0 != v1:
                continue
            a, b = load(market, s0)[strat], load(market, s1)[strat]
            for t in set(a) & set(b):
                if a[t]["score"] is None or b[t]["score"] is None:
                    continue
                n_all += 1
                fa = {f["factor"]: f for f in a[t]["factors"] if f.get("scored") is not False}; fb = {f["factor"]: f for f in b[t]["factors"] if f.get("scored") is not False}
                wa = sum(f["weight"] for f in fa.values() if f["status"] in QUAL); wb = sum(f["weight"] for f in fb.values() if f["status"] in QUAL)
                d = {}
                for k in fa:
                    ca = 100 * fa[k]["weight"] * fa[k]["normalized"] / wa if fa[k]["status"] in QUAL else None
                    cb = 100 * fb[k]["weight"] * fb[k]["normalized"] / wb if k in fb and fb[k]["status"] in QUAL else None
                    if ca is not None and cb is not None:
                        d[k] = cb - ca
                    elif (ca is None) != (cb is None):
                        d[k] = None
                for k, v in d.items():
                    if v is not None:
                        share_of_abs[k] += abs(v); tot_abs += abs(v)
                if abs(b[t]["score"] - a[t]["score"]) > 5:
                    n_big += 1
                    if any(v is None for v in d.values()):
                        status_flip += 1
                    lead = max(((abs(v), k) for k, v in d.items() if v is not None), default=(0, "?"))
                    big[lead[1]] += 1
        key = f"{market}_{strat}"
        res[key] = {"stock_days": n_all, "moves_gt_5": n_big, "share": n_big / n_all, "lead_factor_of_big_moves": dict(big.most_common(6)), "big_moves_with_a_factor_appearing_or_vanishing": status_flip,
                    "share_of_all_day_to_day_movement": {k: round(v / tot_abs, 3) for k, v in share_of_abs.most_common(6)}}
        print(key, res[key])
dump("s07b_jumps.json", res)
