"""Experiment 1: calculation integrity on every recorded snapshot.  No return involved."""
import collections, math
from common import *

res = {"sessions": []}
tot = collections.Counter()
worst = []
for market in ("US", "KR"):
    for session, mv in sessions(market):
        d = load(market, session)
        row = {"market": market, "session": session, "model_version": mv, "dup_records": d["_dup"]}
        for strat in ("SWING", "LONG_TERM"):
            n = bad_score = bad_contrib = out_of_range = none_score = bad_wsum = 0
            maxdiff = 0.0
            wsum = collections.Counter()
            for t, s in d[strat].items():
                n += 1
                rows = scored_rows(s) if any(f.get("scored") is False for f in s["factors"]) else [f for f in s["factors"] if f.get("weight")]
                rc = recompute(rows)
                wsum[sum(f["weight"] for f in rows)] += 1
                if s.get("score") is None or rc is None:
                    none_score += (s.get("score") is None) != (rc is None) or 0
                    if s.get("score") is None and rc is None:
                        tot["both_none"] += 1
                    continue
                diff = abs(rc - s["score"])
                maxdiff = max(maxdiff, diff)
                if diff > 1e-9:
                    bad_score += 1
                    worst.append((diff, market, session, strat, t, s["score"], rc))
                for f in s["factors"]:
                    nv = f.get("normalized")
                    if nv is not None and not (0.0 <= nv <= 1.0) or (nv is not None and not math.isfinite(nv)):
                        out_of_range += 1
                    if f.get("contribution") is not None and abs(f["contribution"] - f["weight"] * nv) > 1e-9:
                        bad_contrib += 1
                    if f.get("status") not in QUAL and (nv is not None or f.get("contribution") is not None) and f.get("scored") is not False:
                        tot["nonreal_with_value"] += 1
            row[strat] = {"n": n, "score_mismatch_gt_1e-9": bad_score, "max_abs_diff": maxdiff, "contribution_mismatch": bad_contrib,
                          "normalized_out_of_0_1": out_of_range, "none_disagree": none_score, "weight_sums": dict(wsum)}
            tot["snapshots"] += n; tot["score_mismatch"] += bad_score; tot["contrib_mismatch"] += bad_contrib; tot["out_of_range"] += out_of_range
        res["sessions"].append(row)
        print(market, session, mv, "dup", d["_dup"], {k: (v["n"], v["score_mismatch_gt_1e-9"], f'{v["max_abs_diff"]:.2e}', v["weight_sums"]) for k, v in row.items() if isinstance(v, dict)})
res["total"] = dict(tot)
res["worst"] = sorted(worst, reverse=True)[:10]
print("TOTAL", dict(tot)); print("worst", res["worst"][:5])

# ---- latest session: weights vs config, coverage, conservative score, band consistency
print("\n== latest session checks (2026-11-24, QSF-1.5.2; weights and formulas equal 1.6.0) ==")
latest = {}
for market in ("US", "KR"):
    session = sessions(market)[-1][0]
    d = load(market, session)
    for strat in ("SWING", "LONG_TERM"):
        prof = config.profile_for(market, strat)
        want = {fid: w for dm in prof["domains"].values() for fid, w in dm.items()}
        never = config.NEVER_AVAILABLE.get((market, strat), ())
        c = collections.Counter()
        for t, s in d[strat].items():
            c["n"] += 1
            got = {f["factor"]: f["weight"] for f in s["factors"] if f.get("scored") is not False}
            if got != want:
                c["weights_differ_from_config"] += 1
            rows = [f for f in s["factors"] if f.get("scored") is not False]
            tw = sum(f["weight"] for f in rows if f["status"] in QUAL); tc = sum(f["weight"] * f["normalized"] for f in rows if f["status"] in QUAL)
            app = sum(f["weight"] for f in rows if f["status"] != "NOT_APPLICABLE")
            eff = sum(f["weight"] * (1.0 if f["status"] == "REAL" else 0.5) for f in rows if f["status"] in QUAL)
            cov = eff / app if app else 0.0
            if abs(cov - (s.get("coverage") or 0)) > 1e-9:
                c["coverage_mismatch"] += 1
            mw = sum(f["weight"] for f in rows if f["status"] == "MISSING" and f["factor"] not in never)
            cons = None if s["score"] is None or not (tw + mw) else 100 * (tc + 0.5 * mw) / (tw + mw)
            if (cons is None) != (s.get("conservative_score") is None) or (cons is not None and abs(cons - s["conservative_score"]) > 1e-9):
                c["conservative_mismatch"] += 1
            # band vs score
            if s["score"] is not None:
                plain = engine.classify(s["score"])["band"]
                if plain != s["band"]:
                    why = "held_back" if s.get("band_held_back") else "deal_pin" if s.get("deal_held") else "buffer_67_70" if (67 <= s["score"] < 70 and s["band"] == "BUY_CANDIDATE") else "UNEXPLAINED"
                    c["band_differs:" + why] += 1
                # action vs band
                if s["action"] == "BUY" and s["band"] not in engine.BUY_CODES:
                    c["BUY_action_outside_buy_band"] += 1
                if s["band"] in engine.BUY_CODES and s["action"] not in ("BUY", "BLOCKED", "INSUFFICIENT_DATA", "HOLD"):
                    c["buy_band_without_buy_action"] += 1
            st = collections.Counter(f["status"] for f in rows)
            for k, v in st.items():
                c["status:" + str(k)] += v
        latest[f"{market}_{strat}"] = dict(c)
        print(market, strat, session, "weight sum", sum(want.values()), dict(c))
res["latest"] = latest
dump("s01_integrity.json", res)
