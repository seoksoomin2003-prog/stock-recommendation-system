"""Inventory of live QSF signals under the current code on the last published session.  No returns, no record, no published file touched.
For each score: per-signal weight, coverage, spread, variance share; effective axes; overlap clusters; what the first axis and size explain.
Usage: python scripts/qsf_signal_inventory.py out.json"""
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from utils import runtime_config  # noqa: E402

runtime_config.load_local_env()
from terminal.qsf import engine  # noqa: E402
from terminal.qsf.service import QSF  # noqa: E402


def ranks(x):
    v, inv = np.unique(x, return_inverse=True)
    o = np.argsort(np.argsort(x, kind="mergesort"), kind="mergesort").astype(float)
    return np.array([o[inv == i].mean() for i in range(len(v))])[inv]


def spearman(x, y):
    a, b = ranks(x), ranks(y)
    return 0.0 if a.std() == 0 or b.std() == 0 else float(np.corrcoef(a, b)[0, 1])


def bets(C):
    ev = np.clip(np.linalg.eigvalsh(np.cov(C.T))[::-1], 0, None)
    return float(ev.sum() ** 2 / (ev ** 2).sum()), float(ev[0] / ev.sum())


def analyse(cards):
    names = sorted({f["factor"] for c in cards for f in c["factors"]})
    pos = {n: j for j, n in enumerate(names)}
    meta = {f["factor"]: (f["domain"], f["weight"]) for c in cards for f in c["factors"]}
    A, C = np.full((len(cards), len(names)), np.nan), np.zeros((len(cards), len(names)))
    for i, c in enumerate(cards):
        for f in c["factors"]:
            if f.get("normalized") is not None:
                A[i, pos[f["factor"]]] = f["normalized"]
            if f.get("contribution") is not None:
                C[i, pos[f["factor"]]] = f["contribution"]
    score = np.array([c["score"] for c in cards], dtype=float)
    out = []
    for n, j in pos.items():
        v = A[:, j]
        ok = ~np.isnan(v)
        cnt = np.unique(v[ok], return_counts=True)[1] if ok.any() else np.array([0])
        out.append({"factor": n, "domain": meta[n][0], "weight": meta[n][1], "cover": float(ok.mean()), "top_value_share": float(cnt.max() / max(ok.sum(), 1)),
                    "std": float(np.nanstd(v)) if ok.any() else 0.0, "var_share": float(np.cov(C[:, j], score)[0, 1] / score.var(ddof=1))})
    used = [x["factor"] for x in out if x["std"] > 0 and x["cover"] >= 0.5 and x["top_value_share"] < 1]
    R = np.eye(len(used))
    for a in range(len(used)):
        for b in range(a + 1, len(used)):
            m = ~np.isnan(A[:, pos[used[a]]]) & ~np.isnan(A[:, pos[used[b]]])
            if m.sum() >= 30:
                R[a, b] = R[b, a] = spearman(A[m, pos[used[a]]], A[m, pos[used[b]]])
    par = list(range(len(used)))

    def root(i):
        while par[i] != i:
            i = par[i]
        return i
    for a in range(len(used)):
        for b in range(a + 1, len(used)):
            if abs(R[a, b]) >= 0.5:
                par[root(a)] = root(b)
    cl = defaultdict(list)
    for a, n in enumerate(used):
        cl[root(a)].append(n)
    ev = np.clip(np.linalg.eigvalsh(R)[::-1], 0, None)
    eq = float(ev.sum() ** 2 / (ev ** 2).sum())
    weighted, first = bets(C)
    u, s, vt = np.linalg.svd(C - C.mean(0), full_matrices=False)
    pc = (C - C.mean(0)) @ vt[0]
    adv = np.array([c["_adv"] if c["_adv"] else np.nan for c in cards], dtype=float)
    m = np.isfinite(adv) & (adv > 0)
    return {"stocks": len(cards), "signals": len(names), "varying": len(used), "clusters": len(cl), "cluster_members": [sorted(x) for x in cl.values() if len(x) > 1], "equal_effective": eq,
            "weighted_axes": weighted, "first_axis_share": first, "first_axis_score_corr": abs(float(np.corrcoef(pc, score)[0, 1])),
            "score_size_corr": spearman(score[m], adv[m]), "first_axis_top": [names[j] for j in np.argsort(-np.abs(vt[0]))[:5]], "factors": sorted(out, key=lambda x: -x["var_share"])}


def main(path):
    q = QSF(Path("."))
    res = {}
    for market in ("US", "KR"):
        live = json.load(open(f"data/qsf/latest_{market}.json", encoding="utf-8"))
        pub = {(r["ticker"], r["strategy"]): r["score"] for r in live["rows"]}
        codes = sorted({t for t, _ in pub})
        if market == "KR":
            bars = json.load(gzip.open("data/qsf/bars_KR.json.gz", "rt"))
            bench = q._history(["^KS11", "^KQ11"])["data"] or {}
            pre = q._prefetch(list(bars), {**bars, **bench}, "^KS11", live["session"])
            for c in pre:
                ident = q._kr_identity(c)
                pre[c]["bench"] = bench.get("^KQ11" if ident and ident.get("market") == "KOSDAQ" else "^KS11") or []
        else:
            pre = q._us_scan_input(sorted(set(q.terminal.lab.universe()["tickers"]) | {t for t in q.terminal.watchlist() if not t.startswith("^")}) if q.terminal else codes)
        cards = defaultdict(list)
        same = total = 0
        for t in codes:
            ctx = q.context(t, market, pre[t])
            if ctx.get("error"):
                continue
            for st in ("SWING", "LONG_TERM"):
                c = engine.score(ctx, st, held=False)
                if c["score"] is None:
                    continue
                liq = next((f for f in c["factors"] if f["factor"] == "liquidity"), None)
                c["_adv"] = (liq.get("raw") or {}).get("adv_value") if liq else None
                total += 1
                same += abs(c["score"] - pub[(t, st)]) < 0.01
                cards[st].append(c)
        print(market, "reproduced", same, "of", total, "session", live["session"], live["model_version"])
        for st, rows in cards.items():
            r = analyse(rows)
            res[f"{market}_{st}"] = r
            print(f"{market} {st}: signals {r['signals']} varying {r['varying']} clusters {r['clusters']} equal {r['equal_effective']:.1f} weighted {r['weighted_axes']:.1f} first {r['first_axis_share']:.2f} corr {r['first_axis_score_corr']:.2f} size {r['score_size_corr']:+.2f}")
            print("  overlaps", r["cluster_members"])
            print("  empty or flat", [(x["factor"], round(x["cover"], 2), round(x["top_value_share"], 2)) for x in r["factors"] if x["cover"] < 0.5 or x["top_value_share"] >= 0.9])
            print("  top var", [(x["factor"], x["weight"], round(x["var_share"], 2)) for x in r["factors"][:7]])
    json.dump(res, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)


if __name__ == "__main__":
    main(sys.argv[1])
