"""Experiment 1 (direction): for every factor, the rank correlation between each stored raw figure and the stored normalised value on
the latest day, against the direction written in factors.py.  And Experiment 9: where the lines fall in each profile.  No return."""
import collections
from common import *
EXPECT = {  # +1 higher raw is better, -1 lower raw is better, 0 not monotone by design / not an input
    "ma20": 0, "ma50": 0, "ma200": 0, "ma50_slope": 1, "ma200_slope": 1, "percentile": 1, "rel_126": 1, "rsi": 0, "macd_hist_pct": 1, "dist_high": 1, "volume_ratio": 0, "gap_today": 0, "breakout": 1, "held_gap": 0,
    "bandwidth": 0, "bandwidth_pct": -1, "ret_12_1": 1, "pos_month_share": 1, "rev_growth": 1, "eps_growth": 1, "ocf_to_ni": 1, "roe": 1, "op_margin": 1, "gross_margin": 1, "roe_years_positive": 1,
    "debt_equity": -1, "current_ratio": 1, "equity_assets": 1, "fcf_margin": 1, "fcf_years_positive": 1, "pe": 0, "pb": -1, "fcf_yield": 1, "rev_cagr3": 1, "eps_cagr3": 1, "share_change": -1,
    "reward_risk": 1, "stop": 0, "target": 0, "cost_pct": 0, "atr_pct": -1, "hist_vol": -1, "adv_value": 1, "max_drawdown_252": 1, "max_gap_60": -1, "interest_cover": 1, "cash_debt": 1, "downside_vol": -1,
    "sessions": 1, "negative": -1, "positive": 1, "window_days": 0, "insider_pct": 1, "returns_capital": 1, "open_market_buy": 1, "open_market_sell": -1, "excluded_transactions": 0, "filings": 0, "overdue": 0}
res = {"direction": {}, "lines": {}}
wrong = []; checked = 0
for market in ("US", "KR"):
    session = sessions(market)[-1][0]
    for strat in ("SWING", "LONG_TERM"):
        snaps = load(market, session)[strat]
        cols = collections.defaultdict(lambda: ([], []))
        for s in snaps.values():
            for f in s["factors"]:
                if f.get("scored") is False or f["status"] not in QUAL or not isinstance(f.get("raw"), dict):
                    continue
                for k, v in f["raw"].items():
                    if isinstance(v, bool):
                        v = float(v)
                    if isinstance(v, (int, float)):
                        cols[(f["factor"], k)][0].append(float(v)); cols[(f["factor"], k)][1].append(f["normalized"])
        key = f"{market}_{strat}"; res["direction"][key] = {}
        for (fid, k), (x, y) in sorted(cols.items()):
            if len(x) < 30:
                continue
            r = spearman(np.array(x), np.array(y)); e = EXPECT.get(k)
            res["direction"][key][f"{fid}.{k}"] = {"rho": r, "expected": e, "n": len(x)}
            if e in (1, -1) and not np.isnan(r):
                checked += 1
                if r * e < 0:
                    wrong.append((key, fid, k, round(r, 3), e, len(x)))
        # ---- lines
        v = np.array([s["score"] for s in snaps.values() if s["score"] is not None])
        res["lines"][key] = {"session": session, "n": len(v), "min": float(v.min()), "p20": float(np.percentile(v, 20)), "median": float(np.median(v)), "p80_top_fifth_cut": float(np.percentile(v, 80)), "p90": float(np.percentile(v, 90)), "max": float(v.max()),
                             "share_ge80": float((v >= 80).mean()), "share_ge70": float((v >= 70).mean()), "share_55_70": float(((v >= 55) & (v < 70)).mean()), "share_40_55": float(((v >= 40) & (v < 55)).mean()), "share_lt40": float((v < 40).mean()),
                             "theoretical_max_if_all_factors_1": 100.0}
        print(key, {k: (round(x, 3) if isinstance(x, float) else x) for k, x in res["lines"][key].items()})
print("direction: figures checked", checked, "| against the written direction:", wrong)
res["direction_checked"] = checked; res["direction_wrong"] = wrong
# KR swing: the highest score of every recorded day since the technical domain left it
mx = []
for s, v in sessions("KR"):
    sn = load("KR", s)["SWING"]
    if any(f.get("scored") is False and f["domain"] == "TECHNICAL" for f in next(iter(sn.values()))["factors"]):
        vals = [x["score"] for x in sn.values() if x["score"] is not None]
        mx.append((s, v, round(max(vals), 1), sum(1 for x in vals if x >= 70), sum(1 for x in vals if x >= 55)))
res["kr_swing_daily_max"] = mx
print("KR swing (technical out): session, version, max score, n>=70, n>=55:", mx)
dump("s01c_direction_lines.json", res)
