# Score of the stock screen against the scan on the same session.  The scan passes each stock's universe rank of six-month return; the
# screen's context has none, so relative_strength falls back to a return against the benchmark.  Touches no record and no published file.
# Usage: python scripts/qsf_screen_scan_gap.py out.json
import gzip
import json
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from utils import runtime_config  # noqa: E402

runtime_config.load_local_env()
from terminal.qsf import engine  # noqa: E402
from terminal.qsf.service import QSF  # noqa: E402

SAMPLE = 25


def main(path):
    q = QSF(Path("."))
    res = {}
    for market in ("KR", "US"):
        live = json.load(open(f"data/qsf/latest_{market}.json", encoding="utf-8"))
        pub = {(r["ticker"], r["strategy"]): r for r in live["rows"]}
        codes = sorted({t for t, _ in pub})
        if market == "KR":
            bars = json.load(gzip.open("data/qsf/bars_KR.json.gz", "rt"))
            bench = q._history(["^KS11", "^KQ11"])["data"] or {}
            pre_all = q._prefetch(list(bars), {**bars, **bench}, "^KS11", live["session"])
            for c in pre_all:
                ident = q._kr_identity(c)
                pre_all[c]["bench"] = bench.get("^KQ11" if ident and ident.get("market") == "KOSDAQ" else "^KS11") or []
        else:
            pre_all = q._us_scan_input(codes)
        rows, same, total = [], 0, 0
        for t in codes:
            if t not in pre_all:
                continue
            ctx = q.context(t, market, pre_all[t])
            if ctx.get("error"):
                continue
            rec = {"t": t, "name": ctx.get("name"), "rank": ctx.get("rs_rank")}
            for st in ("LONG_TERM", "SWING"):
                a = engine.score(ctx, st, held=False)
                b = engine.score({**ctx, "rs_rank": None}, st, held=False)
                p = pub.get((t, st))
                total += 1
                same += bool(p) and abs(a["score"] - p["score"]) < 0.01
                f = next(x for x in b["factors"] if x["factor"] == "relative_strength")
                rec[st] = {"scan": a["score"], "scan_band": a["band"], "screen": b["score"], "screen_band": b["band"], "fallback": f.get("normalized")}
            rows.append(rec)
        print("==", market, "stocks", len(rows), "scan reproduced", same, "of", total, "rank missing", sum(r["rank"] is None for r in rows))
        rank = np.array([r["rank"] for r in rows if r["rank"] is not None])
        back = np.array([r["SWING"]["fallback"] for r in rows if r["rank"] is not None], dtype=float)
        ok = np.isfinite(back)
        print("  fallback at floor", int((back[ok] <= 0).sum()), "at ceiling", int((back[ok] >= 1).sum()), "of", int(ok.sum()), "| rank corr", round(float(np.corrcoef(np.argsort(np.argsort(rank[ok])), np.argsort(np.argsort(back[ok])))[0, 1]), 3))
        for st in ("LONG_TERM", "SWING"):
            d = np.array([r[st]["screen"] - r[st]["scan"] for r in rows if r[st]["scan"] is not None and r[st]["screen"] is not None])
            a = np.abs(d)
            flip = [r for r in rows if r[st]["scan_band"] != r[st]["screen_band"]]
            buy_a = {r["t"] for r in rows if "BUY" in r[st]["scan_band"]}
            buy_b = {r["t"] for r in rows if "BUY" in r[st]["screen_band"]}
            print(" ", st, "n", len(d), "mean signed", round(float(d.mean()), 2), "mean abs", round(float(a.mean()), 2), "p50/p90", np.percentile(a, [50, 90]).round(2), "max", round(float(a.max()), 2), ">=1", int((a >= 1).sum()), ">=2", int((a >= 2).sum()), ">=3", int((a >= 3).sum()),
                  "band differs", len(flip), "buy scan", len(buy_a), "screen", len(buy_b), "scan only", sorted(buy_a - buy_b)[:12], "screen only", sorted(buy_b - buy_a)[:12])
            print("    largest", [(r["t"], r["name"], round(r[st]["screen"], 1), round(r[st]["scan"], 1)) for r in sorted(rows, key=lambda r: -abs(r[st]["screen"] - r[st]["scan"]))[:6]])
        # The real screen path on a sample: separate price request, no prefetch.
        random.seed(20261108)
        pick = random.sample(rows, min(SAMPLE, len(rows)))
        checks = {"no_rank_equals_fallback": 0, "with_rank_equals_scan": 0, "n": 0}
        misses = []
        for r in pick:
            ctx = q.context(r["t"], market)
            if ctx.get("error"):
                continue
            for st in ("LONG_TERM", "SWING"):
                checks["n"] += 1
                x = engine.score(ctx, st, held=False)["score"]
                y = engine.score({**ctx, "rs_rank": r["rank"]}, st, held=False)["score"]
                checks["no_rank_equals_fallback"] += abs(x - r[st]["screen"]) < 0.01
                ok2 = abs(y - r[st]["scan"]) < 0.01
                checks["with_rank_equals_scan"] += ok2
                if not ok2:
                    misses.append((r["t"], st[:4], round(y, 2), round(r[st]["scan"], 2)))
        print("  real screen path", checks, "misses", misses[:10])
        res[market] = rows
    json.dump(res, open(path, "w", encoding="utf-8"), ensure_ascii=False, default=float)


if __name__ == "__main__":
    main(sys.argv[1])
