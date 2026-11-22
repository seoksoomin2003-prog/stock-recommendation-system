"""AGENT 5 (2026-11-23) scratch: SYSTEM TEST B at the engine level, commit 02aed81.
Synthetic bars only (helpers of tests/test_qsf.py).  No provider, no repository data, no ledger.  Read-only on the repository:
the only file written is this script's own output beside it."""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

import numpy as np                                            # noqa: E402

from terminal.qsf import config, engine, holding, kr_bars, technicals   # noqa: E402
from tests.test_qsf import GOOD_FUND, bars, ctx              # noqa: E402
from utils import nyse_calendar                              # noqa: E402

OUT = {}


def brief(r):
    return {"score": None if r["score"] is None else round(r["score"], 2), "conservative": None if r.get("conservative_score") is None else round(r["conservative_score"], 2),
            "band": r["band"], "band_label": r["band_label"], "held_back": r.get("band_held_back"), "action": r["action"], "raw_action": r["raw_action"],
            "actionability": r["actionability"], "coverage": round(r["coverage"], 3), "input_coverage": round(r["input_coverage"], 3), "confidence": r["confidence"],
            "gates": [g["code"] for g in r["gates"]], "gate_text": [g["text"] for g in r["gates"]][:2], "missing": r["missing"], "partial": r["partial"], "stale": r["stale"],
            "data_date": r["data_date"], "max_gap_weekdays": r["tech"].get("max_gap_weekdays"), "bad_rows": r["tech"].get("bad_rows"), "row_defects": r["tech"].get("row_defects")}


def run(name, strategy="SWING", **over):
    try:
        OUT[name] = brief(engine.score(ctx(**over), strategy))
    except Exception as exc:
        OUT[name] = {"EXCEPTION": type(exc).__name__, "text": str(exc)[:160]}
    return OUT[name]


b = bars()
# ---------------------------------------------------------------- baseline, missing statements, stale price
run("B0_baseline_swing")
run("B0_baseline_long", "LONG_TERM")
run("B1_missing_statements_swing", fund={"status": "UNAVAILABLE", "reason": "SEC 재무 조회 실패 (ConnectionError)"})
run("B1_missing_statements_long", "LONG_TERM", fund={"status": "UNAVAILABLE", "reason": "SEC 재무 조회 실패 (ConnectionError)"})
run("B2_stale_price", bars=bars(end="2026-11-03"), price_fresh=False)
c = ctx(bars=bars(end="2026-10-01"))
c.pop("price_fresh")
OUT["B2b_stale_price_flag_absent"] = brief(engine.score(c, "SWING"))

# ---------------------------------------------------------------- invalid values
def edit(i, **kw):
    z = [dict(x) for x in b]
    z[i].update(**kw)
    return z


run("B5_last_close_zero", bars=edit(-1, close=0.0, adj_close=0.0))
run("B5_last_close_negative", bars=edit(-1, close=-12.0, adj_close=-12.0))
run("B5_last_close_nan", bars=edit(-1, close=float("nan"), adj_close=float("nan")))
run("B5_nan_close_40_back", bars=edit(-40, close=float("nan"), adj_close=float("nan")))
run("B5_zero_close_40_back", bars=edit(-40, close=0.0, adj_close=0.0))
run("B5_high_below_low", bars=edit(-3, high=b[-3]["low"] * 0.5))
run("B5_high_below_low_260_back", bars=edit(-260, high=b[-260]["low"] * 0.5))
run("B5_negative_last_volume", bars=edit(-1, volume=-5.0))
run("B5_nan_last_volume", bars=edit(-1, volume=float("nan")))
run("B5_close_above_high", bars=edit(-3, close=b[-3]["high"] * 1.2, adj_close=b[-3]["high"] * 1.2))
z = [dict(x) for x in b]
for x in z[-100:]:
    x.update({k: x[k] * 1.35 for k in ("open", "high", "low", "close", "adj_close")})
run("B5_price_step_35pct_100_back", bars=z)
z = [dict(x) for x in b]
for x in z[-100:]:
    x.update({k: x[k] * 1.44 for k in ("open", "high", "low", "close", "adj_close")})
run("B5_price_step_44pct_100_back", bars=z)
z = [dict(x) for x in b]
for x in z[:-150]:
    x.update({k: x[k] * 2 for k in ("open", "high", "low", "close")})       # an unadjusted 2-for-1 split, adj_close left right
run("B5_unadjusted_2for1_split_150_back", bars=z)
z = [dict(x) for x in b]
for x in z[:-150]:
    x.update({k: x[k] * 1.5 for k in ("open", "high", "low", "close")})     # an unadjusted 3-for-2 split: a 33% day, under the 45% line
run("B5_unadjusted_3for2_split_150_back", bars=z)
# adj_close wrong while close is right (a dividend adjustment gone bad): returns read adj_close, the gate reads close
z = [dict(x) for x in b]
for x in z[:-100]:
    x.update(adj_close=x["adj_close"] * 0.5)
run("B5_adj_close_halved_before_100_back", bars=z)

# ---------------------------------------------------------------- duplicates
run("B6_last_bar_doubled", bars=b + [dict(b[-1])])
run("B6_bar_doubled_mid", bars=b[:200] + [dict(b[199])] + b[200:])
run("B6_out_of_order", bars=b[:100] + [b[101], b[100]] + b[102:])

# ---------------------------------------------------------------- holes in the history
run("B7_missing_40_sessions_same_case_as_2026_11_22", bars=b[:200] + b[240:])
edges = {}
for k in (3, 5, 8, 9, 10, 11, 12, 15):
    r = run(f"B7_hole_{k}_sessions_100_back", bars=b[:len(b) - 100 - k] + b[len(b) - 100:])
    edges[k] = {"max_gap_weekdays": r["max_gap_weekdays"], "gates": r["gates"], "actionability": r["actionability"]}
OUT["B7_edge_table"] = edges
# where the hole sits: the gate reads the last 253 rows
for back in (5, 60, 240, 251, 252, 253, 260):
    r = run(f"B7_hole_15_sessions_ending_{back}_rows_back", bars=b[:len(b) - back - 15] + b[len(b) - back:])
# many small holes: five sessions gone out of every fifteen through the last year (a third of the year missing)
keep = [x for i, x in enumerate(b) if i < 60 or (i % 15) >= 5]
r = run("B7_scattered_small_holes_a_third_of_the_year", bars=keep)
OUT["B7_scattered_small_holes_a_third_of_the_year"]["rows_left"] = len(keep)
t_full, t_gap = technicals.compute(b, None), technicals.compute(keep, None)
OUT["B7_scattered_indicator_shift"] = {k: [None if t_full[k] is None else round(t_full[k], 4), None if t_gap[k] is None else round(t_gap[k], 4)] for k in ("n", "ma50", "ma200", "ret_126", "ret_252", "hist_vol", "max_move_252")}
# every other session missing (a provider that drops alternate rows)
r = run("B7_every_other_session_missing", bars=b[::2] if b[::2][-1]["date"] == b[-1]["date"] else b[1::2])
run("B7_short_history_120", bars=bars(n=120))

# calendars: the longest run of closed weekdays the gate would meet without any defect
def gap_of(days):
    return technicals._max_gap(sorted(days))


us_days = [d.isoformat() for d in (date(2000, 1, 3) + timedelta(days=i) for i in range(365 * 27)) if d.weekday() < 5 and nyse_calendar.is_session(d)]
OUT["CAL_us_2000_2026_longest_closed_weekdays"] = gap_of(us_days)
# Korea: weekdays less the longest holiday runs on record, by hand (public holidays; no provider):
#   2017-10-02..10-09 (temporary holiday, National Foundation Day, Chuseok, Hangul Day): six weekdays closed
#   2025-10-03..10-09: five weekdays closed
kr17 = [d.isoformat() for d in (date(2017, 9, 1) + timedelta(days=i) for i in range(70)) if d.weekday() < 5 and not (date(2017, 10, 2) <= d <= date(2017, 10, 9))]
kr25 = [d.isoformat() for d in (date(2025, 9, 1) + timedelta(days=i) for i in range(70)) if d.weekday() < 5 and not (date(2025, 10, 3) <= d <= date(2025, 10, 9))]
OUT["CAL_kr_chuseok_2017_closed_weekdays"] = gap_of(kr17)
OUT["CAL_kr_chuseok_2025_closed_weekdays"] = gap_of(kr25)

# a stock that really was halted, US style (Yahoo: no rows on halted days): 12 sessions without a row, 100 rows back
halt = b[:len(b) - 112] + b[len(b) - 100:]
OUT["HALT_us_12_sessions_no_rows"] = run("HALT_us_12_sessions", bars=halt)
# ... and Korea, bars built from KRX snapshots: a halted day is in the snapshot with its base price and no trade
days = [x["date"] for x in b[-300:]]
n = len(days)
data = np.full((6, n, 1), np.nan)
raw = np.array([x["close"] for x in b[-300:]]) * 1000          # won
raw[150:170] = raw[149]                                         # twenty halted sessions: the close repeats
rate = np.zeros(n)
rate[1:] = (raw[1:] / raw[:-1] - 1) * 100
data[kr_bars.CLOSE, :, 0] = raw
data[kr_bars.RATE, :, 0] = rate
for k in (kr_bars.OPEN, kr_bars.HIGH, kr_bars.LOW):
    data[k, :, 0] = raw
    data[k, 150:170, 0] = 0.0                                   # no trade on a halted day
data[kr_bars.VOLUME, :, 0] = 500_000.0
data[kr_bars.VOLUME, 150:170, 0] = 0.0
pan = {"dates": days, "codes": {"000001": 0}, "data": data}
yahoo = [{**x, **{k: x[k] * 1000 for k in ("open", "high", "low", "close", "adj_close")}} for x in b[-300:] if not (days[150] <= x["date"] <= days[169])]     # Yahoo has no rows on those days
rebuilt, info = kr_bars.rebuild("000001", yahoo, pan)
OUT["HALT_kr_rebuild_info"] = {**info, "rows": len(rebuilt), "yahoo_rows": len(yahoo), "halted_rows_kept": sum(1 for x in rebuilt if x["volume"] == 0)}
kc = ctx(bars=rebuilt, market="US")                             # gates are market-neutral except liquidity; the US profile is enough to read them
OUT["HALT_kr_20_sessions_rows_kept_flat"] = brief(engine.score(kc, "SWING"))
OUT["HALT_kr_same_stock_from_yahoo_rows_only"] = brief(engine.score(ctx(bars=yahoo), "SWING"))

# ---------------------------------------------------------------- a whole factor missing (the case of 2026-11-22: 75.1 against 90.1)
EXPENSIVE = {**GOOD_FUND, "pe": 60, "pb": 12, "fcf_yield": -0.01}
GONE = {**EXPENSIVE, "pe": None, "pb": None, "fcf_yield": None}
a = engine.score(ctx(fund=EXPENSIVE), "LONG_TERM")
g = engine.score(ctx(fund=GONE), "LONG_TERM")
c2 = ctx(fund=GONE)
c2["tech"] = g["tech"]
OUT["RAISE_a_whole_factor_valuation"] = {"with_figures": brief(a), "figures_missing": brief(g), "score_change": round(g["score"] - a["score"], 2),
                                         "entry_status_when_missing": holding.entry_status(g, c2), "entry_status_with_figures": holding.entry_status(a, {**ctx(fund=EXPENSIVE), "tech": a["tech"]})}
# (b) part of a factor missing: the bad figures gone, the factor rests on the good one
f1 = {**GOOD_FUND, "eps_cagr3": -0.20, "eps_growth": -0.30}
f2 = {**f1, "eps_cagr3": None, "eps_growth": None}
a, g = engine.score(ctx(fund=f1), "LONG_TERM"), engine.score(ctx(fund=f2), "LONG_TERM")
OUT["RAISE_b_sub_figure_growth"] = {"with_figures": brief(a), "figures_missing": brief(g), "score_change": round(g["score"] - a["score"], 2)}
# (c) a bad fundamental domain gone from a swing card
BAD = {**GOOD_FUND, "roe": -0.05, "op_margin": -0.02, "gross_margin": 0.1, "rev_growth": -0.1, "eps_growth": -0.3, "ocf_to_ni": 0.2, "fcf_margin": -0.05, "debt_equity": 3.0, "current_ratio": 0.7,
       "interest_cover": 0.5, "cash_debt": 0.02, "equity_assets": 0.1, "share_change": 0.08, "pe": 60, "pb": 12, "fcf_yield": -0.01, "rev_cagr3": -0.05, "eps_cagr3": -0.1, "roe_years_positive": 0.2,
       "fcf_years_positive": 0.2, "returns_capital": False}
a, g = engine.score(ctx(fund=BAD), "SWING"), engine.score(ctx(fund={"status": "UNAVAILABLE"}), "SWING")
OUT["RAISE_c_bad_statements_gone_swing"] = {"with_figures": brief(a), "figures_missing": brief(g), "score_change": round(g["score"] - a["score"], 2)}
# (d) under the buy line: a weak stock whose bad factor is missing crosses from the avoid side to "watch" (55)
for fund_name, base_fund in (("MID", {**GOOD_FUND, "roe": 0.06, "op_margin": 0.05, "gross_margin": 0.25, "rev_growth": 0.0, "eps_growth": -0.05, "rev_cagr3": 0.0, "eps_cagr3": -0.02, "debt_equity": 1.5, "current_ratio": 1.0,
                                       "interest_cover": 2.5, "roe_years_positive": 0.6, "fcf_years_positive": 0.6, "returns_capital": False, "pe": 60, "pb": 12, "fcf_yield": -0.01}),):
    a = engine.score(ctx(fund=base_fund, bars=bars(drift=-0.0005)), "LONG_TERM")
    g = engine.score(ctx(fund={**base_fund, "pe": None, "pb": None, "fcf_yield": None}, bars=bars(drift=-0.0005)), "LONG_TERM")
    OUT[f"RAISE_d_under_the_buy_line_{fund_name}"] = {"with_figures": brief(a), "figures_missing": brief(g), "score_change": round(g["score"] - a["score"], 2)}
# (e) the other direction
a, g = engine.score(ctx(), "LONG_TERM"), engine.score(ctx(fund={**GOOD_FUND, "pe": None, "pb": None, "fcf_yield": None}), "LONG_TERM")
OUT["LOWER_e_good_valuation_gone"] = {"with_figures": brief(a), "figures_missing": brief(g), "score_change": round(g["score"] - a["score"], 2)}

Path(__file__).with_name("b_engine_output.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
for k, v in OUT.items():
    print(k, json.dumps(v, ensure_ascii=False, default=str))
