"""Would untested Korean event signals add a new axis?  Rank correlation with the live long and swing signals across the live names.  No returns, no score change.
Reads OpenDART into the git-ignored research_data/kr_share_probe/axes.  Usage: python scripts/qsf_kr_candidate_axes.py out.json"""
import gzip
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from utils import runtime_config  # noqa: E402

runtime_config.load_local_env()
from scripts.qsf_kr_corp_action_probe import call  # noqa: E402
from scripts.qsf_signal_inventory import spearman  # noqa: E402
from terminal.qsf import engine  # noqa: E402
from terminal.qsf.service import QSF  # noqa: E402

BEGIN, END = "20251106", "20261106"
OUT = Path("research_data/kr_share_probe/axes")


def amount(v):
    try:
        x = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return x if np.isfinite(x) else None


def candidate(q, c):
    corp = q._corp_code(c)
    if not corp:
        return None
    count = {}
    for e in ("cvbdIsDecsn", "bdwtIsDecsn", "tsstkAqDecsn"):
        got = call(q.dart, OUT / f"{c}_{e}.json", f"{e}.json", corp_code=corp, bgn_de=BEGIN, end_de=END)
        count[e] = len(got.get("list") or []) if got.get("status") in ("000", "013") else None
    rights = json.loads((Path("research_data/kr_share_probe/actions") / f"{c}_piicDecsn.json").read_text(encoding="utf-8")).get("list") or []
    count["rights"] = sum(str(r.get("rcept_no") or "")[:8] >= BEGIN for r in rights)
    div = call(q.dart, OUT / f"{c}_alot.json", "alotMatter.json", corp_code=corp, bsns_year="2025", reprt_code="11011")
    dy = None
    for r in div.get("list") or []:                 # a labelled row of a structured report, not an account mapping
        if "수익률" in str(r.get("se")) and "보통" in str(r.get("stock_knd")):
            dy = amount(r.get("thstrm"))
            break
    hold = call(q.dart, OUT / f"{c}_holder.json", "hyslrSttus.json", corp_code=corp, bsns_year="2025", reprt_code="11011")
    stake = 0.0
    seen = False
    for r in hold.get("list") or []:
        if "보통" in str(r.get("stock_knd")) and str(r.get("nm")).strip() not in ("계", "합계", "소계"):
            v = amount(r.get("trmend_posesn_stock_qota_rt"))
            if v is not None:
                stake += v
                seen = True
    if None in (count["cvbdIsDecsn"], count["bdwtIsDecsn"], count["tsstkAqDecsn"]):
        return None
    return {"financing": count["cvbdIsDecsn"] + count["bdwtIsDecsn"] + count["rights"], "buyback": count["tsstkAqDecsn"], "dividend_yield": dy, "holder_stake": stake if seen else None}


def main(path):
    OUT.mkdir(parents=True, exist_ok=True)
    q = QSF(Path("."))
    live = json.load(open("data/qsf/latest_KR.json", encoding="utf-8"))
    bars = json.load(gzip.open("data/qsf/bars_KR.json.gz", "rt"))
    bench = q._history(["^KS11", "^KQ11"])["data"] or {}
    pre = q._prefetch(list(bars), {**bars, **bench}, "^KS11", live["session"])
    rows = []
    for c in sorted({r["ticker"] for r in live["rows"]}):
        ident = q._kr_identity(c)
        pre[c]["bench"] = bench.get("^KQ11" if ident and ident.get("market") == "KOSDAQ" else "^KS11") or []
        ctx = q.context(c, "KR", pre[c])
        cand = None if ctx.get("error") else candidate(q, c)
        if not cand:
            continue
        rec = {"t": c, **cand}
        for st in ("LONG_TERM", "SWING"):
            s = engine.score(ctx, st, held=False)
            rec[st] = {"score": s["score"], **{f["factor"]: f.get("normalized") for f in s["factors"]}}
        rows.append(rec)
    print("names", len(rows))
    for k in ("financing", "buyback", "dividend_yield", "holder_stake"):
        v = np.array([np.nan if r[k] is None else r[k] for r in rows], dtype=float)
        ok = np.isfinite(v)
        print(k, "value", int(ok.sum()), "nonzero", int((v[ok] != 0).sum()), "pct 10/50/90", np.percentile(v[ok], [10, 50, 90]).round(2))
        for st in ("LONG_TERM", "SWING"):
            s = np.array([r[st]["score"] for r in rows], dtype=float)
            corr = []
            for f in rows[0][st]:
                if f == "score":
                    continue
                x = np.array([np.nan if r[st].get(f) is None else r[st][f] for r in rows], dtype=float)
                m = ok & np.isfinite(x)
                if m.sum() >= 50 and x[m].std() > 0:
                    corr.append((round(spearman(v[m], x[m]), 2), f))
            corr.sort(key=lambda t: -abs(t[0]))
            print("  ", st, "with score", round(spearman(v[ok], s[ok]), 2), "largest", corr[:4])
    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False, default=float)


if __name__ == "__main__":
    main(sys.argv[1])
