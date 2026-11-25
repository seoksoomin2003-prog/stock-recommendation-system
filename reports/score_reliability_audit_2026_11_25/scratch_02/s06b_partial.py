"""Experiment 6 (detail): a factor built from part of its figures.  The conservative score reads only WHOLE factors that are missing;
a figure missing inside a factor leaves the factor's mean to its other figures.  Here: US long-term, latest day.  For stocks that
HAVE the figure, the factor is recomputed without it (live factor function on stored raw figures) to see which way its absence moves
a score.  Also: the confidence label recomputed from the recorded coverage figures.  No return involved."""
import collections
from common import *
res = {}
session = sessions("US")[-1][0]
snaps = load("US", session)["LONG_TERM"]
for fid, key in (("business_quality", "gross_margin"), ("financial_resilience", "interest_cover"), ("valuation", "fcf_yield"), ("growth_quality", "eps_cagr3")):
    d_f, d_s, cross_up, cross_dn, n_have, n_miss = [], [], 0, 0, 0, 0
    for t, s in snaps.items():
        f = next((x for x in s["factors"] if x["factor"] == fid and x["status"] in QUAL), None)
        if f is None or s["score"] is None or "equity_assets" in f["raw"]:
            continue
        if f["raw"].get(key) is None:
            n_miss += 1; continue
        n_have += 1
        fund = {"status": "REAL", "source": "", "filed": None, "is_financial": False, **f["raw"], key: None}
        o = factors.CALC[fid]({"fund": fund})
        if o.get("status") not in QUAL:
            continue
        rows = [({**x, "normalized": o["normalized"]} if x is f else x) for x in s["factors"] if x.get("scored") is not False]
        new = recompute(rows)
        d_f.append(o["normalized"] - f["normalized"]); d_s.append(new - s["score"])
        cross_up += s["score"] < 70 <= new; cross_dn += new < 70 <= s["score"]
    d_f, d_s = np.array(d_f), np.array(d_s)
    res[f"{fid}.{key}"] = {"stocks_with_figure": n_have, "stocks_without_figure(non-financial)": n_miss, "factor_change_mean": float(d_f.mean()), "score_change_mean": float(d_s.mean()),
                           "score_change_p5": float(np.percentile(d_s, 5)), "score_change_p95": float(np.percentile(d_s, 95)), "score_change_max": float(d_s.max()), "share_rising": float((d_s > 0).mean()),
                           "newly_ge70": int(cross_up), "no_longer_ge70": int(cross_dn)}
    print(f"US long, {fid} without {key}: have {n_have}, lack {n_miss}; factor {d_f.mean():+.3f}, score mean {d_s.mean():+.2f} (5%..95%: {np.percentile(d_s,5):+.2f}..{np.percentile(d_s,95):+.2f}, max {d_s.max():+.2f}), rising {100*(d_s>0).mean():.0f}%, newly >=70 {cross_up}, no longer >=70 {cross_dn}")

# confidence label from the recorded coverage figures
conf = collections.Counter()
for market in ("US", "KR"):
    session = sessions(market)[-1][0]
    for strat in ("SWING", "LONG_TERM"):
        dist = collections.Counter(); mism = 0; lows = collections.Counter()
        for t, s in load(market, session)[strat].items():
            dist[s["confidence"]] += 1
            if s["confidence"] == "INSUFFICIENT" or s.get("input_coverage") is None:
                continue
            m = min(s["coverage"], s["input_coverage"])
            want = next((lab for lo, lab in config.CONFIDENCE_BANDS if m >= lo), "LOW")
            stale = any(f["status"] == "STALE" for f in s["factors"] if f.get("scored") is not False)
            if stale and want == "HIGH":
                want = "MEDIUM"
            if want != s["confidence"]:
                mism += 1; lows[(want, s["confidence"])] += 1
        res[f"confidence_{market}_{strat}"] = {"distribution": dict(dist), "label_differs_from_coverage_rule": mism, "which": {str(k): v for k, v in lows.items()}}
        print(market, strat, "confidence:", dict(dist), "| differs from min(coverage, input coverage) rule:", mism, dict(lows))
dump("s06b_partial.json", res)
