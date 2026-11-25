"""Experiment 1 (boundaries) and 8 (same input -> same output): pure functions called with made-up inputs.  No file is written by the engine."""
import copy, json, math, hashlib
from common import *
from terminal.qsf import technicals

out = {}
# --- band lines
cases = [(80.0, None), (79.999999, None), (70.0, None), (69.999999, None), (67.0, "BUY_CANDIDATE"), (66.999999, "BUY_CANDIDATE"), (67.0, None), (69.9, "STRONG_BUY_CANDIDATE"),
         (69.9, "HOLD_WATCH"), (55.0, None), (54.999999, None), (40.0, None), (39.999999, None), (0.0, None), (None, None), (100.0, None), (float("nan"), None)]
out["classify"] = [{"score": s, "prev": p, "band": engine.classify(s, p)["band"], "action_new": engine.action_for(s, False, p), "action_held": engine.action_for(s, True, p)} for s, p in cases]
for r in out["classify"]:
    print(r)
# --- ramp
tests = {"mid": factors.ramp(0.5, 0, 1), "below": factors.ramp(-5, 0, 1), "above": factors.ramp(5, 0, 1), "lower_better": factors.ramp(0.3, 2.0, 0.3), "nan": factors.ramp(float("nan"), 0, 1),
         "inf": factors.ramp(float("inf"), 0, 1), "none": factors.ramp(None, 0, 1)}
try:
    tests["lo_eq_hi"] = factors.ramp(1.0, 1.0, 1.0)
except ZeroDivisionError as e:
    tests["lo_eq_hi"] = "ZeroDivisionError (no factor uses equal anchors; engine would catch it as MISSING)"
tests["mean_empty"] = factors.mean([None, None]); tests["mean_partial"] = (float(factors.mean([0.2, None, 0.6])), factors.mean([0.2, None, 0.6]).have, factors.mean([0.2, None, 0.6]).total)
out["ramp"] = tests; print(tests)
# anchors: every ramp call in factors.py has lo != hi (grep count)
import re
src = open("terminal/qsf/factors.py").read()
pairs = re.findall(r"ramp\([^,]+,\s*(-?[\d.e]+),\s*(-?[\d.e]+)\)", src) + re.findall(r"_rr\(f,\s*\"\w+\",\s*(-?[\d.e]+),\s*(-?[\d.e]+)\)", src) + re.findall(r"_eps_growth\(f,\s*\"\w+\",\s*(-?[\d.e]+),\s*(-?[\d.e]+)\)", src)
out["anchor_pairs"] = len(pairs); out["anchor_equal"] = sum(1 for a, b in pairs if float(a) == float(b))
print("anchor pairs found:", len(pairs), "with lo == hi:", out["anchor_equal"])

# --- a made-up company through the engine (no network: tech, levels, fund, events supplied)
def bars(n=300, start=100.0, drift=0.001, seed=1):
    rng = np.random.default_rng(seed)
    px, rows = start, []
    import datetime as dt
    d = dt.date(2025, 1, 1)
    for i in range(n):
        d += dt.timedelta(days=1)
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        o = px; px = px * (1 + drift + 0.01 * rng.standard_normal()); h = max(o, px) * 1.005; l = min(o, px) * 0.995
        rows.append({"date": d.isoformat(), "open": o, "high": h, "low": l, "close": px, "volume": 1_000_000 + int(1e5 * rng.random())})
    return rows
b = bars(); bench = bars(seed=2)
fund = {"status": "REAL", "source": "made-up", "filed": "2026-01-01", "is_financial": False, "roe": 0.15, "op_margin": 0.12, "gross_margin": 0.4, "roe_years_positive": 1.0, "rev_growth": 0.08, "eps_growth": 0.1,
        "ocf_to_ni": 1.0, "fcf_margin": 0.08, "fcf_years_positive": 0.8, "debt_equity": 0.8, "current_ratio": 1.5, "interest_cover": 6.0, "cash_debt": 0.3, "pe": 18.0, "pb": 3.0, "fcf_yield": 0.04,
        "rev_cagr3": 0.07, "eps_cagr3": 0.08, "share_change": 0.0, "returns_capital": True, "insider_pct": 0.02}
events = {"status": "REAL", "source": "made-up", "as_of": b[-1]["date"], "negative": [], "positive": [], "governance": [], "severe": [], "window_days": 90,
          "insider": {"status": "REAL", "open_market_buy": 0.0, "open_market_sell": 0.0, "window_days": 90}}
def ctx(**over):
    c = {"market": "US", "bars": b, "bench": bench, "fund": copy.deepcopy(fund), "events": copy.deepcopy(events), "earnings": {"sessions": 30, "date": "2027-01-01"}, "regime": {}, "rs_rank": 0.6,
         "bench_name": "SPY", "price_fresh": True, "expected_session": b[-1]["date"]}
    c.update(over)
    return c
def h(card):
    return hashlib.sha256(json.dumps(card, sort_keys=True, default=str).encode()).hexdigest()
rep = {}
for strat in ("SWING", "LONG_TERM"):
    a1, a2 = engine.score(ctx(), strat), engine.score(ctx(), strat)
    rep[strat] = {"score": a1["score"], "identical_twice": h(a1) == h(a2), "coverage": a1["coverage"], "confidence": a1["confidence"], "band": a1["band"]}
    # ordering dependence: shuffle dict key order of fund
    f2 = dict(reversed(list(fund.items())))
    a3 = engine.score(ctx(fund=f2), strat)
    rep[strat]["same_with_reordered_inputs"] = a3["score"] == a1["score"]
out["made_up_twice"] = rep; print(rep)

# --- missing inputs: everything None
empty = engine.score(ctx(fund={"status": "UNAVAILABLE", "reason": "x"}, events={"status": "UNAVAILABLE"}, earnings={}, rs_rank=None), "LONG_TERM")
out["no_fund_no_events_long"] = {k: empty[k] for k in ("score", "coverage", "confidence", "band", "band_label", "action", "actionability", "short_domains")}
print("no fund/events LONG:", out["no_fund_no_events_long"])
empty_s = engine.score(ctx(fund={"status": "UNAVAILABLE", "reason": "x"}, events={"status": "UNAVAILABLE"}, earnings={}, rs_rank=None), "SWING")
out["no_fund_no_events_swing"] = {k: empty_s[k] for k in ("score", "coverage", "confidence", "band", "band_label", "action", "actionability", "short_domains", "conservative_score", "band_held_back")}
print("no fund/events SWING:", out["no_fund_no_events_swing"])
# --- zero / negative denominators
edge = {}
for name, patch in {"pe_negative": {"pe": -5.0}, "pe_zero": {"pe": 0.0}, "pb_none(neg equity)": {"pb": None, "debt_equity": 99.0, "roe": None}, "all_valuation_none": {"pe": None, "pb": None, "fcf_yield": None},
                    "nan_roe": {"roe": float("nan")}, "inf_pe": {"pe": float("inf")}, "loss_now_no_growth": {"loss_now": True, "eps_growth": None, "eps_cagr3": None}, "interest_cover_negative": {"interest_cover": -3.0}}.items():
    f = {**fund, **patch}
    c = engine.score(ctx(fund=f), "LONG_TERM")
    by = {r["factor"]: r for r in c["factors"]}
    edge[name] = {"score": c["score"], "valuation": by["valuation"].get("normalized"), "valuation_status": by["valuation"]["status"], "business_quality": by["business_quality"].get("normalized"),
                  "growth_quality": by["growth_quality"].get("normalized"), "leverage": by["leverage"].get("normalized"), "financial_resilience": by["financial_resilience"].get("normalized"),
                  "band": c["band"], "held_back": c["band_held_back"], "conservative": c["conservative_score"], "confidence": c["confidence"], "input_coverage": c["input_coverage"]}
    print(name, edge[name])
out["edges"] = edge
# --- zero-volume / flat bars: technicals must not raise
flat = [{**r, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0} for r in b]
try:
    c = engine.score(ctx(bars=flat), "SWING")
    out["flat_bars"] = {"score": c["score"], "gates": [g["code"] for g in c["gates"]], "missing": c["missing"], "actionability": c["actionability"]}
except Exception as e:
    out["flat_bars"] = f"RAISED {type(e).__name__}: {e}"
print("flat bars:", out["flat_bars"])
short = b[:50]
try:
    c = engine.score(ctx(bars=short), "SWING")
    out["short_bars"] = {"score": c["score"], "gates": [g["code"] for g in c["gates"]], "missing": c["missing"], "actionability": c["actionability"], "coverage": c["coverage"]}
except Exception as e:
    out["short_bars"] = f"RAISED {type(e).__name__}: {e}"
print("50 bars:", out["short_bars"])
dump("s01b_boundaries.json", out)
