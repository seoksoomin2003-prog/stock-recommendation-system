"""Agent 1, experiments E2-E4 (no return).
E2: buffer candidates on the newest session.  E3: stored scan file vs ledger; rank file vs ledger relative-strength percentile.
E4: per profile and factor on the newest session: status counts, share at 0 / at 1, partial inputs; effective weight shares."""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, ".")
from terminal.qsf import config, engine
from terminal.qsf.ledger import Ledger

OUT = Path("reports/score_reliability_audit_2026_11_25/scratch_1/e2_checks.json")
led = Ledger(Path("."))
rows = led._live_rows()
def sess(market, session):
    out = []
    for r in rows:
        if r["market"] == market and r["session"] == session:
            out += led._load(r)
    return out
res = {}
for m in ("US", "KR"):
    last, prev = "2026-11-24", "2026-11-23"
    a, b = sess(m, last), sess(m, prev)
    pb = {(s["ticker"], s["strategy"]): s for s in b}
    for st in config.STRATEGIES:
        cur = [s for s in a if s["strategy"] == st]
        cand = [s for s in cur if s.get("score") is not None and 67 <= s["score"] < 70]
        was = [s for s in cand if (pb.get((s["ticker"], st)) or {}).get("band") in engine.BUY_CODES]
        kept = [s for s in was if s.get("band") == "BUY_CANDIDATE"]
        notkept = [(s["ticker"], round(s["score"], 2), s.get("band"), s.get("actionability"), pb[(s["ticker"], st)].get("actionability"), s.get("band_held_back"), s.get("deal_held")) for s in was if s.get("band") != "BUY_CANDIDATE"]
        res[f"E2_buffer_{m}_{st}"] = {"score_67_70": len(cand), "prev_in_buy_band": len(was), "kept": len(kept), "not_kept": notkept}
    # E3 scan file vs ledger
    scan = json.load(open(f"data/qsf/latest_{m}.json"))
    lg = {(s["ticker"], s["strategy"]): s for s in a}
    gaps, band_diff, missing = [], 0, 0
    for r in scan["rows"]:
        s = lg.get((r["ticker"], r["strategy"]))
        if s is None:
            missing += 1; continue
        if r["score"] is not None and s["score"] is not None:
            gaps.append(abs(r["score"] - s["score"]))
        band_diff += r["band"] != s["band"]
    ranks = json.load(open(f"data/qsf/ranks_{m}.json"))
    ordered = sorted(ranks["returns"].values())
    rg, nrs, fallback = [], 0, 0
    for s in a:
        f = next((f for f in s["factors"] if f["factor"] == "relative_strength"), None)
        if not f or f.get("normalized") is None:
            continue
        nrs += 1
        raw = f.get("raw") or {}
        if raw.get("percentile") is None:
            fallback += 1; continue
        t = s["ticker"]
        if t in ranks["returns"]:
            mine = float(np.searchsorted(ordered, ranks["returns"][t], side="right") / len(ordered))
            rg.append(abs(mine - raw["percentile"]))
    res[f"E3_{m}"] = {"scan_session": scan["session"], "scan_rows": len(scan["rows"]), "ledger_rows": len(a), "not_in_ledger": missing, "max_score_gap": max(gaps) if gaps else None, "band_differs": band_diff,
                      "ranks_session": ranks["session"], "ranks_n": len(ordered), "rs_rows": nrs, "rs_from_benchmark_fallback": fallback, "rs_rank_compared": len(rg), "rs_rank_max_gap": max(rg) if rg else None}
    # E4 factor status table
    for st in config.STRATEGIES:
        cur = [s for s in a if s["strategy"] == st]
        tab = {}
        stat = defaultdict(Counter); vals = defaultdict(list); partial = Counter(); refw = {}
        for s in cur:
            for f in s["factors"]:
                k = f["factor"]
                stat[k][f["status"]] += 1
                refw[k] = (f["weight"], f.get("reference_weight"), f.get("scored", True), f["domain"])
                if f.get("normalized") is not None:
                    vals[k].append(f["normalized"])
        for k in stat:
            v = np.array(vals[k]) if vals[k] else np.array([])
            tab[k] = {"domain": refw[k][3], "weight": refw[k][0], "reference_weight": refw[k][1], "scored": refw[k][2], "status": dict(stat[k]),
                      "at0": float((v <= 1e-12).mean()) if len(v) else None, "at1": float((v >= 1 - 1e-12).mean()) if len(v) else None,
                      "median": float(np.median(v)) if len(v) else None, "distinct": int(len(set(np.round(v, 6)))) if len(v) else 0}
        # effective weight: mean available weight per domain / mean total available weight
        dom = defaultdict(list); tot = []
        for s in cur:
            w = defaultdict(float)
            for f in s["factors"]:
                if f.get("scored") is False or f.get("normalized") is None:
                    continue
                w[f["domain"]] += f["weight"]
            t = sum(w.values())
            if t:
                tot.append(t)
                for d in config.DOMAINS:
                    dom[d].append(w[d] / t)
        sc = np.array([s["score"] for s in cur if s.get("score") is not None])
        res[f"E4_{m}_{st}"] = {"n": len(cur), "factors": tab, "mean_available_points": float(np.mean(tot)), "min_available_points": float(np.min(tot)), "max_available_points": float(np.max(tot)),
                               "mean_domain_share": {d: float(np.mean(v)) for d, v in dom.items()},
                               "score": {"min": float(sc.min()), "p10": float(np.percentile(sc, 10)), "median": float(np.median(sc)), "p90": float(np.percentile(sc, 90)), "max": float(sc.max()), "n70": int((sc >= 70).sum()), "n80": int((sc >= 80).sum())},
                               "confidence": dict(Counter(s.get("confidence") for s in cur)), "actionability": dict(Counter(s.get("actionability") for s in cur)),
                               "bands": dict(Counter(s.get("band") for s in cur)), "held_back": sum(1 for s in cur if s.get("band_held_back")), "deal_held": sum(1 for s in cur if s.get("deal_held")),
                               "entry_status": dict(Counter(s.get("entry_status") for s in cur))}
OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1))
for k, v in res.items():
    if k.startswith("E4"):
        print(k, {x: v[x] for x in v if x != "factors"})
        for f, t in v["factors"].items():
            print("   ", f, t)
    else:
        print(k, v)
