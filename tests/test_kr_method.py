"""KR-M1: each entry signal fires on the pattern the protocol names and reads nothing after its day, a trade follows the shared exit
rule, the pool is the top fifth of the unmarked stocks, the selection needs all four conditions, and the daily record is written once."""
import json
from datetime import date, timedelta

import numpy as np
import pytest

from terminal.qsf import kr_forward as kf, kr_method as km, research_kr as kr

N = 260


def arrays(close, volume=None):
    """Bars around a close path (days x stocks): the open is the previous close, the high and low sit 1% away."""
    close = np.asarray(close, dtype=float)
    if close.ndim == 1:
        close = close[:, None]
    vol = np.full(close.shape, 1000.0) if volume is None else np.asarray(volume, dtype=float).reshape(close.shape)
    return {"close": close, "open": np.vstack([close[:1], close[:-1]]), "high": close * 1.01, "low": close * 0.99, "volume": vol}


def fired(close, volume=None, i=None, cols=None):
    d = arrays(close, volume)
    cols = np.arange(d["close"].shape[1]) if cols is None else cols
    got = km.signals(d, len(d["close"]) - 1 if i is None else i, cols)
    return {m for m in km.METHODS if got[m][0]}


def rising(n=N, step=0.2):
    return 100 + step * np.arange(n, dtype=float)


def test_a_flat_stock_gives_no_signal_and_a_short_history_gives_none():
    assert fired(np.full(N, 100.0)) == set()
    assert fired(rising(km.NEED_BARS - 1)) == set()


def test_pullback_fires_when_the_close_recovers_its_five_day_line_after_three_closes_under_it():
    c = rising()
    c[-4:-1] = c[-5] - np.array([1.5, 3.0, 4.5])
    c[-1] = c[-2] + 5
    assert "R1" in fired(c)
    c[-3] = c[-5] + 3                      # only two closes under the line: no pullback
    assert "R1" not in fired(c)


def test_oversold_bounce_needs_a_low_two_day_rsi_above_the_200_day_line():
    c = rising()
    c[-2:] = c[-3] - np.array([1.0, 2.0])
    assert "R2" in fired(c)
    down = 200 - 0.2 * np.arange(N, dtype=float)          # the same drop under the 200-day line
    down[-2:] = down[-3] - np.array([1.0, 2.0])
    assert "R2" not in fired(down)


def test_band_reentry_fires_the_day_after_a_close_under_the_lower_band():
    c = np.where(np.arange(N) % 2 == 0, 100.0, 100.5)
    c[-2], c[-1] = 98.0, 100.0
    assert "R3" in fired(c)
    c[-1] = 97.0                           # still under the band
    assert "R3" not in fired(c)


def test_breakout_needs_a_close_over_the_20_day_high_on_one_and_a_half_times_the_volume():
    c, v = np.full(N, 100.0), np.full(N, 1000.0)
    c[-1], v[-1] = 105.0, 3000.0
    assert "T1" in fired(c, v)
    v[-1] = 1400.0
    assert "T1" not in fired(c, v)
    c[-1], v[-1] = 100.9, 3000.0           # under the highest high of the last 20 sessions
    assert "T1" not in fired(c, v)


def test_squeeze_breakout_needs_a_narrow_band_the_day_before():
    c = 100 + np.where(np.arange(N) % 2 == 0, 2.0, -2.0)
    c[-26:-1] = 100 + np.where(np.arange(25) % 2 == 0, 0.1, -0.1)
    c[-1] = 103.0
    assert "T2" in fired(c)
    wide = 100 + np.where(np.arange(N) % 2 == 0, 2.0, -2.0)
    wide[-1] = 110.0                       # a breakout without the squeeze
    assert "T2" not in fired(wide)


def test_alignment_fires_only_on_the_day_the_three_lines_line_up():
    c = np.full(N, 100.0)
    c[-1] = 101.0
    assert "T3" in fired(c)
    c = np.append(c, 102.0)                # the day after: already lined up
    assert "T3" not in fired(c)


def test_relative_strength_needs_the_top_fifth_of_the_universe_and_a_cross_of_the_20_day_line():
    flat = np.full((N, 10), 100.0)
    strong = np.concatenate([np.linspace(50, 100, N - 21), np.full(20, 97.0), [101.0]])
    flat[:, 0] = strong
    assert "T4" in fired(flat)
    alone = fired(flat[:, :1])             # nobody to be stronger than
    assert "T4" not in alone
    weak = flat.copy()
    weak[:, 0] = np.concatenate([np.full(N - 21, 100.0), np.full(20, 97.0), [101.0]])
    weak[:, 1] = strong[::-1].copy()
    weak[:, 1] = np.linspace(50, 100, N)   # another stock holds the top fifth
    assert "T4" not in fired(weak)


def test_signals_read_nothing_after_their_day_and_a_missing_bar_means_no_signal():
    rng = np.random.default_rng(5)
    c = 100 * np.cumprod(1 + rng.normal(0, 0.02, (N + 30, 40)), axis=0)
    d = arrays(c, rng.uniform(500, 3000, c.shape))
    cols = np.arange(40)
    before = {m: v.copy() for m, v in km.signals(d, N, cols).items()}
    for k in d:
        d[k][N + 1:] *= 5
    after = km.signals(d, N, cols)
    assert all(np.array_equal(before[m], after[m]) for m in km.METHODS) and sum(v.sum() for v in before.values()) > 0
    p = rising()
    p[-4:-1] = p[-5] - np.array([1.5, 3.0, 4.5])
    p[-1] = p[-2] + 5
    p[-3] = np.nan
    assert fired(p) == set()


def test_atr_is_the_mean_true_range_of_fourteen_sessions():
    c = np.full(40, 100.0)
    d = arrays(c)
    assert km.atr(d, 39, np.array([0]))[0] == pytest.approx(2.0)
    d["high"][30:, 0] = np.nan             # nine sessions left: too few
    assert np.isnan(km.atr(d, 39, np.array([0]))[0])
    assert np.isnan(km.atr(d, 5, np.array([0]))[0])


def bars(n=14, level=100.0):
    return [np.full(n, level) for _ in range(4)]


def test_a_trade_enters_at_the_next_open_and_leaves_by_stop_target_or_time():
    cost = 0.0053
    o, h, lo, c = bars()
    t = km.simulate(o, h, lo, c, 0, 2.0, cost)
    assert t["reason"] == "TIME" and t["entry_row"] == 1 and t["exit_row"] == 10 and t["days"] == 10 and t["net"] == pytest.approx(-cost)
    o, h, lo, c = bars()
    lo[3] = 95.0
    t = km.simulate(o, h, lo, c, 0, 2.0, cost)
    assert t["reason"] == "STOP" and t["exit"] == 96.0 and t["days"] == 3 and t["net"] == pytest.approx(-0.04 - cost)
    o, h, lo, c = bars()
    h[2] = 107.0
    assert km.simulate(o, h, lo, c, 0, 2.0, cost)["exit"] == 106.0
    lo[2] = 95.0                           # both levels inside one bar: the stop counts
    assert km.simulate(o, h, lo, c, 0, 2.0, cost)["reason"] == "STOP"
    o, h, lo, c = bars()
    lo[1] = 95.9                           # the entry day itself can stop the trade
    assert km.simulate(o, h, lo, c, 0, 2.0, cost)["days"] == 1


def test_a_gap_fills_at_the_open_and_a_stock_gone_early_closes_at_its_last_trade():
    o, h, lo, c = bars()
    o[4], lo[4] = 94.0, 93.0
    t = km.simulate(o, h, lo, c, 0, 2.0, 0.0)
    assert t["reason"] == "STOP" and t["exit"] == 94.0
    o, h, lo, c = bars()
    o[4], h[4] = 108.0, 109.0
    t = km.simulate(o, h, lo, c, 0, 2.0, 0.0)
    assert t["reason"] == "TARGET" and t["exit"] == 108.0
    o, h, lo, c = bars()
    c[5] = 101.0
    for a in (o, h, lo, c):
        a[6:] = np.nan
    t = km.simulate(o, h, lo, c, 0, 2.0, 0.0)
    assert t["reason"] == "GONE" and t["exit"] == 101.0 and t["exit_row"] == 10


def test_no_open_or_no_atr_is_no_trade_and_an_unfinished_trade_stays_open():
    o, h, lo, c = bars()
    o[1] = np.nan
    assert km.simulate(o, h, lo, c, 0, 2.0, 0.0) is None
    o, h, lo, c = bars()
    assert km.simulate(o, h, lo, c, 0, float("nan"), 0.0) is None and km.simulate(o, h, lo, c, 13, 2.0, 0.0) is None
    o, h, lo, c = bars(6)
    c[5] = 102.0
    t = km.simulate(o, h, lo, c, 0, 2.0, 0.0)
    assert t["open"] is True and t["gross"] == pytest.approx(0.02) and t["stop"] == 96.0 and t["target"] == 106.0


def test_a_method_takes_no_new_signal_on_a_stock_it_still_holds():
    d = {k: np.full((40, 1), 100.0) for k in ("open", "high", "low", "close")}
    b = km.Book(d, 0.0)
    assert b.take(0, 0, 2.0, 0) is not None and b.take(0, 5, 2.0, 0) is None        # held through row 10
    assert b.take(0, 10, 2.0, 1) is not None and len(b.trades) == 2
    assert b.take(0, 12, 2.0, 1, scale=float("nan")) is None                        # the record's ATR could not be rescaled


def test_the_pool_is_the_top_fifth_of_the_stocks_without_a_mark():
    scores = {f"{n:06d}": float(n) for n in range(10)}
    scores["000003"] = None
    pool = km.pool_of(scores, {"000009", "000008"}, {"000007"})
    assert pool == ["000006", "000005"]              # six left, a fifth rounded up is two
    assert km.pool_of({}, set(), set()) == [] and km.pool_of({"a": 1.0, "b": 1.0}, set(), set()) == ["a"]


def trade(net, block, reason="TIME"):
    return {"net": net, "block": block, "reason": reason, "days": 10, "open": False}


def test_trades_are_read_by_expectancy_and_block_by_block_against_the_baseline():
    t = [trade(0.06, 0, "TARGET"), trade(-0.04, 0, "STOP"), trade(0.06, 1, "TARGET"), trade(-0.04, 2, "STOP"), {"open": True, "block": 2}]
    s = km.stats(t)
    assert s["trades"] == 4 and s["mean_net"] == pytest.approx(0.01) and s["win_rate"] == 0.5 and s["payoff"] == pytest.approx(1.5) and s["exits"]["STOP"] == 0.5
    assert km.stats([]) == {"trades": 0}
    base = [trade(0.0, 0), trade(0.01, 1), trade(-0.01, 3)]
    cmp_ = km.compare(t, base)
    assert cmp_["blocks"] == 2 and cmp_["mean_diff"] == pytest.approx((0.01 + 0.05) / 2)      # block 2 has no baseline trade, block 3 no method trade
    assert km.drawdown(t, 3) == pytest.approx(-0.04) and km.drawdown([], 3) is None


def test_selection_needs_all_four_conditions_and_names_at_most_two():
    def r(trades, mean, diff, t, early, late):
        return {"trades": trades, "mean_net": mean, "mean_net_minus_b0": diff, "vs_b0": {"t": t, "early": early, "late": late}}
    readings = {m: r(500, 0.001, -0.001, 0.5, 0.0, 0.0) for m in km.METHODS}
    assert km.select(readings)["verdict"] == "NO_PRIMARY" and km.select(readings)["primary"] == []
    readings["R1"] = r(500, 0.010, 0.006, 3.0, 0.004, 0.008)
    readings["R2"] = r(500, 0.012, 0.008, 2.5, 0.004, 0.008)
    readings["R3"] = r(500, 0.011, 0.007, 2.6, 0.004, 0.008)
    readings["T1"] = r(299, 0.030, 0.020, 5.0, 0.010, 0.010)        # too few trades
    readings["T2"] = r(500, 0.030, 0.020, 2.44, 0.010, 0.010)       # t just under the bar
    readings["T3"] = r(500, 0.030, 0.020, 5.0, 0.010, -0.001)       # one half under the baseline
    got = km.select(readings)
    assert got["passed"] == ["R2", "R3", "R1"] and got["primary"] == ["R2", "R3"] and got["verdict"] == "PRIMARY_NAMED"
    assert got["checks"]["T1"]["trades"] is False and got["checks"]["T2"]["t"] is False and got["checks"]["T3"]["both_halves"] is False


def panel(days=330, stocks=40, seed=11):
    rng = np.random.default_rng(seed)
    c = 10000 * np.cumprod(1 + rng.normal(0, 0.02, (days, stocks)), axis=0)
    d = arrays(c, rng.uniform(500, 3000, c.shape))
    d["high"], d["low"] = np.maximum(d["high"], d["open"]), np.minimum(d["low"], d["open"])
    return d


def test_the_selection_run_follows_every_method_and_both_baselines_in_half_period_blocks():
    d = panel()
    dates = [f"2020-{n:04d}" for n in range(330)]
    codes = [f"{j:05d}0" for j in range(40)]
    col = {c: j for j, c in enumerate(codes)}
    rows = [260, 281, 302]
    by_row = {e: [{"i": e, "t": c, "SWING|FUNDAMENTAL": float(j), "SWING|RISK": float(j)} for j, c in enumerate(codes)] for e in rows}
    got = km.run_selection(d, col, dates, rows, by_row, lambda day: {codes[39]}, 0.0053)
    assert got["blocks"] == 6 and got["verdict"] == "NO_PRIMARY" and got["last_signal"] == dates[319]
    assert got["pools"][0] == {"date": dates[260], "universe": 40, "pool": 8}          # 39 unmarked, a fifth rounded up
    assert got["readings"]["B00"]["trades"] == 40 * 6 and got["readings"]["B0"]["trades"] == 8 * 6      # blocks start at rows 260, 270, 281, 291, 302 and 312; all end on file
    assert set(got["readings"]) == set(km.METHODS + km.BASELINES) and all("by_year" in r for r in got["readings"].values())
    assert km.past_score({"SWING|FUNDAMENTAL": 60.0, "SWING|RISK": 30.0}) == pytest.approx(40.0) and km.past_score({"SWING|RISK": 30.0}) is None


def test_past_marks_are_read_from_the_newest_grid_day_not_after_the_evaluation_day():
    marks = {"dates": ["2020-01-02", "2020-01-09"], "symbols": ["A", "B", "C"], "high_risk": np.array([[True, False, False], [False, False, False]]),
             "weak_fund": np.array([[False, False, False], [False, True, False]]), "financing": np.array([[False, False, False], [False, False, True]])}
    assert km.marked_on(marks, "2020-01-01") == set() and km.marked_on(marks, "2020-01-08") == {"A"} and km.marked_on(marks, "2020-01-09") == {"B", "C"}


def world(days=300, stocks=260):
    d = panel(days, stocks, seed=2)
    z = {**d, "dates": np.array([(date(2025, 6, 1) + timedelta(days=n)).isoformat() for n in range(days)]), "symbols": np.array([f"{j:05d}0" for j in range(stocks - 1)] + [kr.MARKET]),
         "value": np.full((days, stocks), 5e9), "cap": np.full((days, stocks), 1e11), "watch": np.zeros((days, stocks), dtype=bool), "adj_close": d["close"]}
    codes = [str(s) for s in z["symbols"][:240]]
    return z, codes


def snaps_of(codes, session, score=lambda n: 30.0 + n / 4):
    return [{"ticker": c, "strategy": "SWING", "score": score(n), "actionability": "ACTIONABLE", "data_date": session, "model_version": "QSF-1.3.1",
             "gates": [{"code": km.BLOCKED}] if n == 239 else []} for n, c in enumerate(codes)]


def marks_for(codes):
    m = {"high_risk": set(codes[230:239]), "weak_fund": set(codes[220:230]), "financing": {codes[238]}, "known": set(codes[:239])}
    m["any"] = m["high_risk"] | m["weak_fund"] | m["financing"]
    return m


def test_the_daily_record_holds_what_the_method_saw_and_no_return():
    z, codes = world()
    session = str(z["dates"][-1])
    doc = km.build_doc(session, snaps_of(codes, session), marks_for(codes), z, 20, {codes[0]: {"score": 33.0, "grade": "LOW"}})
    rows = {r["code"]: r for r in doc["rows"]}
    assert doc["universe"] == 240 and doc["order"] == 20 and doc["baseline_entry"] is True and doc["model_versions"] == ["QSF-1.3.1"]
    assert doc["pool"] == 44 and [c for c, r in rows.items() if r["pool"]] == codes[176:220]      # 239 stocks, 19 marked, 1 blocked: 220 left, a fifth is 44
    assert rows[codes[239]]["blocked"] is True and rows[codes[239]]["marks"] is None and rows[codes[238]]["marks"] == ["high_risk", "financing"]
    assert rows[codes[0]]["risk"] == {"score": 33.0, "grade": "LOW"} and "risk" not in rows[codes[1]] and rows[codes[5]]["atr"] > 0
    assert all(set(v) <= {c for c, r in rows.items() if r["pool"]} for v in doc["signals"].values()) and not any("net" in r or "ret" in r for r in doc["rows"])
    assert km.build_doc(session, snaps_of(codes, session), marks_for(codes), z, 21, None)["baseline_entry"] is False
    with pytest.raises(km.NotReady, match="TOO_FEW_SCORES"):
        km.build_doc(session, snaps_of(codes[:150], session), marks_for(codes), z, 0, None)
    with pytest.raises(km.NotReady, match="NO_PRICES_FOR_DAY"):
        km.build_doc("2027-01-01", snaps_of(codes, session), marks_for(codes), z, 0, None)
    stale = snaps_of(codes, "2020-01-01")           # a score of another day is not that day's score
    with pytest.raises(km.NotReady, match="TOO_FEW_SCORES"):
        km.build_doc(session, stale, marks_for(codes), z, 0, None)


class FakeLedger:
    days = []

    def __init__(self, base):
        pass

    def _live_rows(self):
        return [{"market": "KR", "session": d} for d in self.days] + [{"market": "US", "session": "2026-03-01"}]


def recorder(monkeypatch, z, codes, fail=None):
    """The record run on a made-up world: the live ledger, the marks and the price files are replaced, the writer is the real one."""
    fail = fail or {}
    monkeypatch.setattr(km, "Ledger", FakeLedger)
    dates = [str(x) for x in z["dates"]]

    def scorer(base, day):
        if day in fail:
            raise km.NotReady(fail[day])
        i = dates.index(day)
        cut = {k: (v[:i + 1] if k != "symbols" else v) for k, v in z.items()}
        return km.build_doc(day, snaps_of(codes, day), marks_for(codes), cut, len(kf.read_index(base, km.FOLDER)), None)
    monkeypatch.setattr(km, "score_day", scorer)
    monkeypatch.setattr(km, "_prices", lambda base, first, last: z)


def test_the_record_is_written_once_in_session_order_and_waits_for_a_day_that_is_not_ready(tmp_path, monkeypatch):
    z, codes = world()
    dates = [str(x) for x in z["dates"]]
    fail = {dates[282]: "MARKS_NOT_RECORDED"}
    recorder(monkeypatch, z, codes, fail)
    FakeLedger.days = dates[278:284] + ["2024-01-01"]
    got = km.record(tmp_path, first=dates[280])
    assert got["status"] == "WAITING" and got["written"] == dates[280:282] and got["waiting"] == {"session": dates[282], "reason": "MARKS_NOT_RECORDED"}
    fail.clear()
    fail[dates[282]] = "TOO_FEW_SCORES"            # a partial live day is passed over, not waited for
    got = km.record(tmp_path, first=dates[280])
    assert got["status"] == "OK" and got["written"] == [dates[283]] and got["partial_days"] == [dates[282]]
    again = km.record(tmp_path, first=dates[280])
    assert again["written"] == [] and again["sessions"] == 3
    index = kf.read_index(tmp_path, km.FOLDER)
    assert [r["session"] for r in index] == [dates[280], dates[281], dates[283]] and kf.verify(tmp_path, km.FOLDER)["status"] == "OK"
    assert [kf._read_day(tmp_path / km.FOLDER, r["session"])["order"] for r in index] == [0, 1, 2]


def test_following_the_record_rescales_the_recorded_atr_to_the_prices_on_file():
    z, codes = world()
    dates = [str(x) for x in z["dates"]]
    s = 280
    j = 3
    close = float(z["close"][s, j])
    doc = {"session": dates[s], "order": 0, "baseline_entry": True,
           "rows": [{"code": codes[j], "pool": True, "signals": ["R1"], "close": close / 2, "atr": 50.0},          # recorded on a price basis half of this build
                    {"code": codes[4], "pool": False, "signals": ["R1"], "close": float(z["close"][s, 4]), "atr": 100.0},
                    {"code": codes[5], "pool": True, "signals": [], "close": None, "atr": None}]}
    got = km.follow([doc], z, 0.0)
    assert [t["code"] for t in got["R1"]] == [codes[j]] and len(got["B0"]) == 1 and len(got["B00"]) == 2 and got["T1"] == []
    t = got["R1"][0]
    entry = float(z["open"][s + 1, j])
    direct = km.simulate(z["open"][:, j], z["high"][:, j], z["low"][:, j], z["close"][:, j], s, 100.0, 0.0)
    assert t["entry"] == entry and t["net"] == pytest.approx(direct["net"]) and t["signal_day"] == dates[s] and t["entry_day"] == dates[s + 1]
    assert km.follow([{**doc, "session": "2030-01-01"}], z, 0.0)["R1"] == []
    assert km.matured([{"session": dates[289]}, {"session": dates[290]}], dates) == [dates[289]]


def test_the_view_and_the_two_readings_come_from_the_record(tmp_path, monkeypatch):
    z, codes = world()
    dates = [str(x) for x in z["dates"]]
    recorder(monkeypatch, z, codes)
    assert km.status(tmp_path)["status"] == "NO_RECORD" and km.progress(tmp_path)["status"] == "NO_RECORD"
    FakeLedger.days = dates[270:296]
    km.record(tmp_path, first=dates[270])
    view = km.write_status(tmp_path)
    assert view["status"] == "REAL" and view["sessions"] == 26 and view["matured"] == 20 and view["last"] == dates[295] and km.status(tmp_path)["sessions"] == 26
    b00 = view["methods"]["B00"]          # entries on record days 0, 10 and 20; the last ones are still running unless a level was touched
    assert b00["trades"] + b00["open_count"] == 240 * 3 and b00["trades"] >= 240 * 2 and view["methods"]["B0"]["trades"] >= 2
    assert set(view["methods"]) == set(km.METHODS + km.BASELINES) and view["primary"] == [] and "판정 전" in view["note"]
    with pytest.raises(ValueError):
        km.evaluate_once(tmp_path, 60)
    assert km.evaluate_once(tmp_path, 120, log=lambda m: None) == {"status": "NOT_READY", "matured": 20, "needed": 120}
    monkeypatch.setattr(km, "READ_AT", (10, 240))
    first = km.evaluate_once(tmp_path, 10, log=lambda m: None)
    assert first["status"] == "REAL" and first["verdict"] == "NO_PRIMARY" and first["signal_days"] == 10 and first["last"] == dates[279] and first["model_version_days"] == {"QSF-1.3.1": 10}
    assert first["readings"]["B00"]["trades"] == 240 and km.evaluate_once(tmp_path, 10)["status"] == "ALREADY_RUN"
    (tmp_path / km.SELECTION).write_text(json.dumps({"primary": ["R1"]}), encoding="utf-8")
    km.forward_report(tmp_path, 10).unlink()
    assert km.evaluate_once(tmp_path, 10, log=lambda m: None)["verdict"]["R1"] in ("METHOD_SUPPORTED", "NOT_DISTINGUISHED") and km.primaries(tmp_path) == ["R1"]
