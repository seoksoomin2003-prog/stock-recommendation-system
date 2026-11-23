"""The order plan (priority, limits, costs) and the paper book that follows it (reports/PAPER_BOOK_RULES.md).  All offline."""
from datetime import date, datetime, timedelta, timezone

import pytest

from terminal import portfolio as pf
from terminal.qsf import config, kr_forward as kf, order_plan as op, paper_book as pb


def snap(ticker, strategy="SWING", score=60.0, price=100.0, atr=2.0, session="2026-11-12", entry="ENTRY_NOW", actionability="ACTIONABLE", adv=1e10, target=None):
    return {"ticker": ticker, "strategy": strategy, "score": score, "price": price, "stop": price - 2 * atr, "target": target or price + 3 * atr, "data_date": session,
            "actionability": actionability, "entry_status": entry, "factors": [{"factor": "liquidity", "raw": {"adv_value": adv}}], "model_version": config.MODEL_VERSION}


def filler(session, n=210):
    return [snap(f"F{k:03d}", score=30.0, session=session, entry="NO_VALID_ENTRY_SETUP") for k in range(n)]


# ---------------------------------------------------------------------- costs
def test_fees_are_the_published_ones_and_slippage_grows_with_the_order():
    assert op.fees("KR", 1_000_000, "BUY") == pytest.approx(150.0) and op.fees("KR", 1_000_000, "SELL") == pytest.approx(150.0 + 2000.0)
    assert op.fees("US", 10_000, "BUY") == pytest.approx(10.0) and op.fees("US", 10_000, "SELL") == pytest.approx(10.0 + 0.206)
    small, big = op.slippage_bps("KR", 1e6, 1e10, 0.03), op.slippage_bps("KR", 1e8, 1e10, 0.03)
    assert small["spread"] == big["spread"] == 15.0 and small["impact"] == pytest.approx(1e4 * 0.03 * 0.01) and big["impact"] == pytest.approx(10 * small["impact"])
    assert big["total"] == pytest.approx(15.0 + big["impact"])
    unknown = op.slippage_bps("US", 1e4, None, 0.02)
    assert unknown == {"spread": 10.0, "impact": None, "total": 10.0}            # an unknown impact is not a zero impact: it is shown as unknown


# ---------------------------------------------------------------------- candidates
def test_candidates_are_what_the_program_reads_as_enterable_now_in_score_order():
    snaps = [snap("A", score=58), snap("B", score=66), snap("C", score=90, entry="WAIT_FOR_PULLBACK"), snap("D", score=95, actionability="BLOCKED"),
             snap("E", "LONG_TERM", score=72, price=200.0, atr=4.0), snap("G", score=99, session="2026-11-11"), {**snap("H", score=80), "stop": None}]
    got = op.candidates(snaps, "2026-11-12", {"B": {"name": "비", "sector": "IT"}})
    assert [c["ticker"] for c in got] == ["H", "E", "B", "A"]
    by = {c["ticker"]: c for c in got}
    assert by["B"]["name"] == "비" and by["B"]["sector"] == "IT" and by["B"]["stop"] == 96.0 and by["B"]["target"] == 106.0 and by["B"]["atr"] == 2.0 and by["B"]["style"] == "SWING"
    assert by["E"]["style"] == "LONG" and by["E"]["stop"] == pytest.approx(200.0 - 5 * 4.0) and by["E"]["target"] is None and by["H"]["stop"] is None


# ---------------------------------------------------------------------- the plan
def account(equity=10_000_000.0, cash=None, positions=None):
    return {"equity": equity, "cash": equity if cash is None else cash, "positions": positions or {}}


def cand(ticker, style="SWING", score=60.0, close=10_000.0, atr=200.0, adv=1e11, sector=None):
    return {"ticker": ticker, "name": ticker, "sector": sector, "style": style, "score": score, "close": close, "atr": atr, "stop": close - (2 if style == "SWING" else 5) * atr,
            "target": close + 3 * atr if style == "SWING" else None, "adv_value": adv, "session": "2026-11-12"}


def test_the_plan_sizes_by_the_tightest_limit_and_reserves_cash_at_the_limit_price():
    got = op.build([cand("A")], account(), "KR")
    o = got["orders"][0]
    # Korea, swing: 0.5% risk of 10,000,000 = 50,000 over a 400 stop distance = 125 shares; 10% weight = 100 shares
    assert o["shares"] == 100 and o["binding"] == "WEIGHT" and o["limit"] == 10_100.0 and o["weight_pct"] == pytest.approx(10.0) and o["risk_pct"] == pytest.approx(0.4)
    assert got["cash_after"] == pytest.approx(10_000_000 - 100 * 10_100 * 1.00015) and o["fee_buy"] == pytest.approx(150.0) and o["fee_sell"] == pytest.approx(2150.0)
    assert o["slippage_bps"]["spread"] == 15.0 and o["participation_pct"] == pytest.approx(0.001) and o["est_round_trip_pct"] > 0.23 + 0.30
    wide = op.build([cand("A", atr=1000.0)], account(), "KR")["orders"][0]
    assert wide["binding"] == "RISK" and wide["shares"] == 25


def test_score_decides_who_goes_first_and_the_sleeve_stops_the_rest():
    cands = [cand(t, score=s) for t, s in (("A", 61), ("B", 69), ("C", 65), ("D", 63))]
    got = op.build(sorted(cands, key=lambda c: -c["score"]), account(), "KR")
    assert [o["ticker"] for o in got["orders"]] == ["B", "C", "D"]                  # swing sleeve: 30% of equity at 10% each
    assert got["skipped"] == [{"ticker": "A", "name": "A", "style": "SWING", "score": 61, "code": "SLEEVE_FULL", "reason": "스타일 비중 한도 도달"}]
    assert got["sleeve"]["SWING"]["value"] == pytest.approx(3_000_000) and got["sleeve"]["SWING"]["cap"] == pytest.approx(3_000_000) and got["sleeve"]["LONG"]["cap"] == pytest.approx(7_000_000)
    longs = op.build([cand(t, "LONG", score=70 - n, atr=100.0) for n, t in enumerate("ABCDE")], account(), "KR")
    assert [o["shares"] for o in longs["orders"]] == [200, 200, 200, 100] and longs["orders"][-1]["binding"] == "SLEEVE" and longs["skipped_counts"] == {"SLEEVE_FULL": 1}


def test_a_stock_gets_one_order_and_held_stocks_none():
    cands = [cand("A", "LONG", score=80, atr=100.0), cand("A", "SWING", score=75), cand("B", score=70), cand("C", score=60)]
    held = {"B": {"style": "SWING", "value": 500_000.0, "sector": None}}
    got = op.build(cands, account(positions=held, cash=9_500_000.0), "KR")
    assert [(o["ticker"], o["style"]) for o in got["orders"]] == [("A", "LONG"), ("C", "SWING")] and got["skipped_counts"] == {"ALREADY_PLANNED": 1, "ALREADY_HELD": 1}


def test_sector_cash_liquidity_and_missing_inputs_each_have_their_own_reading():
    sec = op.build([cand(t, "LONG", score=80 - n, atr=100.0, sector="반도체") for n, t in enumerate("ABC")], account(), "KR")
    assert [o["shares"] for o in sec["orders"]] == [200, 200] and sec["skipped_counts"] == {"SECTOR_FULL": 1}             # 40% sector limit at 20% each
    poor = op.build([cand("A"), cand("B", score=50)], account(cash=600_000.0), "KR")
    assert poor["orders"][0]["shares"] == 59 and poor["orders"][0]["binding"] == "CASH" and poor["skipped_counts"] == {"NO_CASH": 1}
    thin = op.build([cand("A", adv=5e7)], account(), "KR")["orders"][0]
    assert thin["shares"] == 50 and thin["binding"] == "LIQUIDITY" and thin["participation_pct"] == pytest.approx(1.0) and thin["slippage_bps"]["impact"] == pytest.approx(1e4 * 0.02 * 0.1)
    odd = op.build([{**cand("A"), "stop": None}, {**cand("B"), "adv_value": None}, cand("C", close=2_000_000.0, atr=40_000.0)], account(), "KR")
    assert odd["orders"] == [] and odd["skipped_counts"] == {"NO_STOP": 1, "NO_LIQUIDITY": 1, "TOO_SMALL": 1}
    us = op.build([cand("AAPL", close=200.0, atr=4.0, adv=5e9)], account(equity=10_000.0), "US")["orders"][0]
    assert us["shares"] == 5 and us["binding"] == "WEIGHT" and us["fee_buy"] == pytest.approx(1.0) and us["slippage_bps"]["spread"] == 10.0     # US swing: 1% risk, 10% weight


# ---------------------------------------------------------------------- the paper book, one session at a time
def calendar(n, start=date(2026, 11, 12)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def loader_of(series):
    """``series``: {ticker: [(day, open, close), ...]}."""
    return lambda t: [{"date": d, "open": o, "close": c, "adj_close": c} for d, o, c in series.get(t, [])]


def test_the_first_session_only_plans_and_the_next_open_fills_with_fee_and_slippage():
    days = calendar(3)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_050, 10_200), (days[2], 10_200, 10_300)]}))
    one = pb.step(None, days[0], "KR", bars, filler(days[0]) + [snap("A", price=10_000.0, atr=200.0, session=days[0], adv=1e11)])
    assert one["fills"] == [] and one["exits"] == [] and one["equity"] == pb.START_CASH["KR"] and [o["ticker"] for o in one["plan"]["orders"]] == ["A"] and one["plan"]["scored"]
    assert one["state"]["plan"][0]["shares"] == 100 and one["rows"] == one["plan"]["orders"]
    two = pb.step(one["state"], days[1], "KR", bars, None)
    f = two["fills"][0]
    slip = op.slippage_bps("KR", 100 * 10_050, 1e11, 200 / 10_050)["total"]
    assert f["qty"] == 100 and f["open"] == 10_050 and f["price"] == pytest.approx(10_050 * (1 + slip / 1e4)) and f["fee"] == pytest.approx(100 * f["price"] * 0.00015)
    p = two["state"]["positions"]["A"]
    assert p["sessions"] == 1 and p["last_close"] == 10_200 and p["stop"] == 9_600 and p["target"] == 10_600 and p["cost"] == pytest.approx(100 * f["price"] + f["fee"])
    assert two["cash"] == pytest.approx(pb.START_CASH["KR"] - p["cost"]) and two["equity"] == pytest.approx(two["cash"] + 100 * 10_200) and two["plan"]["scored"] is False
    assert two["state"]["plan"] == [] and two["state"]["fees"] == pytest.approx(f["fee"]) and two["state"]["slippage"] == pytest.approx(100 * (f["price"] - 10_050))


def test_an_open_above_the_limit_or_under_the_stop_is_not_chased():
    days = calendar(2)
    plan = filler(days[0]) + [snap(t, price=10_000.0, atr=200.0, session=days[0], adv=1e11, score=60 + n) for n, t in enumerate("ABC")]
    bars = pb.Bars(loader_of({"A": [(days[0], 1, 10_000), (days[1], 10_101, 10_200)], "B": [(days[0], 1, 10_000), (days[1], 9_600, 9_500)], "C": [(days[0], 1, 10_000)]}))
    one = pb.step(None, days[0], "KR", bars, plan)
    two = pb.step(one["state"], days[1], "KR", bars, None)
    assert two["fills"] == [] and {u["ticker"]: u["reason"] for u in two["unfilled"]} == {"A": "ABOVE_LIMIT", "B": "BELOW_STOP", "C": "NO_OPEN"}
    assert two["cash"] == pb.START_CASH["KR"] and two["state"]["positions"] == {}


def held(days, style="SWING", **levels):
    st = pb.new_state("KR")
    st["cash"] -= 1_000_000.0
    st["positions"]["A"] = {"ticker": "A", "name": "에이", "sector": None, "style": style, "qty": 100.0, "entry": 10_000.0, "entry_session": days[0], "stop": 9_600.0, "target": 10_600.0,
                            "atr": 200.0, "adv_value": 1e11, "cost": 1_000_150.0, "sessions": 1, "missing": 0, "last_close": 10_000.0, "last_bar": days[0], **levels}
    return st


def test_a_close_at_the_stop_or_target_exits_at_the_next_open_and_the_result_is_net_of_costs():
    days = calendar(3)
    for close, reason in ((9_550, "STOP"), (10_650, "TARGET")):
        bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_000, close), (days[2], close - 50, close)]}))
        mid = pb.step(held(days), days[1], "KR", bars, None)
        assert mid["decisions"] == [{"ticker": "A", "reason": reason}] and mid["exits"] == [] and mid["state"]["pending_exits"] == mid["decisions"]
        end = pb.step(mid["state"], days[2], "KR", bars, None)
        e = end["exits"][0]
        slip = op.slippage_bps("KR", 100 * (close - 50), 1e11, 200 / (close - 50))["total"]
        price = (close - 50) * (1 - slip / 1e4)
        assert e["reason"] == reason and e["exit"] == pytest.approx(price) and e["fee"] == pytest.approx(100 * price * 0.00215) and e["sessions"] == 2
        assert e["pnl"] == pytest.approx(100 * price - e["fee"] - 1_000_150.0) and e["net_pct"] == pytest.approx(e["pnl"] / 1_000_150.0 * 100)
        assert end["state"]["positions"] == {} and end["state"]["pending_exits"] == [] and end["state"]["closed"] == 1 and end["state"]["wins"] == (1 if reason == "TARGET" else 0)
        assert end["cash"] == pytest.approx(9_000_000.0 + 100 * price - e["fee"]) and end["state"]["realized"] == pytest.approx(e["pnl"])


def test_a_swing_position_is_closed_at_the_close_of_its_thirtieth_session_and_a_long_one_is_not():
    days = calendar(2)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_000, 10_100)]}))
    got = pb.step(held(days, sessions=pb.SWING_TIME_STOP - 1), days[1], "KR", bars, None)
    assert got["exits"][0]["reason"] == "TIME" and got["exits"][0]["ref_price"] == 10_100 and got["exits"][0]["sessions"] == 30 and got["state"]["positions"] == {}
    long = pb.step(held(days, "LONG", sessions=200, target=None), days[1], "KR", bars, None)
    assert long["exits"] == [] and long["decisions"] == [] and long["state"]["positions"]["A"]["sessions"] == 201


def test_a_long_position_leaves_when_its_long_score_falls_under_forty_and_not_on_a_swing_score():
    days = calendar(2)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_000, 10_100)]}))
    low = [snap("A", "LONG_TERM", score=39.9, session=days[1]), snap("A", "SWING", score=80.0, session=days[1])]
    assert pb.step(held(days, "LONG", target=None), days[1], "KR", bars, low)["decisions"] == [{"ticker": "A", "reason": "SCORE"}]
    ok = [snap("A", "LONG_TERM", score=40.0, session=days[1]), snap("A", "SWING", score=10.0, session=days[1])]
    assert pb.step(held(days, "LONG", target=None), days[1], "KR", bars, ok)["decisions"] == []
    assert pb.step(held(days, "LONG", target=None), days[1], "KR", bars, None)["decisions"] == []           # no score that day: nothing is assumed
    assert pb.step(held(days, "SWING"), days[1], "KR", bars, low)["decisions"] == []


def test_a_restated_price_file_moves_the_stored_levels_so_a_split_is_not_a_fall():
    days = calendar(2)
    bars = pb.Bars(loader_of({"A": [(days[0], 5_000, 5_000), (days[1], 5_000, 5_050)]}))          # the file now shows half prices for the day already recorded
    got = pb.step(held(days), days[1], "KR", bars, None)
    p = got["state"]["positions"]["A"]
    assert got["adjusted"] == [{"ticker": "A", "factor": 0.5}] and p["qty"] == 200.0 and p["stop"] == 4_800.0 and p["target"] == 5_300.0 and p["entry"] == 5_000.0
    assert got["decisions"] == [] and got["equity"] == pytest.approx(9_000_000.0 + 200 * 5_050)


def test_a_stock_without_prices_for_ten_sessions_is_closed_at_its_last_close():
    days = calendar(12)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000)]}))
    st = held(days)
    for n, day in enumerate(days[1:], 1):
        got = pb.step(st, day, "KR", bars, None)
        st = got["state"]
        if n < pb.HALT_SESSIONS:
            assert got["exits"] == [] and st["positions"]["A"]["missing"] == n and got["equity"] == pytest.approx(10_000_000.0)
        elif n == pb.HALT_SESSIONS:
            assert got["exits"][0]["reason"] == "NO_PRICE" and got["exits"][0]["ref_price"] == 10_000.0 and st["positions"] == {}


def test_a_session_reads_no_price_after_its_own_day():
    days = calendar(4)
    series = {"A": [(days[0], 10_000, 10_000), (days[1], 10_050, 9_500), (days[2], 9_400, 9_300), (days[3], 9_000, 9_100)]}
    full, cut = pb.Bars(loader_of(series)), pb.Bars(loader_of({"A": series["A"][:2]}))
    one = pb.step(None, days[0], "KR", full, filler(days[0]) + [snap("A", price=10_000.0, atr=200.0, session=days[0], adv=1e11)])
    assert pb.step(one["state"], days[1], "KR", full, None) == pb.step(one["state"], days[1], "KR", cut, None)


# ---------------------------------------------------------------------- the daily record
class FakeLedger:
    days = []
    extra = {}

    def __init__(self, base):
        pass

    def verify(self):
        return {"status": "OK"}

    def _live_rows(self):
        return [{"market": "KR", "session": d} for d in self.days] + [{"market": "US", "session": "2026-11-30"}]

    def _load(self, row):
        return filler(row["session"]) + self.extra.get(row["session"], [])


def test_the_record_writes_each_trading_day_once_in_order_and_each_day_builds_on_the_one_before(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "Ledger", FakeLedger)
    days = calendar(6)
    FakeLedger.days = days[:3]
    FakeLedger.extra = {days[0]: [snap("A", price=10_000.0, atr=200.0, session=days[0], adv=1e11)]}
    series = {"005930": [(d, 100, 100) for d in days[:3]], "A": [(days[0], 10_000, 10_000), (days[1], 10_050, 10_700), (days[2], 10_650, 10_600)]}
    at = datetime(2026, 11, 20, tzinfo=timezone.utc)
    got = pb.record(tmp_path, "KR", loader_of(series), info=lambda: {"A": {"name": "에이", "sector": "IT"}}, bench=lambda: [{"date": d, "close": 2_500.0 + n} for n, d in enumerate(days)], now=lambda: at)
    assert got["status"] == "OK" and got["written"] == days[:3] and got["sessions"] == 3
    docs = [kf._read_day(tmp_path / pb.FOLDERS["KR"], d) for d in days[:3]]
    assert [len(d["fills"]) for d in docs] == [0, 1, 0] and docs[1]["decisions"] == [{"ticker": "A", "reason": "TARGET"}] and docs[2]["exits"][0]["reason"] == "TARGET"
    assert docs[1]["state"]["positions"]["A"]["name"] == "에이" and docs[2]["state"]["positions"] == {} and docs[0]["benchmark_close"] == 2_500.0 and docs[2]["late"] is False and docs[0]["late"] is True
    assert pb.record(tmp_path, "KR", loader_of(series), now=lambda: at)["written"] == [] and kf.verify(tmp_path, pb.FOLDERS["KR"])["status"] == "OK"
    FakeLedger.days = days[:4]                                     # the ledger has a newer session than the price file
    assert pb.record(tmp_path, "KR", loader_of(series), now=lambda: at)["status"] == "WAITING"
    series["005930"] += [(d, 100, 100) for d in days[3:5]]         # the price file is ahead of the ledger: only scored days are written
    more = pb.record(tmp_path, "KR", loader_of(series), now=lambda: at)
    assert more["written"] == [days[3]] and more["sessions"] == 4
    view = pb.status(tmp_path, "KR")
    assert view["status"] == "REAL" and view["sessions"] == 4 and view["closed"] == 1 and view["wins"] == 1 and view["exit_counts"] == {"TARGET": 1} and view["integrity"] == "OK"
    assert view["equity"] == pytest.approx(view["cash"]) and view["return_pct"] == pytest.approx((view["equity"] / 10_000_000 - 1) * 100) and view["benchmark_return_pct"] == pytest.approx(2 / 2_500 * 100)      # the last run passed no index: that day has none
    assert view["recent"]["exits"][0]["ticker"] == "A" and view["fees"] > 0 and view["slippage"] > 0 and view["mean_net_pct"] == pytest.approx(view["recent"]["exits"][0]["net_pct"])
    assert pb.status(tmp_path, "US")["status"] == "NO_RECORD" and "주문을 보내지 않으며" in view["note"]


def test_the_book_never_spends_cash_it_does_not_have(tmp_path):
    days = calendar(2)
    names = [f"S{k}" for k in range(12)]
    plan = filler(days[0]) + [snap(t, "LONG_TERM", price=10_000.0, atr=100.0, session=days[0], adv=1e11, score=90 - n) for n, t in enumerate(names)]
    bars = pb.Bars(loader_of({t: [(days[0], 10_000, 10_000), (days[1], 10_049, 10_049)] for t in names}))
    one = pb.step(None, days[0], "KR", bars, plan)
    two = pb.step(one["state"], days[1], "KR", bars, None)
    assert two["cash"] >= 0 and len(two["fills"]) == len(one["plan"]["orders"]) == 4 and two["held_value"] <= 0.7 * two["equity"] * 1.01
    assert all(p["qty"] * p["last_close"] <= 0.2 * two["equity"] * 1.01 for p in two["state"]["positions"].values())


def test_the_two_books_are_backed_up_and_their_defaults_are_the_users_choices():
    from terminal import automation
    assert {"paper_book_kr", "paper_book_us"} <= set(automation.FORWARD_STORES) and sum("paper_book_" in g for g in automation.BACKUP_GLOBS) == 2
    assert pb.START_CASH == {"KR": 10_000_000.0, "US": 10_000.0} and pb.SWING_TIME_STOP == 30 and pb.LONG_EXIT_SCORE == 40.0
    assert pf.DEFAULT_SETTINGS["stop_atr_long"] == 5.0 and pf.DEFAULT_SETTINGS["target_long_kr_pct"] == 70.0 and op.ENTRY_READY == "ENTRY_NOW"


def test_an_order_under_one_percent_of_the_account_is_not_placed():
    nearly_full = account(positions={"X": {"style": "LONG", "value": 6_950_000.0, "sector": None}}, cash=3_050_000.0)
    got = op.build([op_c for op_c in [cand("A", "LONG", atr=100.0)]], nearly_full, "KR")             # 50,000 of sleeve room is five shares: 0.5% of the account
    assert got["orders"] == [] and got["skipped_counts"] == {"SLEEVE_FULL": 1} and got["assumptions"]["min_weight_pct"] == 1.0
    tiny = op.build([cand("A", atr=4_000.0)], account(equity=10_000_000.0), "KR")                     # 0.5% risk over an 8,000 stop distance: six shares, 0.6%
    assert tiny["orders"] == [] and tiny["skipped_counts"] == {"TOO_SMALL": 1}


def test_runs_that_overlap_write_each_day_once(tmp_path, monkeypatch):
    """Several daily runs started at the same moment: the lock lets one write, the others find the days already written."""
    import threading
    monkeypatch.setattr(pb, "Ledger", FakeLedger)
    days = calendar(4)
    FakeLedger.days = days
    FakeLedger.extra = {days[0]: [snap("A", price=10_000.0, atr=200.0, session=days[0], adv=1e11)]}
    series = {"005930": [(d, 100, 100) for d in days], "A": [(d, 10_000, 10_000) for d in days]}
    at = datetime(2026, 11, 20, tzinfo=timezone.utc)
    results, errors = [], []

    def run():
        try:
            results.append(pb.record(tmp_path, "KR", loader_of(series), now=lambda: at))
        except Exception as exc:          # a second writer must wait, never fail
            errors.append(exc)
    threads = [threading.Thread(target=run) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and sorted(len(r["written"]) for r in results) == [0, 0, 0, 0, 0, 4]
    index = kf.read_index(tmp_path, pb.FOLDERS["KR"])
    assert [r["session"] for r in index] == days and kf.verify(tmp_path, pb.FOLDERS["KR"])["status"] == "OK"
    assert pb.status(tmp_path, "KR")["fills"] == 1 and len(pb.status(tmp_path, "KR")["positions"]) == 1


def test_the_three_layers_are_wired_into_the_daily_steps_the_server_and_the_screen():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    assert app.count('_paper_book_record("KR")') == 1 and app.count('_paper_book_record("US")') == 1 and app.count('_regime_weights_record("KR")') == 1 and app.count('_regime_weights_record("US")') == 1
    assert app.index('res["method"] = kr_method.record') < app.index('_regime_weights_record("KR")') < app.index('_paper_book_record("KR")') < app.index("lookahead.run(PROJECT_ROOT)")
    assert all(f'"{a}"' in app for a in ("paper-book-record", "paper-book-status", "regime-weights-run", "regime-weights-record", "regime-weights-status", "lookahead-audit"))
    server = (root / "terminal" / "server.py").read_text(encoding="utf-8")
    assert all(f'"/api/qsf/{p}"' in server for p in ("paper-book", "order-plan", "regime-weights", "lookahead"))
    js = (root / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert all(w in js for w in ("주문 계획·가상 장부", "주문을 보내지 않습니다", "판정 전 참고", "미래 자료 차단 점검", "시장 국면에 따른 영역 가중치", "슬리피지 추정", "기준 미달 (조건"))
    assert 'exec: () => { qsfPlan(); qsfPaper(); }' in js and "qsfRegime(); qsfLookahead();" in js
    rules = (root / pb.RULES).read_text(encoding="utf-8")
    assert all(w in rules for w in ("PB-1", "1,000만 원", "1만 달러", "0.015%", "0.00206%", "30거래일", "5 ATR", "판정 전 참고", "주문을 보내지 않으며"))
    plan = (root / "reports" / "QSF_REGIME_WEIGHTS_PROTOCOL.md").read_text(encoding="utf-8")
    assert all(w in plan for w in ("REGIME_WEIGHTS_SUPPORTED", "NOT_SUPPORTED", "2.24", "걸어가기", "일회 예외", "2026-11-12 변경(첫 기록 전)"))


def test_the_real_account_plan_says_so_when_there_is_no_scan_and_never_writes(tmp_path):
    from terminal.services import Terminal
    from tests.test_terminal_1 import AFTER, fake_src
    t = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)
    before = sorted(p.name for p in tmp_path.rglob("*") if p.is_file())
    got = t.order_plan("US")
    assert got["status"] == "NO_SCAN" and "주문을 보내지 않습니다" in got["note"] and pb.status(tmp_path, "US")["status"] == "NO_RECORD"
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == before


def test_candidates_are_counted_by_style_and_buy_band():
    from terminal.qsf import order_plan
    cands = [{"style": "SWING", "score": 71.0}, {"style": "SWING", "score": 58.0}, {"style": "LONG", "score": 70.0}, {"style": "LONG", "score": 69.9}, {"style": "LONG", "score": 55.0}]
    assert order_plan.count_by(cands) == {"SWING": {"all": 2, "buy": 1}, "LONG": {"all": 3, "buy": 1}} and order_plan.count_by([]) == {}
