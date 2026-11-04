"""P6-20 prospective outcome measurement and paper portfolios.

Pure functions: ``(ledger records, price snapshot, as_of_session) -> outcomes``.  No clock,
no network, no writes, so every result can be replayed bit-for-bit from a stored snapshot.

Price basis (never mixed inside one return):
* PRICE basis: provider Open/High/Low/Close, split-adjusted, not dividend-adjusted.
* TOTAL basis: the same prices multiplied by the provider's dividend adjustment factor
  ``adj_close / close`` of the same session, so dividends paid inside the window are included.

Primary measurement (frozen exit assumptions, P6-11B, unchanged):
  entry #1 (frozen 40% of target) at the entry-reference open; each session close is
  evaluated by the frozen ``DecisionEngine.evaluate_existing_position``; any signal it
  emits (entry #2, HARD_STOP, THESIS_INVALIDATION, TRAILING_ATR, 30D review exit) is
  filled at the NEXT session open (a close-based signal is not executable at that close).
  The measurement window ends at the first exit fill or at the close of the session where
  the frozen 30-weekday horizon review falls due, whichever comes first.
"""
import math
from datetime import date, datetime, time, timezone
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

from utils import nyse_calendar

DIAGNOSTIC_HORIZONS = (5, 10, 20, 30)
DEFAULT_COST_BPS = (0.0, 5.0, 10.0, 25.0)     # per side, HYPOTHETICAL scenarios
ENTRY_ROLL_LIMIT = 5                          # sessions to wait for a valid open (halts, missing bars)
BENCHMARK = "SPY"
MIN_SAMPLE = 30


def _d(x) -> date:
    return pd.Timestamp(x).date()


def _finite(x) -> bool:
    return x is not None and isinstance(x, (int, float, np.floating)) and math.isfinite(float(x))


def indicators_until(closes: pd.Series):
    """Canonical-pipeline definitions (pipeline/canonical.py): close-proxy ATR(14) and EMA20."""
    ps = closes.dropna()
    if len(ps) < 15:
        return float("nan"), float("nan")
    atr = ps.pct_change().abs().rolling(14).mean().iloc[-1] * ps.iloc[-1]
    ema20 = ps.ewm(span=20, adjust=False).mean().iloc[-1]
    return float(atr), float(ema20)


def _bar(df: Optional[pd.DataFrame], d: date) -> Optional[pd.Series]:
    if df is None or d not in df.index:
        return None
    row = df.loc[d]
    return row if _finite(row.get("close")) else None


def _tr_factor(row: pd.Series) -> float:
    if row is None or not _finite(row.get("adj_close")) or not _finite(row.get("close")) or row["close"] == 0:
        return float("nan")
    return float(row["adj_close"]) / float(row["close"])


def _valid_open(row) -> bool:
    return row is not None and _finite(row.get("open")) and float(row["open"]) > 0 and \
        (not _finite(row.get("volume")) or float(row["volume"]) > 0)


def find_entry(df: Optional[pd.DataFrame], planned: date, as_of: date) -> Dict[str, Any]:
    """First valid open on/after the planned entry session; never before it (no look-ahead)."""
    if planned > as_of:
        return {"status": "PENDING_ENTRY", "reason": "ENTRY_SESSION_NOT_YET_COMPLETED"}
    sessions = nyse_calendar.sessions_between(planned, as_of)
    for i, s in enumerate(sessions[:ENTRY_ROLL_LIMIT]):
        row = _bar(df, s)
        if _valid_open(row):
            return {"status": "ENTERED", "session": s, "price": float(row["open"]), "delay_sessions": i,
                    "tr_factor": _tr_factor(row)}
    if len(sessions) < ENTRY_ROLL_LIMIT:
        return {"status": "PENDING_ENTRY", "reason": "NO_VALID_OPEN_YET", "sessions_checked": len(sessions)}
    return {"status": "ENTRY_UNAVAILABLE", "reason": f"NO_VALID_OPEN_WITHIN_{ENTRY_ROLL_LIMIT}_SESSIONS"}


def _next_open(df, after: date, as_of: date):
    s = after
    for _ in range(ENTRY_ROLL_LIMIT):
        s = nyse_calendar.next_session(s)
        if s > as_of:
            return None
        row = _bar(df, s)
        if _valid_open(row):
            return s, float(row["open"]), _tr_factor(row)
    return "UNAVAILABLE"


def _alpha_at(lookup: Callable[[str, date], Optional[float]], ticker: str, d: date):
    try:
        return lookup(ticker, d) if lookup else None
    except Exception:
        return None


def _cost_table(p_in: float, p_out: float, bench: Optional[float], cost_bps) -> List[Dict[str, Any]]:
    out = []
    for bps in cost_bps:
        c = bps / 10_000.0
        net = ((1 - c) * p_out) / ((1 + c) * p_in) - 1
        out.append({"cost_bps_per_side": bps, "net_return": net,
                    "net_excess_vs_spy": (net - bench) if bench is not None else None,
                    "label": "HYPOTHETICAL cost assumption (not an observed execution cost)"})
    return out


def observation_outcome(obs: Dict[str, Any], prices: Dict[str, pd.DataFrame], as_of: date,
                        alpha_lookup: Optional[Callable[[str, date], Optional[float]]] = None,
                        cost_bps=DEFAULT_COST_BPS) -> Dict[str, Any]:
    from core.decision_engine import DecisionEngine      # frozen engine, called, never modified
    t = obs["ticker"]
    df, spy = prices.get(t), prices.get(BENCHMARK)
    planned = _d(obs["signal"]["entry_session"])
    out: Dict[str, Any] = {"observation_id": obs["observation_id"], "run_id": obs["run_id"], "ticker": t,
                           "observation_class": obs["observation_class"], "as_of_session": as_of.isoformat(),
                           "planned_entry_session": planned.isoformat(),
                           "market_phase_at_signal": obs["signal"]["market_phase"]}
    entry = find_entry(df, planned, as_of)
    out["entry"] = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in entry.items()}
    if entry["status"] != "ENTERED":
        out["outcome_state"] = "PENDING_OUTCOME" if entry["status"] == "PENDING_ENTRY" else "INCOMPLETE"
        out["incomplete_reason"] = entry.get("reason")
        return out
    e_day, p_in = entry["session"], entry["price"]
    spy_entry = _bar(spy, e_day)
    bench_ok = _valid_open(spy_entry)

    # Corporate actions: stops were set in the scan's price basis; rescale to this snapshot.
    ref = _d(obs["reference_session"]) if obs.get("reference_session") else None
    ref_row = _bar(df, ref) if ref else None
    basis = (float(ref_row["close"]) / float(obs["reference_close"])) if (
        ref_row is not None and _finite(obs.get("reference_close")) and obs["reference_close"]) else float("nan")
    splits = df.loc[(df.index > (ref or e_day)) & (df.index <= as_of), "splits"] if "splits" in df else pd.Series()
    out["corporate_actions"] = {
        "stop_basis_factor": basis,
        "splits_after_reference": {str(k): float(v) for k, v in splits[splits.fillna(0) != 0].items()},
        "dividends_in_window": {}, "note": "prices split-adjusted by provider; returns use one snapshot only"}

    sessions = [s for s in nyse_calendar.sessions_between(e_day, as_of)]
    closes = df["close"]
    portfolio = obs["observation_class"] == "PORTFOLIO_TOP5"
    engine = DecisionEngine()
    state = {"security_id": f"paper:{t}", "ticker": t, "lifecycle_state": "ENTRY_1_EXECUTED",
             "entry_date": datetime.combine(e_day, time(9, 30)).isoformat(),
             "hard_stop": (obs.get("hard_stop") or 0) * basis if portfolio and _finite(basis) else None,
             "trailing_stop": (obs.get("trailing_stop") or 0) * basis if portfolio and _finite(basis) else None,
             "entry_1_weight": obs.get("entry_1_weight"), "entry_2_weight": obs.get("entry_2_weight"),
             "target_weight": obs.get("target_weight"), "sector": obs.get("sector")}
    rule_path = portfolio and state["hard_stop"] is not None
    tw = obs.get("target_weight") or 0
    out["entry_fractions"] = ({"entry_1": obs["entry_1_weight"] / tw, "entry_2": obs["entry_2_weight"] / tw}
                              if portfolio and tw else None)
    events, pending_signal, entry2, exit_fill, end = [], None, None, None, None
    missing_sessions, horizon_review, gap = 0, None, 0
    path = []
    for s in sessions:
        row = _bar(df, s)
        if pending_signal:
            nxt = (s, float(row["open"]), _tr_factor(row)) if _valid_open(row) else None
            if nxt is None:
                missing_sessions += 1
                continue
            kind, reason = pending_signal
            if kind == "ENTRY_2":
                entry2 = {"session": s.isoformat(), "price": nxt[1], "tr_factor": nxt[2]}
                state["lifecycle_state"] = "FULL_POSITION"
                events.append({"session": s.isoformat(), "event": "ENTRY_2_FILLED", "price": nxt[1]})
                pending_signal = None
            else:
                exit_fill = {"session": s.isoformat(), "price": nxt[1], "tr_factor": nxt[2], "type": "OPEN",
                             "reason": reason}
                events.append({"session": s.isoformat(), "event": "EXIT_FILLED", "reason": reason, "price": nxt[1]})
                end = s
                path.append((s, nxt[1]))
                break
        if row is None:
            missing_sessions += 1
            gap += 1 if _bar(spy, s) is not None else 0
            if gap >= ENTRY_ROLL_LIMIT:
                out["outcome_state"] = "INCOMPLETE"
                out["incomplete_reason"] = f"DATA_GAP_{gap}_SESSIONS_WITH_BENCHMARK_BARS"
                break
            continue
        gap = 0
        path.append((s, float(row["close"])))
        if not rule_path:
            continue
        hist = closes[closes.index <= s]
        atr, ema20 = indicators_until(hist)
        if not (_finite(atr) and _finite(ema20)):
            continue
        as_of_dt = datetime.combine(s, time(16, 0))
        held = int(np.busday_count(e_day, s))
        alpha = None
        if held >= int(obs.get("horizon_days") or 30):
            alpha = _alpha_at(alpha_lookup, t, s)
            if alpha is None:
                horizon_review = "UNAVAILABLE_NO_SAME_DAY_SCAN"
                end = s
                break
        dec = engine.evaluate_existing_position(as_of_dt, state, {"close": float(row["close"]), "ema20": ema20,
                                                                  "atr": atr, "alpha": alpha if alpha is not None else 0})
        state["trailing_stop"] = dec.trailing_stop
        if dec.exit_candidate:
            pending_signal = ("EXIT", dec.exit_reason)
            events.append({"session": s.isoformat(), "event": "EXIT_SIGNAL", "reason": dec.exit_reason,
                           "close": float(row["close"])})
            if dec.exit_reason == "30D_REVIEW_NEGATIVE_ALPHA":
                horizon_review = "EXIT_NEGATIVE_ALPHA"
            continue
        if held >= int(obs.get("horizon_days") or 30):
            horizon_review = "HOLD_REVIEW_PASSED"
            end = s
            break
        if "ENTRY_2_CONFIRMED" in (dec.reason_codes or []) and state["lifecycle_state"] != "FULL_POSITION":
            pending_signal = ("ENTRY_2", "ENTRY_2_CONFIRMED")
            events.append({"session": s.isoformat(), "event": "ENTRY_2_SIGNAL", "close": float(row["close"])})

    # ---------------------------------------------------------------- returns
    if out.get("outcome_state") == "INCOMPLETE":
        out["frozen_rule_path"] = {"applied": rule_path, "events": events}
        return out
    out["frozen_rule_path"] = {"applied": rule_path,
                               "not_applied_reason": None if rule_path or not portfolio else "STOP_BASIS_UNAVAILABLE",
                               "events": events, "horizon_review": horizon_review,
                               "final_trailing_stop": state.get("trailing_stop"),
                               "initial_hard_stop": state.get("hard_stop"),
                               "missing_sessions": missing_sessions}
    out["entry_2"] = entry2
    if exit_fill is None and end is not None:
        row = _bar(df, end)
        exit_fill = {"session": end.isoformat(), "price": float(row["close"]), "tr_factor": _tr_factor(row),
                     "type": "CLOSE", "reason": "HORIZON_REACHED" if horizon_review else "MEASUREMENT_END"}
    completed = exit_fill is not None
    if not rule_path and exit_fill is None:
        # Non-portfolio (watchlist) diagnostics: frozen horizon only, no stops (no position sizing).
        horizon = [s for s in sessions if int(np.busday_count(e_day, s)) >= int(obs.get("horizon_days") or 30)]
        if horizon and _bar(df, horizon[0]) is not None:
            row = _bar(df, horizon[0])
            exit_fill = {"session": horizon[0].isoformat(), "price": float(row["close"]), "tr_factor": _tr_factor(row),
                         "type": "CLOSE", "reason": "HORIZON_REACHED"}
        completed = exit_fill is not None
    if exit_fill is None:
        last = next(((s, p) for s, p in reversed(path)), None)
        out["outcome_state"] = "PENDING_OUTCOME"
        out["mark"] = {"session": last[0].isoformat(), "price": last[1]} if last else None
        mark_price, mark_day, mark_type = (last[1], last[0], "CLOSE") if last else (None, None, None)
    else:
        out["outcome_state"] = "COMPLETED_OUTCOME" if completed else "PENDING_OUTCOME"
        mark_price, mark_day, mark_type = exit_fill["price"], _d(exit_fill["session"]), exit_fill["type"]
    out["exit"] = exit_fill
    if mark_price is None:
        return out

    r_price = mark_price / p_in - 1
    mrow = _bar(df, mark_day)
    tr_out = _tr_factor(mrow) if mrow is not None else float("nan")
    r_total = (mark_price * tr_out) / (p_in * entry["tr_factor"]) - 1 if _finite(tr_out) and _finite(
        entry["tr_factor"]) else None
    bench = bench_total = None
    srow = _bar(spy, mark_day)
    if bench_ok and srow is not None:
        s_out = float(srow["open"] if mark_type == "OPEN" else srow["close"])
        bench = s_out / float(spy_entry["open"]) - 1
        if _finite(_tr_factor(srow)) and _finite(_tr_factor(spy_entry)):
            bench_total = (s_out * _tr_factor(srow)) / (float(spy_entry["open"]) * _tr_factor(spy_entry)) - 1
    window = df[(df.index >= e_day) & (df.index <= mark_day)]
    divs = window["dividends"][window["dividends"].fillna(0) != 0] if "dividends" in window else pd.Series()
    out["corporate_actions"]["dividends_in_window"] = {str(k): float(v) for k, v in divs.items()}
    close_path = np.array([p for _, p in path] or [mark_price], dtype=float)
    peak = np.maximum.accumulate(np.concatenate([[p_in], close_path]))
    dd = np.concatenate([[p_in], close_path]) / peak - 1
    hl = window[window.index < mark_day] if mark_type == "OPEN" else window   # exit at open: no later intraday
    hi = hl["high"].max() if "high" in hl and hl["high"].notna().any() else float("nan")
    lo = hl["low"].min() if "low" in hl and hl["low"].notna().any() else float("nan")
    out["returns"] = {
        "basis": "entry-1 reference open -> exit fill (or mark); split-adjusted provider prices",
        "price_return": r_price, "total_return": r_total,
        "total_return_basis": "provider dividend adjustment (adj_close/close) applied to both legs",
        "benchmark": BENCHMARK, "benchmark_window": {"entry": e_day.isoformat(), "exit": mark_day.isoformat(),
                                                     "exit_price_type": mark_type},
        "benchmark_price_return": bench, "benchmark_total_return": bench_total,
        "excess_vs_spy_price": (r_price - bench) if bench is not None else None,
        "excess_vs_spy_total": (r_total - bench_total) if (r_total is not None and bench_total is not None) else None,
        "benchmark_status": "VALID" if bench is not None else "UNAVAILABLE",
        "mfe_intraday": (hi / p_in - 1) if _finite(hi) else None,
        "mae_intraday": (lo / p_in - 1) if _finite(lo) else None,
        "mfe_close": float(close_path.max() / p_in - 1), "mae_close": float(close_path.min() / p_in - 1),
        "max_drawdown_close": float(dd.min()),
        "sessions_in_window": len([s for s in sessions if s <= mark_day]),
        "cost_sensitivity": _cost_table(p_in, mark_price, bench, cost_bps),
    }
    diag = {}
    for h in DIAGNOSTIC_HORIZONS:
        if len(sessions) > h and _bar(df, sessions[h]) is not None:
            p = float(_bar(df, sessions[h])["close"])
            b = _bar(spy, sessions[h])
            br = (float(b["close"]) / float(spy_entry["open"]) - 1) if (bench_ok and b is not None) else None
            diag[f"{h}s"] = {"session": sessions[h].isoformat(), "price_return": p / p_in - 1,
                             "excess_vs_spy": (p / p_in - 1 - br) if br is not None else None}
        else:
            diag[f"{h}s"] = None
    out["diagnostic_fixed_horizons"] = {"label": "DIAGNOSTIC ONLY - not a strategy rule; close of the h-th "
                                                 "session after the entry session", "horizons": diag}
    return out


# ------------------------------------------------------------------ paper portfolio
def paper_portfolio(run: Dict[str, Any], outcomes: Dict[str, Dict[str, Any]], prices: Dict[str, pd.DataFrame],
                    as_of: date) -> Dict[str, Any]:
    """Original TOP-5, original weights and capital; staged frozen entries; no rebalancing."""
    capital = float(run.get("capital") or 0)
    res = {"run_id": run["run_id"], "capital": capital, "capital_source": run.get("capital_source"),
           "original_top5": run.get("top5"), "original_sector_exposure": run.get("sector_exposure"),
           "label": "PAPER portfolio from the original recommendation - not an actual investor return"}
    positions, flows = [], []
    for p in run.get("top5") or []:
        o = outcomes.get(f"{run['run_id']}:{p['ticker']}")
        if o is None:
            res["status"] = "RECONSTRUCTION_FAILED"
            res["reason"] = f"missing outcome for {p['ticker']}"
            return res
        positions.append((p, o))
    if any(o.get("outcome_state") == "INCOMPLETE" for _, o in positions):
        res["status"] = "INCOMPLETE"
    entered = [(p, o) for p, o in positions if (o.get("entry") or {}).get("status") == "ENTERED"]
    if not entered:
        res.setdefault("status", "PENDING_OUTCOME")
        res["value"] = capital
        return res
    start = min(_d(o["entry"]["session"]) for _, o in entered)
    ends = [_d(o["exit"]["session"]) for _, o in entered if o.get("exit")]
    all_done = len(ends) == len(positions) and all(o.get("outcome_state") == "COMPLETED_OUTCOME" for _, o in positions)
    end = max(ends) if all_done else as_of
    cash, holdings, divs, series, legs = capital, {}, 0.0, [], []
    for s in nyse_calendar.sessions_between(start, end):
        for p, o in entered:
            t, target = p["ticker"], capital * float(p.get("weight") or 0)
            fr = o.get("entry_fractions") or {"entry_1": 1.0, "entry_2": 0.0}
            legs_ = [(o["entry"]["session"], o["entry"]["price"], fr["entry_1"])]
            if o.get("entry_2"):
                legs_.append((o["entry_2"]["session"], o["entry_2"]["price"], fr["entry_2"]))
            for sess, price, frac in legs_:
                if _d(sess) == s:
                    notional = target * frac
                    holdings[t] = holdings.get(t, 0.0) + notional / price
                    cash -= notional
                    legs.append({"ticker": t, "session": sess, "price": price, "notional": notional})
            ex = o.get("exit")
            if ex and _d(ex["session"]) == s and o.get("outcome_state") == "COMPLETED_OUTCOME" and t in holdings:
                cash += holdings.pop(t) * ex["price"]
        value = cash
        for t, sh in holdings.items():
            row = _bar(prices.get(t), s)
            dv = row.get("dividends") if row is not None else None
            if _finite(dv) and dv:
                divs += sh * float(dv)
            if row is None:
                value = float("nan")
                break
            value += sh * float(row["close"])
        series.append((s, value))
    vals = np.array([v for _, v in series], dtype=float)
    spy = prices.get(BENCHMARK)
    s0, s1 = _bar(spy, start), _bar(spy, series[-1][0])
    bench = (float(s1["close"]) / float(s0["open"]) - 1) if (_valid_open(s0) and s1 is not None) else None
    final = vals[-1] if len(vals) else capital
    finite = vals[np.isfinite(vals)]
    peak = np.maximum.accumulate(np.concatenate([[capital], finite])) if len(finite) else np.array([capital])
    res.update({
        "status": res.get("status") or ("COMPLETED_OUTCOME" if all_done else "PENDING_OUTCOME"),
        "window": {"start": start.isoformat(), "end": series[-1][0].isoformat()},
        "fills": legs, "cash_end": cash, "open_positions": sorted(holdings),
        "value_end_price_basis": final, "dividends_received_cash": divs,
        "portfolio_return_price": final / capital - 1 if capital else None,
        "portfolio_return_with_dividends": (final + divs) / capital - 1 if capital else None,
        "spy_return_same_window": bench,
        "spy_comparison": "full capital in SPY at the first entry open, marked to the same end close",
        "excess_vs_spy": (final / capital - 1 - bench) if (bench is not None and capital) else None,
        "max_drawdown": float((np.concatenate([[capital], finite]) / peak - 1).min()) if len(finite) else 0.0,
        "uninvested_note": "frozen staged entry: 40% at entry #1, 60% only after the frozen EMA20 confirmation; "
                           "unfilled tranches stay in cash",
        "marked_values_missing_sessions": int((~np.isfinite(vals)).sum()),
    })
    return res


# ------------------------------------------------------------------ statistics
def _stats(vals: List[float]) -> Dict[str, Any]:
    a = np.array([v for v in vals if v is not None and math.isfinite(v)], dtype=float)
    if not len(a):
        return {"n": 0, "mean": None, "median": None, "std": None, "win_rate": None, "min": None, "max": None}
    return {"n": int(len(a)), "mean": float(a.mean()), "median": float(np.median(a)),
            "std": float(a.std(ddof=1)) if len(a) > 1 else None, "win_rate": float((a > 0).mean()),
            "min": float(a.min()), "max": float(a.max())}


def summarize(observations: List[Dict[str, Any]], outcomes: Dict[str, Dict[str, Any]],
              cohorts: Dict[str, Dict[str, Any]], portfolios: List[Dict[str, Any]],
              cost_bps=DEFAULT_COST_BPS) -> Dict[str, Any]:
    official = [o for o in observations if o["observation_class"] == "PORTFOLIO_TOP5"
                and cohorts[o["observation_id"]]["cohort"] == "VALID_PROSPECTIVE"]
    done = [outcomes[o["observation_id"]] for o in official
            if outcomes[o["observation_id"]].get("outcome_state") == "COMPLETED_OUTCOME"]
    r = [x["returns"]["price_return"] for x in done if x.get("returns")]
    ex = [x["returns"]["excess_vs_spy_price"] for x in done if x.get("returns")]
    by_rank = {}
    for o in official:
        x = outcomes[o["observation_id"]]
        if x.get("outcome_state") == "COMPLETED_OUTCOME" and x.get("returns"):
            by_rank.setdefault(str(o.get("recommendation_rank")), []).append(x["returns"]["price_return"])
    by_date = {}
    for o in official:
        x = outcomes[o["observation_id"]]
        if x.get("outcome_state") == "COMPLETED_OUTCOME" and x.get("returns"):
            by_date.setdefault(o["recommendation_timestamp_utc"][:10], []).append(x["returns"]["price_return"])
    costs = []
    for i, bps in enumerate(cost_bps):
        net = [x["returns"]["cost_sensitivity"][i]["net_return"] for x in done if x.get("returns")]
        netx = [x["returns"]["cost_sensitivity"][i]["net_excess_vs_spy"] for x in done if x.get("returns")]
        costs.append({"cost_bps_per_side": bps, "mean_net_return": _stats(net)["mean"],
                      "mean_net_excess_vs_spy": _stats([v for v in netx if v is not None])["mean"]})
    signs = {np.sign(c["mean_net_excess_vs_spy"]) for c in costs if c["mean_net_excess_vs_spy"] is not None}
    watch = [outcomes[o["observation_id"]] for o in observations if o["observation_class"] == "WATCHLIST_DIAGNOSTIC"
             and cohorts[o["observation_id"]]["cohort"] == "VALID_PROSPECTIVE"
             and outcomes[o["observation_id"]].get("outcome_state") == "COMPLETED_OUTCOME"]
    states = {}
    for o in official:
        s = outcomes[o["observation_id"]].get("outcome_state")
        states[s] = states.get(s, 0) + 1
    entries = [outcomes[o["observation_id"]]["entry"].get("session") for o in official
               if outcomes[o["observation_id"]]["entry"].get("session")]
    exits = [x["exit"]["session"] for x in done if x.get("exit")]
    n = len(r)
    vp = [p for p in portfolios if p.get("cohort") == "VALID_PROSPECTIVE"]
    vpd = [p for p in vp if p.get("status") == "COMPLETED_OUTCOME"]
    return {
        "official_scope": "VALID_PROSPECTIVE x PORTFOLIO_TOP5 x COMPLETED_OUTCOME",
        "valid_observations": len(official), "outcome_states": states,
        "completed_observations": n, "independent_runs": len({o["run_id"] for o in official}),
        "measurement_period": {"first_entry": min(entries) if entries else None,
                               "last_exit": max(exits) if exits else None},
        "sample_status": "NO_COMPLETED_OBSERVATIONS" if n == 0 else (
            "INSUFFICIENT_SAMPLE" if n < MIN_SAMPLE else "OBSERVATIONAL_ONLY"),
        "price_return": _stats(r), "excess_vs_spy": _stats([v for v in ex if v is not None]),
        "total_return": _stats([x["returns"]["total_return"] for x in done if x.get("returns")]),
        "mfe_close": _stats([x["returns"]["mfe_close"] for x in done if x.get("returns")]),
        "mae_close": _stats([x["returns"]["mae_close"] for x in done if x.get("returns")]),
        "max_drawdown_close": _stats([x["returns"]["max_drawdown_close"] for x in done if x.get("returns")]),
        "by_recommendation_rank": {k: _stats(v) for k, v in sorted(by_rank.items())},
        "by_recommendation_date": {k: _stats(v) for k, v in sorted(by_date.items())},
        "watchlist_diagnostic_price_return": _stats([x["returns"]["price_return"] for x in watch if x.get("returns")]),
        "cost_sensitivity": costs,
        "cost_sensitivity_conclusion_changes": len(signs) > 1,
        "paper_portfolios": {"valid": len(vp), "completed": len(vpd),
                             "mean_return_price": _stats([p.get("portfolio_return_price") for p in vpd])["mean"],
                             "mean_spy_return": _stats([p.get("spy_return_same_window") for p in vpd])["mean"],
                             "mean_excess_vs_spy": _stats([p.get("excess_vs_spy") for p in vpd])["mean"]},
        "transaction_costs_included": "gross figures exclude costs; see cost_sensitivity (hypothetical scenarios)",
        "statistical_caution": (
            f"{n} completed observation(s) from {len({o['run_id'] for o in official})} run(s). Observations from "
            "overlapping runs are not independent. No significance test is performed, no annualised figure is "
            "reported, and results are preliminary until at least 30 completed observations from many independent "
            "scan dates exist. Paper results are not actual investor returns."),
    }
