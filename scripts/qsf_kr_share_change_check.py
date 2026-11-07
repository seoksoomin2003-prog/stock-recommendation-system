"""Korean one-year share change: where the price-based figure misreads corporate events, and what candidate rules would do to the live score.
Measurement only: no record, no published file, no return.  Needs research_data/kr_share_probe/actions (scripts/qsf_kr_corp_action_probe.py actions).
Usage: python scripts/qsf_kr_share_change_check.py out.json"""
import gzip
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, ".")
from utils import runtime_config  # noqa: E402

runtime_config.load_local_env()
from terminal.qsf import engine, krx_history  # noqa: E402
from terminal.qsf import research_kr as kr  # noqa: E402
from terminal.qsf.service import QSF  # noqa: E402

ACTIONS = Path("research_data/kr_share_probe/actions")
# A capital reduction is left out: a cancellation of treasury shares is a real fall, and a share consolidation already shows no change here.
RESHAPE = ("cmpDvDecsn", "cmpDvmgDecsn", "cmpMgDecsn", "stkExtrDecsn")
MIN_EVENT_CHANGE, MIN_CONFLICT = 0.02, 0.05
DILUTION_EXIT = 0.10


def bets(C):
    ev = np.clip(np.linalg.eigvalsh(np.cov(C.T))[::-1], 0, None)
    return round(float(ev.sum() ** 2 / (ev ** 2).sum()), 2)


def events_of(code):
    out = []
    for e in RESHAPE + ("piicDecsn",):
        p = ACTIONS / f"{code}_{e}.json"
        if p.exists():
            for r in json.loads(p.read_text(encoding="utf-8")).get("list") or []:
                n = str(r.get("rcept_no") or "")
                out.append({"type": e, "date": f"{n[:4]}-{n[4:6]}-{n[6:8]}", "method": r.get("dv_mth") or r.get("mg_mth") or r.get("cr_mth")})
    return out


def _clean_adj(rows, day, then):
    a = {r["date"]: r.get("adj_close") for r in rows or []}
    if not a.get(day) or not a.get(then):
        return None
    return a[day] / a[then]


def main(path):
    base = Path(".")
    live = json.load(open("data/qsf/latest_KR.json", encoding="utf-8"))
    pub = {(r["ticker"], r["strategy"]): r for r in live["rows"]}
    codes = sorted({t for t, _ in pub})
    px = kr._load(base)
    pos = {s: i for i, s in enumerate(px.symbols)}
    i = len(px.dates) - 1
    day, then = str(px.dates[i])[:10], str(px.dates[i - 252])[:10]
    cap, adj = px.data["cap"], px.data["adj_close"]
    now, old = krx_history.listed_shares(base / "research_data" / "krx", day), krx_history.listed_shares(base / "research_data" / "krx", then)
    print("window", then, day, "listed shares", len(now), len(old))
    start = (date.fromisoformat(then) - timedelta(days=180)).isoformat()

    q = QSF(base)
    bars = json.load(gzip.open("data/qsf/bars_KR.json.gz", "rt"))
    bench = q._history(["^KS11", "^KQ11"])["data"] or {}
    pre = q._prefetch(list(bars), {**bars, **bench}, "^KS11", live["session"])
    rows, same = [], 0
    contrib = {"none": [], "raw": [], "rule": []}
    for c in codes:
        ident = q._kr_identity(c)
        pre[c]["bench"] = bench.get("^KQ11" if ident and ident.get("market") == "KOSDAQ" else "^KS11") or []
        ctx = q.context(c, "KR", pre[c])
        if ctx.get("error"):
            continue
        j = pos.get(c)
        a = None
        if j is not None and all(np.isfinite(x) and x > 0 for x in (cap[i, j], cap[i - 252, j], adj[i, j], adj[i - 252, j])):
            a = float((cap[i, j] / cap[i - 252, j]) / (adj[i, j] / adj[i - 252, j]) - 1)
        b = float(now[c] / old[c] - 1) if now.get(c) and old.get(c) else None
        ev = events_of(c)
        reshape = [e for e in ev if e["type"] in RESHAPE and e["date"] >= start]
        conflict = a is not None and b is not None and abs(a) >= MIN_CONFLICT and a * b < 0
        event = a is not None and bool(reshape) and abs(a) >= MIN_EVENT_CHANGE
        ya = _clean_adj(bars.get(c), day, then)
        rec = {"t": c, "name": ctx.get("name"), "a": a, "b": b, "reshape": reshape, "rights": [e["date"] for e in ev if e["type"] == "piicDecsn" and e["date"] >= then], "conflict": conflict, "event": event,
               "a_yahoo": None if ya is None or a is None else float((cap[i, j] / cap[i - 252, j]) / ya - 1)}
        fund = ctx.get("fund") or {}
        rec["fund_ok"] = fund.get("status") in ("REAL", "STALE")
        for tag, ch in (("none", None), ("raw", a), ("rule", None if event or conflict else a)):
            f = {**fund, "share_change": ch} if rec["fund_ok"] else fund
            s = engine.score({**ctx, "fund": f}, "LONG_TERM", held=False)
            rec[tag] = {"score": s["score"], "band": s["band"]}
            contrib[tag].append({x["factor"]: x.get("contribution") or 0.0 for x in s["factors"]})
        same += abs(rec["none"]["score"] - pub[(c, "LONG_TERM")]["score"]) < 0.01
        sw = engine.score({**ctx, "fund": {**fund, "share_change": a} if rec["fund_ok"] else fund}, "SWING", held=False)
        rec["swing_same"] = abs(sw["score"] - pub[(c, "SWING")]["score"]) < 0.01
        rows.append(rec)
    print("names", len(rows), "live score reproduced", same, "| value a", sum(r["a"] is not None for r in rows), "b", sum(r["b"] is not None for r in rows), "| reshape event", sum(bool(r["reshape"]) for r in rows), "conflict", sum(r["conflict"] for r in rows), "blanked", sum(r["event"] or r["conflict"] for r in rows), "swing unchanged", sum(r["swing_same"] for r in rows))
    types = {}
    for r in rows:
        for e in r["reshape"]:
            types[e["type"]] = types.get(e["type"], 0) + 1
    print("event types", types)
    names = sorted(contrib["none"][0])
    print("weighted axes", {t: bets(np.array([[c[n] for n in names] for c in contrib[t]])) for t in contrib})
    yy = [r for r in rows if r["a_yahoo"] is not None]
    gaps = np.abs([r["a_yahoo"] - r["a"] for r in yy])
    print("yahoo adjusted price against KRX adjusted: names", len(yy), "gap >1%", int((gaps > .01).sum()), ">5%", int((gaps > .05).sum()), "max", round(float(gaps.max()), 3), "worst", [(r["t"], round(r["a"], 3), round(r["a_yahoo"], 3)) for r in sorted(yy, key=lambda r: -abs(r["a_yahoo"] - r["a"]))[:8]])
    for tag in ("raw", "rule"):
        d = np.array([r[tag]["score"] - r["none"]["score"] for r in rows])
        ab = np.abs(d)
        buy0 = {r["t"] for r in rows if r["none"]["band"] == "BUY_CANDIDATE"}
        buy1 = {r["t"] for r in rows if r[tag]["band"] == "BUY_CANDIDATE"}
        kept = [r for r in rows if r[tag]["score"] != r["none"]["score"] or (tag == "raw")]
        print(f"{tag}: >=1 {(ab >= 1).sum()} >=3 {(ab >= 3).sum()} max {ab.max():.2f} band moves {sum(r[tag]['band'] != r['none']['band'] for r in rows)} buy {len(buy0)}->{len(buy1)} out {sorted(buy0 - buy1)} in {sorted(buy1 - buy0)}")
    print("--- largest |a| (name, a, b, reshape types, conflict, rights)")
    for r in sorted((r for r in rows if r["a"] is not None), key=lambda r: -abs(r["a"]))[:32]:
        print(r["t"], r["name"], round(r["a"], 3), None if r["b"] is None else round(r["b"], 3), sorted({e["type"] for e in r["reshape"]}), r["event"] or r["conflict"], len(r["rights"]))
    print("--- reshape events with small |a|", [(r["t"], r["name"], round(r["a"], 3)) for r in rows if r["reshape"] and r["a"] is not None and abs(r["a"]) < 0.02][:25])
    print("--- conflict without event", [(r["t"], r["name"], round(r["a"], 3), round(r["b"], 3)) for r in rows if r["conflict"] and not r["reshape"]])
    v = [r for r in rows if r["a"] is not None]
    print("blanked", [(r["t"], r["name"], round(r["a"], 3), round(r["b"], 3), sorted({e["type"] for e in r["reshape"]})) for r in rows if r["event"] or r["conflict"]])
    print("rule band moves", [(r["t"], r["name"], round(r["none"]["score"], 1), round(r["rule"]["score"], 1), r["none"]["band"], r["rule"]["band"]) for r in rows if r["rule"]["band"] != r["none"]["band"]])
    for tag, f in (("raw", lambda r: True), ("rule", lambda r: not r["event"] and not r["conflict"])):
        print("exit dilution above 10%", tag, [(r["t"], r["name"], round(r["a"], 3)) for r in v if f(r) and r["a"] > DILUTION_EXIT][:40])
    json.dump(rows, open(path, "w", encoding="utf-8"), ensure_ascii=False, default=float)


if __name__ == "__main__":
    main(sys.argv[1])
