"""Which Korean live signals move together: the measurement behind reports/QSF_KR_CHALLENGER_PROTOCOL.md.

Read-only.  It reads the normalized signal values of five Korean ledger sessions and nothing else: no price, no return.
Run from the project folder: .venv/bin/python scripts/qsf_kr_bundle_overlap.py
"""
import glob
import gzip
import json
from collections import defaultdict

import numpy as np

DAYS = ("2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17")     # every Korean ledger session on the market-value universe before the protocol
MIN_COVER, MAX_SAME, SAME_BUNDLE = 0.5, 0.9, 0.5


def ranks(x):
    """Average ranks, ties shared."""
    _, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
    start = np.cumsum(cnt) - cnt
    return (start + (cnt - 1) / 2.0)[inv]


def percentile(col):
    out = np.full(len(col), np.nan)
    ok = np.isfinite(col)
    if ok.sum() >= 2:
        out[ok] = ranks(col[ok]) / (ok.sum() - 1)
    return out


def spearman(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30:
        return float("nan")
    x, y = ranks(a[m]), ranks(b[m])
    if x.std() == 0 or y.std() == 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def load(day):
    path = sorted(glob.glob(f"data/qsf/ledger/{day}_KR_*"))[-1]
    by = defaultdict(list)
    with gzip.open(path, "rt") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("score") is not None and r.get("data_date") == day:
                by[r["strategy"]].append(r)
    return {k: sorted(v, key=lambda r: r["ticker"]) for k, v in by.items()}


def same_share(v):
    ok = np.isfinite(v)
    return float(np.unique(v[ok], return_counts=True)[1].max() / ok.sum()) if ok.any() else 1.0


def mean_of(parts, need):
    x = np.array(parts)
    have = np.isfinite(x).sum(0)
    return np.where(have >= need * len(parts), np.nansum(x, 0) / np.maximum(have, 1), np.nan)


def main():
    data = {d: load(d) for d in DAYS}
    for strategy in ("SWING", "LONG_TERM"):
        newest = data[DAYS[-1]][strategy][0]["factors"]
        names = [x["factor"] for x in newest if x.get("scored", True) is not False and x["weight"] > 0]     # the signals the live score counts
        points = {x["factor"]: x["weight"] for x in newest}
        mats = {}
        for d in DAYS:
            rows = data[d][strategy]
            a = np.full((len(rows), len(names)), np.nan)
            for i, r in enumerate(rows):
                for x in r["factors"]:
                    if x["factor"] in names and x.get("normalized") is not None:
                        a[i, names.index(x["factor"])] = float(x["normalized"])
            mats[d] = a
        cover = np.mean([[np.isfinite(mats[d][:, j]).mean() for j in range(len(names))] for d in DAYS], 0)
        same = np.mean([[same_share(mats[d][:, j]) for j in range(len(names))] for d in DAYS], 0)
        use = [j for j in range(len(names)) if cover[j] >= MIN_COVER and same[j] < MAX_SAME]
        print(f"\n=== {strategy}: {len(names)} counted signals, stocks per day {[len(data[d][strategy]) for d in DAYS]}")
        for j, n in enumerate(names):
            print(f"  {n:26s} points {points[n]:3.0f}  with a value {cover[j]:.2f}  same value {same[j]:.2f}  {'kept' if j in use else 'LEFT OUT'}")
        k = len(use)
        per_day = []
        for d in DAYS:
            r = np.eye(k)
            for p in range(k):
                for q in range(p + 1, k):
                    r[p, q] = r[q, p] = spearman(mats[d][:, use[p]], mats[d][:, use[q]])
            per_day.append(r)
        mean = np.nanmean(np.array(per_day), 0)
        parent = list(range(k))

        def find(i):
            while parent[i] != i:
                i = parent[i]
            return i
        for p in range(k):
            for q in range(p + 1, k):
                if abs(mean[p, q]) >= SAME_BUNDLE:
                    parent[find(p)] = find(q)
        groups = defaultdict(list)
        for p in range(k):
            groups[find(p)].append(names[use[p]])
        bundles = sorted(groups.values(), key=lambda g: names.index(g[0]))
        print("  pairs with |mean rank correlation| >= 0.35:")
        for p in range(k):
            for q in range(p + 1, k):
                if abs(mean[p, q]) >= 0.35:
                    print(f"    {names[use[p]]:24s} {names[use[q]]:22s} mean {mean[p, q]:+.3f}  per day {[round(float(r[p, q]), 2) for r in per_day]}")
        print(f"  bundles: {len(bundles)}")
        for b in bundles:
            print(f"    {b}  live points {sum(points[n] for n in b):.0f}")
        for d in DAYS:
            rows = data[d][strategy]
            pct = {names[j]: percentile(mats[d][:, j]) for j in use}
            final = mean_of([mean_of([pct[n] for n in b], 0.5) for b in bundles], 0.7) * 100
            live = np.array([float(r["score"]) for r in rows])
            top = max(1, len(rows) // 5)
            a = set(np.argsort(-np.where(np.isfinite(final), final, -1), kind="mergesort")[:top])
            b = set(np.argsort(-live, kind="mergesort")[:top])
            print(f"  {d}: challenger scores {int(np.isfinite(final).sum())}/{len(rows)}, rank correlation with the live score {spearman(final, live):.3f}, shared top fifth {len(a & b) / top:.2f}")


if __name__ == "__main__":
    main()
