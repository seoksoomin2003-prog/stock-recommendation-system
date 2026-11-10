# Korean score if consolidated figures were paired with consolidated figures, and if two groups with a financial business were read as
# financial or had their cash flow left empty.  Touches no record, no ledger and no published file: context and score only.  Output JSON goes to the path given.
import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from utils import runtime_config  # noqa: E402

runtime_config.load_local_env()
from terminal.qsf import engine, fundamentals  # noqa: E402
from terminal.qsf.service import QSF  # noqa: E402

FINANCE_GROUPS = {"005380": "현대자동차", "000880": "한화"}


def latest(rows, as_of, end=None):
    rows = fundamentals._vintage(rows or [], as_of)
    if end:
        rows = [r for r in rows if r["end"] == end]
    return rows[-1] if rows else None


def paired(fund, data, as_of):
    """Consolidated over consolidated.  The stock market value belongs to the parent's holders, so free cash flow is cut to their share."""
    eq, all_eq = latest(data.get("equity"), as_of), None
    if not eq:
        return fund
    all_eq = latest(data.get("equity_all"), as_of, eq["end"])
    if not all_eq or all_eq["val"] <= 0 or eq["val"] <= 0 or eq["val"] > all_eq["val"]:
        return fund
    share = eq["val"] / all_eq["val"]
    out = dict(fund, parent_share=share)
    if fund.get("debt_equity") is not None and fund["debt_equity"] != 99.0:
        out["debt_equity"] = fund["debt_equity"] * share
    if fund.get("equity_assets") is not None:
        out["equity_assets"] = fund["equity_assets"] / share
    if fund.get("fcf_yield") is not None:
        out["fcf_yield"] = fund["fcf_yield"] * share
    ocf, ni = latest(data.get("ocf"), as_of), latest(data.get("net_income_all"), as_of)
    if ocf and ni and ocf["end"] == ni["end"]:
        out["ocf_to_ni"] = ocf["val"] / ni["val"] if ni["val"] > 0 else None
    return out


def as_financial(fund):
    return dict(fund, is_financial=True)


def blanked(fund):
    """No figure rather than a wrong one: cash flow that holds a financial business says nothing of the car or the holding company."""
    return dict(fund, fcf=None, fcf_yield=None, fcf_margin=None, fcf_years_positive=None, ocf_to_ni=None)


def main(path):
    q = QSF(Path("."))
    live = json.load(open("data/qsf/latest_KR.json", encoding="utf-8"))
    pub = {(r["ticker"], r["strategy"]): r for r in live["rows"]}
    bars = json.load(gzip.open("data/qsf/bars_KR.json.gz", "rt"))
    bench = q._history(["^KS11", "^KQ11"])["data"] or {}
    pre_all = q._prefetch(list(bars), {**bars, **bench}, "^KS11", live["session"])
    out, same, total = [], 0, 0
    for c in sorted({t for t, _ in pub}):
        if c not in bars:
            continue
        ident = q._kr_identity(c)
        ctx = q.context(c, "KR", {**pre_all[c], "bench": bench.get("^KQ11" if ident.get("market") == "KOSDAQ" else "^KS11") or []})
        if ctx.get("error"):
            continue
        fund = ctx["fund"]
        cached = q.cache.read(f"krfund3:{c}") or {}
        data = cached.get("data") or {}
        fp = paired(fund, data, ctx["expected_session"]) if fund.get("status") != "UNAVAILABLE" else fund
        ff = as_financial(fund) if c in FINANCE_GROUPS else fund
        fb = blanked(fp) if c in FINANCE_GROUPS else fp
        fk = blanked(fund) if c in FINANCE_GROUPS else fund
        rec = {"t": c, "name": ctx.get("name"), "klass": ident.get("industry_class"), "share": fp.get("parent_share"),
               "before": {k: fund.get(k) for k in ("fcf_yield", "ocf_to_ni", "debt_equity", "equity_assets")}, "after": {k: fp.get(k) for k in ("fcf_yield", "ocf_to_ni", "debt_equity", "equity_assets")}}
        for st in ("LONG_TERM", "SWING"):
            a = engine.score(ctx, st, held=False)
            p = pub.get((c, st))
            total += 1
            same += bool(p) and abs(a["score"] - p["score"]) < 0.01
            rec[st] = {"base": {"score": a["score"], "band": a.get("band"), "cov": a.get("coverage")}}
            for tag, f in (("pair", fp), ("fin", ff), ("blank", fk), ("both", fb)):
                b = engine.score({**ctx, "fund": f}, st, held=False)
                rec[st][tag] = {"score": b["score"], "band": b.get("band"), "cov": b.get("coverage")}
        out.append(rec)
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    print("reproduced published", same, "of", total)
    for st in ("LONG_TERM", "SWING"):
        for tag in ("pair", "fin", "blank", "both"):
            d = [abs((r[st][tag]["score"] or 0) - (r[st]["base"]["score"] or 0)) for r in out]
            changed = [(r["name"], r[st]["base"]["band"][:5], r[st][tag]["band"][:5], round(r[st]["base"]["score"], 1), round(r[st][tag]["score"], 1)) for r in out if r[st]["base"]["band"] != r[st][tag]["band"]]
            buy0 = sum("BUY" in r[st]["base"]["band"] for r in out)
            buy1 = sum("BUY" in r[st][tag]["band"] for r in out)
            print(st, tag, "n", len(d), ">=1", sum(x >= 1 for x in d), ">=3", sum(x >= 3 for x in d), ">=5", sum(x >= 5 for x in d), "max", round(max(d), 1), "buy", buy0, "->", buy1, "bands", len(changed))
            print("   ", changed[:40])
    for c in FINANCE_GROUPS:
        r = next(x for x in out if x["t"] == c)
        print(c, r["name"], {st: {k: (round(v["score"], 1), v["band"][:5], round(v["cov"], 3)) for k, v in r[st].items()} for st in ("LONG_TERM", "SWING")})
    top = sorted(out, key=lambda r: -abs(r["LONG_TERM"]["both"]["score"] - r["LONG_TERM"]["base"]["score"]))[:22]
    for r in top:
        print(r["t"], r["name"], "share", None if r["share"] is None else round(r["share"], 2), "L", round(r["LONG_TERM"]["base"]["score"], 1), "->", round(r["LONG_TERM"]["both"]["score"], 1),
              "S", round(r["SWING"]["base"]["score"], 1), "->", round(r["SWING"]["both"]["score"], 1),
              {k: (None if v is None else round(v, 2)) for k, v in r["before"].items()}, {k: (None if v is None else round(v, 2)) for k, v in r["after"].items()})


if __name__ == "__main__":
    main(sys.argv[1])
