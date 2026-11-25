"""Experiment 8: can a recorded score be rebuilt from the ledger alone?
(a) composite from the stored normalised values: s01 (exact).  (b) here: each factor's normalised value recomputed by calling the
live factor function (terminal/qsf/factors.py, QSF-1.6.0) on the stored RAW figures of the latest recorded session; a mismatch is
either a hidden input the ledger does not keep or a formula that changed.  (c) relative strength without the scan's rank file
(rank basis NO_SCAN): the size of the score difference, approximated from the stored 6-month figure.  No return involved."""
import collections, json
from common import *

def ctx_from(s, f):
    """A context holding only what the ledger kept for this factor."""
    raw = f.get("raw") or {}
    fid = f["factor"]
    c = {"market": s["market"], "tech": {"date": s["data_date"], "close": s["price"]}, "levels": {}, "fund": None, "events": None, "earnings": {}, "regime": {}}
    t = c["tech"]
    if fid in ("trend_structure", "momentum", "breakout_volume", "volatility_structure", "long_trend", "momentum_persistence", "atr_risk", "liquidity", "drawdown_gap", "downside_drawdown"):
        t.update(raw)
    if fid == "relative_strength":
        t.update({"rel_126": raw.get("rel_126"), "rel_63": raw.get("rel_63")}); c["rs_rank"] = raw.get("percentile"); c["bench_name"] = raw.get("benchmark")
    if fid == "risk_reward":
        c["levels"] = {"status": "REAL", "reward_risk": raw.get("reward_risk"), "stop": raw.get("stop"), "target": raw.get("target"), "round_trip_cost_pct": raw.get("cost_pct"), "target_method": ""}
    if fid in ("earnings_revenue_quality", "profitability", "balance_sheet", "cash_flow_quality", "valuation", "business_quality", "growth_quality", "free_cash_flow", "balance_dilution",
               "financial_resilience", "leverage", "capital_allocation"):
        fin = "equity_assets" in raw or (fid == "valuation" and "fcf_yield" not in raw)
        c["fund"] = {"status": f["status"], "source": f.get("source"), "filed": f.get("as_of"), "is_financial": fin, **raw}
    if fid == "earnings_calendar":
        c["earnings"] = {"sessions": raw.get("sessions"), "date": raw.get("next_earnings"), "basis": raw.get("basis"), "overdue": raw.get("overdue"), "from": raw.get("from")}
    if fid in ("material_disclosures", "material_events"):
        c["events"] = {"status": "REAL", "source": "", "negative": [{"label": ""}] * int(raw.get("negative") or 0), "positive": [{"label": ""}] * int(raw.get("positive") or 0), "window_days": raw.get("window_days")}
    if fid == "governance":
        c["events"] = {"status": "REAL", "source": "", "governance": [{"label": x} for x in raw.get("issues") or []]}
    if fid == "insider_activity":
        c["events"] = {"status": "REAL", "source": "", "insider": raw}
    if fid == "insider_ownership":
        c["events"] = {"status": "REAL", "source": "", "insider": raw.get("insider") or {}}; c["fund"] = {"insider_pct": raw.get("insider_pct")}
    return c

res = {}
for market in ("US", "KR"):
    session = sessions(market)[-1][0]
    for strat in ("SWING", "LONG_TERM"):
        snaps = load(market, session)[strat]
        per = collections.defaultdict(collections.Counter); worst = collections.defaultdict(float); ex = {}
        rebuilt_ok = rebuilt_n = 0; maxd = 0.0
        for t, s in snaps.items():
            rows = []
            good = True
            for f in s["factors"]:
                if f.get("scored") is False or f["status"] not in QUAL:
                    if f.get("scored") is not False:
                        rows.append(f)
                    continue
                try:
                    o = factors.CALC[f["factor"]](ctx_from(s, f))
                    nv = o.get("normalized") if o.get("status") in QUAL else None
                except Exception as e:
                    nv = None
                d = None if nv is None else abs(nv - f["normalized"])
                kind = "exact" if d is not None and d < 1e-9 else "differs" if d is not None else "not_rebuildable"
                per[f["factor"]][kind] += 1
                if kind != "exact":
                    good = False
                    if d is not None and d > worst[f["factor"]]:
                        worst[f["factor"]] = d; ex[f["factor"]] = {"ticker": t, "stored": f["normalized"], "rebuilt": nv, "raw": f.get("raw")}
                rows.append({**f, "normalized": nv if nv is not None else f["normalized"]})
            if s["score"] is not None:
                rebuilt_n += 1
                rc = recompute(rows)
                dd = abs(rc - s["score"]); maxd = max(maxd, dd); rebuilt_ok += dd < 1e-6
        key = f"{market}_{strat}"
        res[key] = {"session": session, "model_version_recorded": next(iter(snaps.values()))["model_version"], "factors": {k: dict(v) for k, v in per.items()}, "worst_difference": dict(worst), "examples": ex,
                    "scores_rebuilt_exactly_from_raw": rebuilt_ok, "scores": rebuilt_n, "max_score_difference": maxd}
        print(f"\n=== {key} {session}: scores rebuilt from RAW figures within 1e-6: {rebuilt_ok}/{rebuilt_n}, max difference {maxd:.2f}")
        for k, v in per.items():
            if v["differs"] or v["not_rebuildable"]:
                print(f"   {k:26s} exact {v['exact']:4d} differs {v['differs']:4d} not rebuildable {v['not_rebuildable']:4d} worst {worst[k]:.3f}  e.g. {json.dumps(ex.get(k), ensure_ascii=False, default=str)[:260]}")
        # (c) rank basis NO_SCAN: relative strength by the benchmark formula.  The ledger keeps rel_126 only (not rel_63), so this is an approximation.
        diffs = []
        for t, s in snaps.items():
            rs = next((f for f in s["factors"] if f["factor"] == "relative_strength" and f.get("scored") is not False and f["status"] in QUAL), None)
            if rs is None or s["score"] is None or (rs.get("raw") or {}).get("rel_126") is None:
                continue
            alt = factors.ramp(rs["raw"]["rel_126"], -0.15, 0.20)
            rows = [({**f, "normalized": alt} if f is rs else f) for f in s["factors"] if f.get("scored") is not False]
            diffs.append((recompute(rows) - s["score"], s["score"], recompute(rows)))
        if diffs:
            d = np.array([x[0] for x in diffs]); a = np.array([x[1] for x in diffs]); b = np.array([x[2] for x in diffs])
            res[key]["no_scan_rank_basis"] = {"n": len(d), "mean_change": float(d.mean()), "mean_abs_change": float(np.abs(d).mean()), "max_abs_change": float(np.abs(d).max()), "rho": spearman(a, b),
                                              "ge70_scan": int((a >= 70).sum()), "ge70_no_scan": int((b >= 70).sum()), "crossing_70_either_way": int(((a >= 70) != (b >= 70)).sum())}
            print("   NO_SCAN (benchmark formula, approx.):", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res[key]["no_scan_rank_basis"].items()})

# (d) stored latest scan equals the ledger
for market in ("US", "KR"):
    d = json.load(open(f"data/qsf/latest_{market}.json"))
    snaps = load(market, d["session"])
    diff = n = 0
    for r in d["rows"]:
        s = snaps[r["strategy"]].get(r["ticker"])
        n += 1
        if s is None or (s["score"] is None) != (r["score"] is None) or (s["score"] is not None and abs(s["score"] - r["score"]) > 0.0051) or s["band"] != r["band"]:
            diff += 1
    res[f"latest_file_{market}"] = {"session": d["session"], "rows": n, "rows_differing_from_ledger": diff, "model_version": d["model_version"]}
    print(f"latest_{market}.json vs ledger ({d['session']}, {d['model_version']}): rows {n}, differing {diff}")
res["ledger_verify"] = LED.verify()
print("ledger hash chain:", res["ledger_verify"], "| live config MODEL_VERSION:", config.MODEL_VERSION, "| sessions recorded under it:", sum(1 for m in ("US", "KR") for s, v in sessions(m) if v == config.MODEL_VERSION))
dump("s08_repro.json", res)
