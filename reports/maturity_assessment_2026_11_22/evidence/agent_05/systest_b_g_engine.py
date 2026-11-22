"""AGENT 5 scratch: SYSTEM TEST B (data failure resilience) and TEST G (missing evidence and confidence), engine level.
Synthetic bars only (tests/test_qsf.py helpers).  No provider, no repository data, no ledger.  Read-only on the repository."""
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from terminal.qsf import config, engine, technicals          # noqa: E402
from tests.test_qsf import GOOD_FUND, SESSION, bars, ctx     # noqa: E402

OUT = {}


def brief(r):
    return {"score": None if r["score"] is None else round(r["score"], 2), "band": r["band"], "band_label": r["band_label"], "action": r["action"], "actionability": r["actionability"],
            "coverage": round(r["coverage"], 3), "input_coverage": round(r["input_coverage"], 3), "confidence": r["confidence"], "gates": [g["code"] for g in r["gates"]],
            "missing": r["missing"], "partial": r["partial"], "stale": r["stale"], "data_date": r["data_date"]}


def run(name, strategy="SWING", **over):
    try:
        r = engine.score(ctx(**over), strategy)
        OUT[name] = brief(r)
    except Exception as exc:          # what the engine does with input it cannot take
        OUT[name] = {"EXCEPTION": type(exc).__name__, "text": str(exc)[:160]}
    return OUT[name]


# ------------------------------------------------------------------ TEST B
run("B0_baseline_swing")
run("B0_baseline_long", "LONG_TERM")
# 1 missing statements
run("B1_missing_statements_swing", fund={"status": "UNAVAILABLE", "reason": "SEC 재무 조회 실패 (ConnectionError)"})
run("B1_missing_statements_long", "LONG_TERM", fund={"status": "UNAVAILABLE", "reason": "SEC 재무 조회 실패 (ConnectionError)"})
# 2 stale last price: the bars end one session before the expected one
run("B2_stale_price", bars=bars(end="2026-11-03"), price_fresh=False)
# 2b the same bars, but the caller did not say (engine default price_fresh=True): what the engine alone would do
c = ctx(bars=bars(end="2026-10-01"))
c.pop("price_fresh")
OUT["B2b_stale_price_flag_absent"] = brief(engine.score(c, "SWING"))
# 5 invalid values handed straight to the engine (the source layer is tested apart)
b = bars()
z = [dict(x) for x in b]; z[-1].update(close=0.0, adj_close=0.0)
run("B5_last_close_zero", bars=z)
z = [dict(x) for x in b]; z[-1].update(close=-12.0, adj_close=-12.0)
run("B5_last_close_negative", bars=z)
z = [dict(x) for x in b]; z[-1].update(close=float("nan"), adj_close=float("nan"))
run("B5_last_close_nan", bars=z)
z = [dict(x) for x in b]; z[-40].update(close=float("nan"), adj_close=float("nan"))
run("B5_nan_close_40_bars_back", bars=z)
z = [dict(x) for x in b]; z[-40].update(close=0.0, adj_close=0.0)
run("B5_zero_close_40_bars_back", bars=z)
z = [dict(x) for x in b]; z[-3].update(high=z[-3]["low"] * 0.5)      # high below low
run("B5_high_below_low", bars=z)
z = [dict(x) for x in b]; z[-1].update(volume=float("nan"))
run("B5_nan_last_volume", bars=z)
z = [dict(x) for x in b]; z[-1].update(volume=-5.0)
run("B5_negative_last_volume", bars=z)
z = [dict(x) for x in b]
for x in z[-100:]:
    x.update(close=x["close"] * 10, adj_close=x["adj_close"] * 10, open=x["open"] * 10, high=x["high"] * 10, low=x["low"] * 10)     # a 10x unit error 100 bars back
run("B5_price_x10_100_bars_back", bars=z)
z = [dict(x) for x in b]
for x in z[-100:]:
    x.update(close=x["close"] * 1.35, adj_close=x["adj_close"] * 1.35, open=x["open"] * 1.35, high=x["high"] * 1.35, low=x["low"] * 1.35)   # a 35% step: under the 45% gate
run("B5_price_step_35pct_100_bars_back", bars=z)
z = [dict(x) for x in b]
for x in z[:-150]:
    x.update(close=x["close"] * 2, open=x["open"] * 2, high=x["high"] * 2, low=x["low"] * 2)      # an unadjusted 2-for-1 split 150 bars back (adj_close left right)
run("B5_unadjusted_2for1_split_150_back", bars=z)
z = [dict(x) for x in b]
for x in z[:-270]:
    x.update(close=x["close"] * 2, open=x["open"] * 2, high=x["high"] * 2, low=x["low"] * 2)      # the same, but older than 252 bars
run("B5_unadjusted_2for1_split_270_back", bars=z)
# 6 duplicated bars
run("B6_last_bar_doubled", bars=b + [dict(b[-1])])
run("B6_bar_doubled_mid", bars=b[:200] + [dict(b[199])] + b[200:])
run("B6_out_of_order", bars=b[:100] + [b[101], b[100]] + b[102:])
# 7 a missing stretch of history: 40 sessions cut out of the middle (no price jump: the synthetic drift is small)
gap = b[:200] + b[240:]
run("B7_missing_40_sessions", bars=gap)
t_full, t_gap = technicals.compute(b, None), technicals.compute(gap, None)
OUT["B7_indicator_shift"] = {k: [None if t_full[k] is None else round(t_full[k], 4), None if t_gap[k] is None else round(t_gap[k], 4)] for k in ("n", "ma50", "ma200", "ret_126", "ret_252", "hist_vol", "max_move_252", "row_defects")}
gap2 = b[:120] + b[280:]      # 160 sessions missing: n falls under 200
run("B7_missing_160_sessions", bars=gap2)
# short history
run("B7_short_history_120", bars=bars(n=120))

# ------------------------------------------------------------------ TEST G
BAD_FUND = {**GOOD_FUND, "roe": -0.05, "op_margin": -0.02, "gross_margin": 0.1, "rev_growth": -0.1, "eps_growth": -0.3, "ocf_to_ni": 0.2, "fcf_margin": -0.05, "debt_equity": 3.0, "current_ratio": 0.7,
            "interest_cover": 0.5, "cash_debt": 0.02, "equity_assets": 0.1, "share_change": 0.08, "pe": 60, "pb": 12, "fcf_yield": -0.01, "rev_cagr3": -0.05, "eps_cagr3": -0.1, "roe_years_positive": 0.2,
            "fcf_years_positive": 0.2, "returns_capital": False}
for s in ("SWING", "LONG_TERM"):
    run(f"G1_strong_{s}", s)
    run(f"G2_insufficient_{s}", s, fund=None, events=None, earnings={"sessions": None})
    run(f"G3_conflict_good_chart_bad_statements_{s}", s, fund=BAD_FUND)
    run(f"G3_conflict_bad_chart_good_statements_{s}", s, bars=bars(drift=-0.002))
    run(f"G4_stale_statements_{s}", s, fund={**GOOD_FUND, "status": "STALE"})
    run(f"G4_stale_price_{s}", s, bars=bars(end="2026-11-03"), price_fresh=False)
    run(f"G5_valuation_unknown_{s}", s, fund={**GOOD_FUND, "pe": None, "pb": None, "fcf_yield": None, "pe_basis": None})
    run(f"G5_valuation_pe_only_{s}", s, fund={**GOOD_FUND, "pb": None, "fcf_yield": None})

# ------------------------------------------------------------------ can missing data raise a score?
# (a) a whole factor missing: an expensive stock (valuation scores 0) against the same stock with the valuation inputs gone
EXPENSIVE = {**GOOD_FUND, "pe": 60, "pb": 12, "fcf_yield": -0.01}
a = engine.score(ctx(fund=EXPENSIVE), "LONG_TERM")
bb = engine.score(ctx(fund={**EXPENSIVE, "pe": None, "pb": None, "fcf_yield": None}), "LONG_TERM")
OUT["RAISE_a_whole_factor_valuation"] = {"with_figures": brief(a), "figures_missing": brief(bb), "score_change": round(bb["score"] - a["score"], 2)}
# (b) part of a factor missing: the bad figure of three is gone, the factor rests on the good two
f1 = {**GOOD_FUND, "eps_cagr3": -0.20, "eps_growth": -0.30}
f2 = {**f1, "eps_cagr3": None, "eps_growth": None}
a, bb = engine.score(ctx(fund=f1), "LONG_TERM"), engine.score(ctx(fund=f2), "LONG_TERM")
OUT["RAISE_b_sub_figure_growth"] = {"with_figures": brief(a), "figures_missing": brief(bb), "score_change": round(bb["score"] - a["score"], 2)}
# (c) the whole bad fundamental domain missing in a swing card (statement source down for one stock)
a, bb = engine.score(ctx(fund=BAD_FUND), "SWING"), engine.score(ctx(fund={"status": "UNAVAILABLE"}), "SWING")
OUT["RAISE_c_bad_statements_gone_swing"] = {"with_figures": brief(a), "figures_missing": brief(bb), "score_change": round(bb["score"] - a["score"], 2)}
# (d) the worst case the sufficiency rule still lets through, by arithmetic on the long-term profile: factors worth up to 30% of the
#     counted weight may be missing; if each of them would have scored 0, the shown score is the true one divided by the share left.
prof = config.profile_for("US", "LONG_TERM")
counted = sum(sum(d.values()) for d in prof["domains"].values())
OUT["RAISE_d_arithmetic_bound"] = {"counted_weight": counted, "min_total_coverage": config.MIN_TOTAL_COVERAGE,
                                   "note": "score_shown = score_true / coverage when every missing factor would have scored 0",
                                   "true_49_shown": round(49 / 0.70, 1), "true_56_shown": round(56 / 0.80, 1), "true_63_shown": round(63 / 0.90, 1)}
# (e) the other direction: a missing GOOD factor lowers the score
a, bb = engine.score(ctx(), "LONG_TERM"), engine.score(ctx(fund={**GOOD_FUND, "pe": None, "pb": None, "fcf_yield": None}), "LONG_TERM")
OUT["LOWER_e_good_valuation_gone"] = {"with_figures": round(a["score"], 2), "figures_missing": round(bb["score"], 2), "score_change": round(bb["score"] - a["score"], 2)}

Path(__file__).with_name("test_b_g_engine_output.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
for k, v in OUT.items():
    print(k, json.dumps(v, ensure_ascii=False, default=str))
