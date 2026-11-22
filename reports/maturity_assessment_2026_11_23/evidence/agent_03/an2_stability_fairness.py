"""Agent 03, analysis 2: system test C (ranking stability), system test D (industry fairness), the conservative score and the
stance presets, on the 2026-11-20 session scored by today's code (big/cards_151.json).  Scores and factor values only: no return,
IC or performance figure.  A random-factor baseline is simulated on random numbers.
"""
import json, sys, copy
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
REPO = HERE.resolve().parents[3]
sys.path.insert(0, str(REPO))
from terminal.qsf import config, factors, stance, technicals

D = json.loads((HERE / "big" / "cards_151.json").read_text(encoding="utf-8"))
RNG = np.random.default_rng(20261123)
OUT = {}
BUY = ("BUY_CANDIDATE", "STRONG_BUY_CANDIDATE")


def frame(market, strategy):
    cards = [c for c in D[market]["cards"].values() if c["strategy"] == strategy and c["score"] is not None]
    prof = config.profile_for(market, strategy)
    w = pd.Series({f: wt for d in prof["domains"].values() for f, wt in d.items()}, dtype=float)
    X = pd.DataFrame({c["ticker"]: {f["factor"]: f["normalized"] for f in c["factors"] if f.get("scored") is not False and f["status"] in ("REAL", "STALE")} for c in cards}).T.reindex(columns=list(w.index)).astype(float)
    s = pd.Series({c["ticker"]: c["score"] for c in cards}, dtype=float)
    return cards, X, w, s


def score_of(X, w):
    return 100 * (X.fillna(0) * w).sum(axis=1) / (X.notna() * w).sum(axis=1)


def rho(a, b):
    return float(pd.concat([a, b], axis=1).corr(method="spearman").iloc[0, 1])


def keep(a, b, n=20):
    return len(set(a.nlargest(n).index) & set(b.nlargest(n).index))


def cmp(base, new, line=70.0):
    b0, b1 = set(base.index[base >= line]), set(new.index[new >= line])
    return {"rho": round(rho(base, new), 4), "top20_kept": keep(base, new), "buy_n": len(b1), "buy_kept": len(b0 & b1), "buy_in": len(b1 - b0), "buy_out": len(b0 - b1),
            "max_abs_move": round(float((new - base).abs().max()), 2), "median_abs_move": round(float((new - base).abs().median()), 3)}


# ------------------------------------------------------------------ test C
for market in ("US", "KR"):
    for strategy in ("SWING", "LONG_TERM"):
        key = f"{market}_{strategy}"
        cards, X, w, s = frame(market, strategy)
        o = {"n": len(s), "buy_n": int((s >= 70).sum())}
        # (a) weights +-20% (uniform multipliers per factor), 500 draws
        res = []
        for _ in range(500):
            w2 = w * RNG.uniform(0.8, 1.2, len(w))
            res.append(cmp(s, score_of(X, w2)))
        r = pd.DataFrame(res)
        o["weights_pm20"] = {"rho_p5": round(float(r["rho"].quantile(.05)), 4), "rho_min": round(float(r["rho"].min()), 4), "top20_p5": int(r["top20_kept"].quantile(.05)),
                             "buy_n_p5_p50_p95": [int(r["buy_n"].quantile(q)) for q in (.05, .5, .95)], "buy_kept_p5": int(r["buy_kept"].quantile(.05)),
                             "crossers_p50_p95": [int((r["buy_in"] + r["buy_out"]).quantile(q)) for q in (.5, .95)], "max_move_p95": round(float(r["max_abs_move"].quantile(.95)), 2)}
        # the same on independent random factors under the same weights and the same marginal spread (baseline)
        base = []
        for _ in range(100):
            Xr = pd.DataFrame(RNG.uniform(0, 1, X.shape), index=X.index, columns=X.columns)
            sr = score_of(Xr, w)
            base.append(rho(sr, score_of(Xr, w * RNG.uniform(0.8, 1.2, len(w)))))
        o["weights_pm20_random_baseline_rho_p5"] = round(float(np.quantile(base, .05)), 4)
        # (b) drop one factor at a time
        drops = {}
        for f in w.index:
            if X[f].notna().sum() == 0:
                drops[f] = {"note": "no data for any stock: dropping changes nothing"}
                continue
            drops[f] = cmp(s, score_of(X.drop(columns=f), w.drop(f)))
        o["drop_one"] = drops
        worst = min((v for v in drops.values() if "rho" in v), key=lambda v: v["rho"])
        o["drop_one_worst"] = [k for k, v in drops.items() if v is worst][0], worst
        # (c) equal weights
        o["equal_weights"] = cmp(s, score_of(X, pd.Series(1.0, index=w.index)))
        # (d) noise on the normalized values (sigma 0.02 and 0.05), 200 draws
        for sig in (0.02, 0.05):
            res = []
            for _ in range(200):
                res.append(cmp(s, score_of((X + RNG.normal(0, sig, X.shape)).clip(0, 1), w)))
            r = pd.DataFrame(res)
            o[f"noise_{sig}"] = {"rho_p50": round(float(r["rho"].median()), 4), "top20_p50": int(r["top20_kept"].median()), "buy_kept_p50": int(r["buy_kept"].median()),
                                 "crossers_p50": int((r["buy_in"] + r["buy_out"]).median()), "median_abs_move_p50": round(float(r["median_abs_move"].median()), 3)}
        OUT[key] = o


# (e) one raw input perturbed slightly, through the real factor functions.  The fund figures of a card are stored in the dump;
# first check that the stored figures reproduce the recorded factor values, then move one figure by +-5% for every stock.
FUND_FACTORS = ("earnings_revenue_quality", "profitability", "balance_sheet", "cash_flow_quality", "valuation", "business_quality", "growth_quality", "free_cash_flow",
                "balance_dilution", "financial_resilience", "leverage", "capital_allocation")


def refactor(card, fund):
    out = {}
    for f in card["factors"]:
        if f.get("scored") is False or f["factor"] not in FUND_FACTORS:
            continue
        o = factors.CALC[f["factor"]]({"fund": fund, "market": card.get("market")})
        out[f["factor"]] = o.get("normalized") if o["status"] in ("REAL", "STALE") else None
    return out


for market in ("US", "KR"):
    for strategy in ("SWING", "LONG_TERM"):
        key = f"{market}_{strategy}"
        cards, X, w, s = frame(market, strategy)
        ok = bad = 0
        for c in cards:
            got = refactor(c, c["fund"])
            for f, v in got.items():
                rec = X.at[c["ticker"], f]
                same = (v is None and np.isnan(rec)) or (v is not None and not np.isnan(rec) and abs(v - rec) < 1e-9)
                ok, bad = ok + same, bad + (not same)
        res = {"reproduced_factor_values": ok, "not_reproduced": bad}
        inputs = ("pe", "pb", "fcf_yield", "roe", "op_margin", "gross_margin", "rev_growth", "eps_growth", "debt_equity", "current_ratio", "interest_cover", "fcf_margin", "share_change")
        for inp in inputs:
            for mult in (0.95, 1.05):
                X2 = X.copy()
                for c in cards:
                    fund = dict(c["fund"])
                    if fund.get(inp) is None:
                        continue
                    fund[inp] = fund[inp] * mult
                    for f, v in refactor(c, fund).items():
                        X2.at[c["ticker"], f] = np.nan if v is None else v
                res[f"{inp}x{mult}"] = cmp(s, score_of(X2, w))
        # price +-1% and +-3%: only what can be recomputed from the stored figures (valuation ratios; the swing reward/risk factor
        # from the stored close, ATR and resistance).  Moving averages, highs and volatility are not recomputed: a lower bound.
        for mult in (0.97, 0.99, 1.01, 1.03):
            X2 = X.copy()
            for c in cards:
                fund = dict(c["fund"])
                for k, up in (("pe", True), ("pb", True), ("fcf_yield", False)):
                    if fund.get(k) is not None:
                        fund[k] = fund[k] * mult if up else fund[k] / mult
                for f, v in refactor(c, fund).items():
                    if f == "valuation":
                        X2.at[c["ticker"], f] = np.nan if v is None else v
                t = c["tech"]
                if "risk_reward" in X2.columns and t.get("atr") and t.get("close"):
                    close = t["close"] * mult
                    res_ok = t.get("resistance") if (t.get("resistance") and t["resistance"] >= close + t["atr"]) else None
                    lv = technicals.levels({"atr": t["atr"], "close": close, "resistance": res_ok}, market)
                    rr = factors.ramp(lv.get("reward_risk"), 1.0, 3.0) if lv.get("status") == "REAL" else None
                    X2.at[c["ticker"], "risk_reward"] = np.nan if rr is None else rr
            res[f"price x{mult}"] = cmp(s, score_of(X2, w))
        OUT[key]["one_input"] = res

# ------------------------------------------------------------------ conservative score
for market in ("US", "KR"):
    for strategy in ("SWING", "LONG_TERM"):
        key = f"{market}_{strategy}"
        cards, X, w, s = frame(market, strategy)
        rows = []
        for c in cards:
            fs = [f for f in c["factors"] if f.get("scored") is not False]
            tw = sum(f["weight"] for f in fs if f["status"] in ("REAL", "STALE"))
            tc = sum(f["weight"] * f["normalized"] for f in fs if f["status"] in ("REAL", "STALE"))
            mw = sum(f["weight"] for f in fs if f["status"] == "MISSING")
            naw = sum(f["weight"] for f in fs if f["status"] == "NOT_APPLICABLE")
            # the same idea one level down: a factor built from part of its figures, the absent figures read at the middle
            pc = 0.0
            for f in fs:
                if f["status"] in ("REAL", "STALE"):
                    inp = f.get("inputs")
                    x = f["normalized"] if not inp else (f["normalized"] * inp["have"] + 0.5 * (inp["total"] - inp["have"])) / inp["total"]
                    pc += f["weight"] * x
            rows.append({"ticker": c["ticker"], "score": c["score"], "cons_rec": c["conservative"], "cons_calc": 100 * (tc + 0.5 * mw) / (tw + mw), "miss_w": mw, "na_w": naw,
                         "cons_with_na": 100 * (tc + 0.5 * (mw + naw)) / (tw + mw + naw), "cons_with_partial": 100 * (pc + 0.5 * mw) / (tw + mw),
                         "cons_all": 100 * (pc + 0.5 * (mw + naw)) / (tw + mw + naw), "partial_n": sum(1 for f in fs if f.get("inputs")),
                         "missing": [f["factor"] for f in fs if f["status"] == "MISSING"], "na": [f["factor"] for f in fs if f["status"] == "NOT_APPLICABLE"],
                         "band": c["band"], "held_back": c["held_back"], "act": c["actionability"], "fin": bool(c["fund"].get("is_financial"))})
        r = pd.DataFrame(rows).set_index("ticker")
        act = r["act"] == "ACTIONABLE"
        ge70 = act & (r["score"] >= 70)
        # what the absent factors' cross-sectional mean is: the middle (0.5) is 'conservative' only if the factor's typical value is not lower
        miss_means = {}
        for f in w.index:
            n_miss = int(sum(f in m for m in r["missing"]))
            if n_miss:
                miss_means[f] = {"missing_n": n_miss, "mean_of_present": None if X[f].notna().sum() == 0 else round(float(X[f].mean()), 3), "weight": float(w[f])}
        OUT[key]["conservative"] = {
            "max_abs_diff_recorded_vs_recomputed": float((r["cons_rec"] - r["cons_calc"]).abs().max()),
            "cards_with_missing_factor": int((r["miss_w"] > 0).sum()), "cards_with_na_factor": int((r["na_w"] > 0).sum()), "cards_with_partial_factor": int((r["partial_n"] > 0).sum()),
            "actionable_score_ge70": int(ge70.sum()), "held_back": int(r["held_back"].fillna(False).astype(bool).sum()),
            "held_back_list": [(t, round(x.score, 1), round(x.cons_rec, 1), x.missing, x.band) for t, x in r[r["held_back"].fillna(False).astype(bool)].iterrows()],
            "ge70_conservative_higher_than_score": int((ge70 & (r["miss_w"] > 0) & (r["cons_rec"] >= r["score"])).sum()),
            "ge70_would_fall_if_na_also_neutral": int((ge70 & (r["cons_with_na"] < 70)).sum()), "ge70_would_fall_if_partial_also_neutral": int((ge70 & (r["cons_with_partial"] < 70)).sum()),
            "ge70_would_fall_if_all_neutral": int((ge70 & (r["cons_all"] < 70)).sum()), "ge70_financial": int((ge70 & r["fin"]).sum()), "ge70_financial_fall_if_na_neutral": int((ge70 & r["fin"] & (r["cons_with_na"] < 70)).sum()),
            "ge70_with_partial_factor": int((ge70 & (r["partial_n"] > 0)).sum()), "missing_factor_means": miss_means,
            "fin_mean_score": round(float(r.loc[r["fin"], "score"].mean()), 2), "fin_mean_cons_with_na": round(float(r.loc[r["fin"], "cons_with_na"].mean()), 2)}

# ------------------------------------------------------------------ stance presets on the real session
for market in ("US", "KR"):
    snaps = [{"ticker": c["ticker"], "strategy": c["strategy"], "score": c["score"], "actionability": c["actionability"], "confidence": c["confidence"], "price": c["price"], "stop": c["stop"],
              "band": c["band"], "entry_status": c["entry_status"], "held_back": c["held_back"], "sector": c["sector"], "atr_risk": next((f["normalized"] for f in c["factors"] if f["factor"] == "atr_risk"), None)}
             for c in D[market]["cards"].values()]
    wide = stance.volatile(snaps)
    o = {"wide_n": len(wide), "swing_snaps": sum(1 for x in snaps if x["strategy"] == "SWING")}
    for lvl in stance.LEVELS:
        got = stance.marks(snaps, lvl)
        per = {}
        for strat in ("SWING", "LONG_TERM"):
            mine = [x for x in snaps if x["strategy"] == strat]
            cand = [x for x in mine if got[(x["ticker"], strat)] is None]
            reasons = pd.Series([got[(x["ticker"], strat)] for x in mine if got[(x["ticker"], strat)]]).value_counts().to_dict()
            plan_all = [x for x in mine if x["actionability"] == "ACTIONABLE" and x["entry_status"] == "ENTRY_NOW" and x["score"] is not None]
            plan = [x for x in plan_all if got[(x["ticker"], strat)] is None] if stance.PRESETS[lvl]["plan_needs_line"] else plan_all
            per[strat] = {"screen_candidates": len(cand), "of_which_band_not_buy": sum(1 for x in cand if x["band"] not in BUY), "of_which_held_back": sum(1 for x in cand if x["held_back"]),
                          "of_which_entry_now": sum(1 for x in cand if x["entry_status"] == "ENTRY_NOW"), "reasons": reasons, "plan_candidates": len(plan),
                          "plan_min_score": round(min((x["score"] for x in plan), default=float("nan")), 1), "plan_score_lt70": sum(1 for x in plan if x["score"] < 70),
                          "candidate_sectors": pd.Series([x["sector"] for x in cand]).value_counts().to_dict() if lvl == "DEFENSIVE" else None}
        o[lvl] = per
    # what the widest-third rule removes among stocks at 75+ that pass the confidence rule, and how it relates to the score's own volatility factor
    sw = {x["ticker"]: x for x in snaps if x["strategy"] == "SWING"}
    width = {t: stance._range_share(x) for t, x in sw.items()}
    a = pd.Series({t: v for t, v in width.items() if v is not None})
    b = pd.Series({t: sw[t]["atr_risk"] for t in a.index}, dtype=float)
    o["range_vs_atr_risk_spearman"] = round(rho(a, b), 3)
    o["wide_sector_share"] = pd.Series([sw[t]["sector"] for t in wide]).value_counts(normalize=True).round(3).to_dict()
    o["universe_sector_share"] = pd.Series([x["sector"] for x in sw.values()]).value_counts(normalize=True).round(3).to_dict()
    o["wide_range_threshold"] = round(float(a.sort_values(ascending=False).iloc[len(wide) - 1]), 4) if wide else None
    for strat in ("SWING", "LONG_TERM"):
        hi = [x for x in snaps if x["strategy"] == strat and x["actionability"] == "ACTIONABLE" and (x["score"] or 0) >= 75]
        o[f"{strat}_ge75_actionable"] = len(hi)
        o[f"{strat}_ge75_in_wide_third"] = sum(1 for x in hi if x["ticker"] in wide)
        o[f"{strat}_ge75_low_conf"] = sum(1 for x in hi if x["confidence"] == "LOW")
    OUT[f"{market}_stance"] = o

# ------------------------------------------------------------------ test D: industry fairness (long-term score)
for market in ("US", "KR"):
    cards, X, w, s = frame(market, "LONG_TERM")
    meta = pd.DataFrame({c["ticker"]: {"sector": c["sector"] or "분류 없음", "fin": bool(c["fund"].get("is_financial")), "mcap": c["fund"].get("market_cap"), "name": c["name"], "debt_basis": c["fund"].get("debt_basis")} for c in cards}).T
    fin = meta["fin"].astype(bool)
    sec = meta["sector"]
    o = {"fin_n": int(fin.sum()), "fin_mean": round(float(s[fin].mean()), 2), "nonfin_mean": round(float(s[~fin].mean()), 2)}
    # the same score on the factors every company can have (those never 'not applicable')
    na_f = ["free_cash_flow", "leverage"]
    common = score_of(X.drop(columns=na_f), w.drop(na_f))
    o["common_factor_score_fin_mean"], o["common_factor_score_nonfin_mean"] = round(float(common[fin].mean()), 2), round(float(common[~fin].mean()), 2)
    o["factor_means_fin_vs_nonfin"] = {f: [None if X.loc[fin, f].notna().sum() == 0 else round(float(X.loc[fin, f].mean()), 3), round(float(X.loc[~fin, f].mean()), 3)] for f in w.index}
    o["nonfin_mean_of_na_factors"] = {f: round(float(X.loc[~fin, f].mean()), 3) for f in na_f}
    # partial inputs among financials: how many figures the factors rest on
    inp = {}
    for f in ("valuation", "business_quality", "growth_quality", "financial_resilience", "balance_dilution"):
        have = [(next((x.get("inputs") for x in c["factors"] if x["factor"] == f and x.get("scored") is not False), None), bool(c["fund"].get("is_financial"))) for c in cards]
        inp[f] = {"fin_partial_share": round(float(np.mean([h is not None for h, fi in have if fi])), 3), "nonfin_partial_share": round(float(np.mean([h is not None for h, fi in have if not fi])), 3)}
    o["partial_inputs"] = inp
    o["status_fin"] = {f: pd.Series([next((x["status"] for x in c["factors"] if x["factor"] == f and x.get("scored") is not False), None) for c in cards if c["fund"].get("is_financial")]).value_counts().to_dict() for f in w.index}
    # sector table: mean score, mean of the heavy factors, share in the 70+ set
    tab = {}
    for k in sorted(sec.unique()):
        m = sec == k
        tab[k] = {"n": int(m.sum()), "score": round(float(s[m].mean()), 1), "ge70": int((s[m] >= 70).sum()), **{f: (None if X.loc[m, f].notna().sum() == 0 else round(float(X.loc[m, f].mean()), 2)) for f in ("valuation", "business_quality", "growth_quality", "free_cash_flow", "balance_dilution", "financial_resilience", "leverage", "downside_drawdown")},
                  "fin_scored": int((m & fin).sum())}
    o["sector_table"] = tab
    # representative companies: the largest by market value in each sector
    rep = {}
    mc = pd.to_numeric(meta["mcap"], errors="coerce")
    for k in sorted(sec.unique()):
        idx = mc[sec == k].dropna().nlargest(2).index
        rep[k] = [{"ticker": t, "name": meta.at[t, "name"], "score": round(float(s[t]), 1), "fin": bool(fin[t]), "debt_basis": meta.at[t, "debt_basis"],
                   **{f: (None if np.isnan(X.at[t, f]) else round(float(X.at[t, f]), 2)) for f in ("valuation", "business_quality", "growth_quality", "free_cash_flow", "balance_dilution", "financial_resilience", "leverage")}} for t in idx]
    o["representatives"] = rep
    o["debt_basis_counts"] = meta["debt_basis"].value_counts(dropna=False).to_dict()
    OUT[f"{market}_fairness"] = o

(HERE / "an2_stability_fairness.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("written")
