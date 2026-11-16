"""The turnover rules beside the paper book (TO-1) and the reading that decides on them (reports/QSF_TURNOVER_RULES_PROTOCOL.md).  All offline."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from terminal.qsf import holding, kr_forward as kf, order_plan as op, paper_book as pb, turnover_book as tb
from tests.test_earnings_gap import daily
from tests.test_order_plan_paper_book import FakeLedger, account, calendar, cand, filler, held, loader_of, snap
from tests.test_qsf import run

ROOT = Path(__file__).resolve().parents[1]
RULES = dict(tb.RULES)
AT = datetime(2027, 12, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def no_switch(monkeypatch):
    monkeypatch.delenv(tb.ENV, raising=False)


# ---------------------------------------------------------------------- the step without the rules
def test_without_the_rules_the_record_has_not_one_key_more():
    days = calendar(2)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_000, 10_100)]}))
    doc = pb.step(held(days), days[1], "KR", bars, None)
    assert "rule_events" not in doc and "cooldown" not in doc["state"] and doc["rules"] == pb.VERSION == "PB-2"
    ruled = pb.step(held(days), days[1], "KR", bars, None, rules=RULES, version=tb.VERSION)
    assert ruled["rule_events"] == [] and ruled["state"]["cooldown"] == {} and ruled["rules"] == "TO-1"
    assert {k: v for k, v in ruled.items() if k not in ("rule_events", "rules", "state")} == {k: v for k, v in doc.items() if k not in ("rules", "state")}


# ---------------------------------------------------------------------- R1: the wait after a stop
def test_a_stock_sold_at_its_stop_gets_no_new_order_for_twenty_closes():
    days = calendar(25)
    series = {"A": [(days[0], 10_000, 10_000), (days[1], 10_000, 9_550)] + [(d, 9_500, 9_500) for d in days[2:]]}
    bars = pb.Bars(loader_of(series))
    again = lambda d: filler(d) + [snap("A", price=9_500.0, atr=200.0, session=d, adv=1e11)]       # noqa: E731  the stock reads as enterable every day after
    base = pb.step(pb.step(held(days), days[1], "KR", bars, None)["state"], days[2], "KR", bars, again(days[2]))
    assert base["exits"][0]["reason"] == "STOP" and [o["ticker"] for o in base["plan"]["orders"]] == ["A"]              # the paper book buys it straight back
    st = pb.step(held(days), days[1], "KR", bars, None, rules=RULES)["state"]
    blocked = []
    for k, d in enumerate(days[2:23], start=2):
        doc = pb.step(st, d, "KR", bars, again(d), rules=RULES)
        st = doc["state"]
        if k == 2:
            assert doc["exits"][0]["reason"] == "STOP" and doc["rule_events"] == [{"rule": "REENTRY_WAIT", "ticker": "A", "style": "SWING", "left": 20}]
            assert doc["plan"]["skipped_counts"] == {"REENTRY_WAIT": 1} and st["cooldown"] == {"A": 19}
        blocked.append(doc["plan"]["orders"] == [])
    assert blocked == [True] * 20 + [False] and st["cooldown"] == {}            # closes of the sale day and the 19 after it; the 21st plans it again


def test_only_a_stop_starts_the_wait():
    days = calendar(3)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_000, 10_650), (days[2], 10_600, 10_000)]}))
    st = pb.step(held(days), days[1], "KR", bars, None, rules=RULES)["state"]
    doc = pb.step(st, days[2], "KR", bars, filler(days[2]) + [snap("A", price=10_000.0, atr=200.0, session=days[2], adv=1e11)], rules=RULES)
    assert doc["exits"][0]["reason"] == "TARGET" and doc["state"]["cooldown"] == {} and [o["ticker"] for o in doc["plan"]["orders"]] == ["A"]


def test_the_plan_skips_a_blocked_ticker_and_says_why():
    got = op.build([cand("A", score=70), cand("B")], account(), "KR", blocked={"A": 3})
    assert [o["ticker"] for o in got["orders"]] == ["B"] and got["skipped"][0]["code"] == "REENTRY_WAIT" and got["skipped"][0]["reason"] == "손절 뒤 재진입 대기"
    assert [o["ticker"] for o in op.build([cand("A", score=70), cand("B")], account(), "KR")["orders"]] == ["A", "B"]


# ---------------------------------------------------------------------- R2: a swing past its time stop
def at_thirty(days, **over):
    return held(days, sessions=pb.SWING_TIME_STOP - 1, **over)


@pytest.mark.parametrize("snaps, kept", [
    ([dict(score=60.0)], "HOLD_EXTENDED"),
    ([dict(score=55.0)], "HOLD_EXTENDED"),
    ([dict(score=54.9)], None),
    ([dict(score=80.0, actionability="BLOCKED")], None),
    ([], "HOLD_NO_SCORE"),
])
def test_at_the_thirtieth_session_the_position_stays_while_its_swing_score_is_enough(snaps, kept):
    days = calendar(2)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_000, 10_100)]}))
    today = [snap("A", price=10_100.0, atr=200.0, session=days[1], entry="WAIT_FOR_PULLBACK", **s) for s in snaps]
    assert pb.step(at_thirty(days), days[1], "KR", bars, today)["exits"][0]["reason"] == "TIME"                # the paper book sells whatever the score
    doc = pb.step(at_thirty(days), days[1], "KR", bars, today, rules=RULES)
    if kept:
        assert doc["exits"] == [] and "A" in doc["state"]["positions"] and doc["rule_events"] == [{"rule": kept, "ticker": "A", "sessions": 30, "score": snaps[0]["score"] if snaps else None}]
    else:
        assert doc["exits"][0]["reason"] == "TIME" and doc["exits"][0]["sessions"] == 30 and doc["state"]["positions"] == {} and doc["rule_events"] == []


def test_a_long_term_score_is_not_the_swing_score_and_the_cap_sells_whatever_the_score():
    days = calendar(2)
    bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_000, 10_100)]}))
    long_only = [snap("A", "LONG_TERM", score=90.0, price=10_100.0, atr=200.0, session=days[1])]
    assert pb.step(at_thirty(days), days[1], "KR", bars, long_only, rules=RULES)["rule_events"][0]["rule"] == "HOLD_NO_SCORE"
    high = [snap("A", score=99.0, price=10_100.0, atr=200.0, session=days[1], entry="WAIT_FOR_PULLBACK")]
    capped = pb.step(held(days, sessions=RULES["hold_cap"] - 1), days[1], "KR", bars, high, rules=RULES)
    assert capped["exits"][0]["reason"] == "TIME" and capped["exits"][0]["sessions"] == 60 and capped["rule_events"] == []
    assert pb.step(held(days, sessions=RULES["hold_cap"] - 2), days[1], "KR", bars, high, rules=RULES)["exits"] == []


def test_the_stop_and_the_target_are_read_before_the_score():
    days = calendar(2)
    high = lambda px: [snap("A", score=99.0, price=px, atr=200.0, session=days[1], entry="WAIT_FOR_PULLBACK")]      # noqa: E731
    for close, reason in ((9_550, "STOP"), (10_650, "TARGET")):
        bars = pb.Bars(loader_of({"A": [(days[0], 10_000, 10_000), (days[1], 10_000, close)]}))
        doc = pb.step(at_thirty(days), days[1], "KR", bars, high(float(close)), rules=RULES)
        assert doc["decisions"] == [{"ticker": "A", "reason": reason}] and doc["rule_events"] == []


# ---------------------------------------------------------------------- the daily record: a fork of the paper book
def books(tmp_path, monkeypatch, n=9, read_at=5):
    """A paper book from 2026-11-12 and the comparison book from 2026-11-16, both through ``n`` sessions.  A is bought on the first
    plan, falls through its stop and reads as enterable ever after: the paper book buys it back, the comparison book waits."""
    monkeypatch.setattr(pb, "Ledger", FakeLedger)
    monkeypatch.setattr(tb, "READ_AT", read_at)
    days = calendar(n)
    FakeLedger.days = days
    FakeLedger.extra = {d: [snap("A", price=10_000.0 if k == 0 else 9_500.0, atr=200.0, session=d, adv=1e11)] for k, d in enumerate(days)}
    series = {"005930": [(d, 100, 100) for d in days],
              "A": [(days[0], 10_000, 10_000), (days[1], 10_000, 10_000), (days[2], 10_000, 9_550)] + [(d, 9_500, 9_500 + 10 * k) for k, d in enumerate(days[3:])]}
    load = loader_of(series)
    assert pb.record(tmp_path, "KR", load, now=lambda: AT)["status"] == "OK"         # a second call with a longer calendar adds the new days
    return days, load


def test_the_comparison_book_starts_from_the_paper_books_state_and_parts_only_where_a_rule_acts(tmp_path, monkeypatch):
    days, load = books(tmp_path, monkeypatch)
    assert days[2] == tb.FIRST
    got = tb.record(tmp_path, "KR", load, now=lambda: AT)
    assert got["status"] == "OK" and got["written"] == days[2:] and tb.record(tmp_path, "KR", load, now=lambda: AT)["written"] == []
    assert kf.verify(tmp_path, tb.FOLDERS["KR"])["status"] == "OK" and kf.verify(tmp_path, pb.FOLDERS["KR"])["status"] == "OK"
    b = {d: kf._read_day(tmp_path / pb.FOLDERS["KR"], d) for d in days}
    t = {d: kf._read_day(tmp_path / tb.FOLDERS["KR"], d) for d in days[2:]}
    same = lambda x: {k: v for k, v in x.items() if k not in ("rules", "rule_events", "state", "recorded_at", "late", "before_next_open")}      # noqa: E731
    assert b[days[1]]["fills"][0]["ticker"] == "A" and same(t[days[2]]) == same(b[days[2]]) and t[days[2]]["rules"] == "TO-1" and b[days[2]]["rules"] == "PB-2"
    assert t[days[2]]["decisions"] == [{"ticker": "A", "reason": "STOP"}] and t[days[3]]["exits"][0]["reason"] == "STOP" and b[days[3]]["exits"][0]["reason"] == "STOP"
    assert [o["ticker"] for o in b[days[3]]["plan"]["orders"]] == ["A"] and t[days[3]]["plan"]["orders"] == [] and t[days[3]]["rule_events"][0]["rule"] == "REENTRY_WAIT"
    assert b[days[4]]["fills"][0]["ticker"] == "A" and t[days[4]]["fills"] == [] and t[days[-1]]["state"]["positions"] == {} and "A" in b[days[-1]]["state"]["positions"]


# ---------------------------------------------------------------------- figures and the decision
def doc(equity, cash, fees=0.0, slippage=0.0, fills=(), exits=(), events=()):
    return {"equity": equity, "cash": cash, "state": {"fees": fees, "slippage": slippage}, "fills": list(fills), "exits": list(exits), "rule_events": list(events)}


def test_the_figures_count_what_was_traded_paid_and_bought_back():
    docs = [doc(1_010.0, 500.0, fees=1.0, slippage=1.0, fills=[{"ticker": "A", "qty": 5, "price": 100.0}]),
            doc(990.0, 990.0, fees=3.0, slippage=2.0, exits=[{"ticker": "A", "qty": 5, "exit": 98.0, "reason": "STOP"}]),
            doc(1_000.0, 480.0, fees=4.0, slippage=3.0, fills=[{"ticker": "A", "qty": 5, "price": 104.0}, {"ticker": "B", "qty": 1, "price": 10.0}])]
    f = tb.figures(docs, {"equity": 1_000.0, "fees": 1.0, "slippage": 0.0})
    assert f["sessions"] == 3 and f["return_pct"] == pytest.approx(0.0) and f["cost"] == pytest.approx(6.0) and f["cost_pct"] == pytest.approx(6.0 / 1_000.0 * 100)
    assert f["traded_pct"] == pytest.approx((500 + 490 + 520 + 10) / 1_000.0 * 100) and f["fills"] == 3 and f["exits"] == 1 and f["exit_counts"] == {"STOP": 1} and f["rebuys_after_stop"] == 1
    assert f["max_drawdown_pct"] == pytest.approx((990 / 1_010 - 1) * 100) and len(f["log_returns"]) == 3 and sum(f["log_returns"]) == pytest.approx(0.0)
    assert tb.rule_counts(docs[:2] + [doc(1.0, 1.0, events=[{"rule": "REENTRY_WAIT"}, {"rule": "HOLD_EXTENDED"}, {"rule": "REENTRY_WAIT"}])]) == {"REENTRY_WAIT": 2, "HOLD_EXTENDED": 1, "HOLD_NO_SCORE": 0, "STOPS": 1}


@pytest.mark.parametrize("cost_rules, mean, t, decision, evidence, words", [
    (0.5, 0.0002, 0.9, "ADOPT", "NOT_DISTINCT", "약한 결정"),
    (0.5, 0.0002, 2.4, "ADOPT", "DISTINCT", "규칙을 적용합니다"),
    (0.5, 0.0, None, "ADOPT", "NOT_DISTINCT", "계산할 수 없음"),
    (0.5, -0.0001, -0.4, "KEEP", "NOT_DISTINCT", "기존 규칙을 유지합니다"),
    (0.5, -0.0004, -2.6, "KEEP", "DISTINCT", "0보다 작습니다"),
    (1.0, 0.0003, 2.5, "KEEP", "DISTINCT", "낮지 않습니다"),
    (1.2, 0.0003, 0.5, "KEEP", "NOT_DISTINCT", "낮지 않습니다"),
])
def test_the_decision_needs_a_lower_cost_and_a_mean_difference_not_under_zero(cost_rules, mean, t, decision, evidence, words):
    fig = lambda c: {"cost_pct": c, "return_pct": 3.0, "max_drawdown_pct": -5.0}          # noqa: E731
    got = tb.decide(fig(1.0), fig(cost_rules), mean, t)
    assert got["decision"] == decision and got["evidence"] == evidence and words in " ".join(got["why"]) and len(got["why"]) == 4
    assert "1.00%" in got["why"][0] and f"{cost_rules:.2f}%" in got["why"][0] and f"{mean * 1e4:+.2f}bp" in got["why"][1]        # every reason carries its numbers


def test_two_books_that_never_parted_keep_the_rules_as_they_are():
    docs = [doc(1_000.0 + k, 500.0, fees=1.0 + k, slippage=0.0) for k in range(6)]
    got = tb.measure(docs, docs, {"equity": 1_000.0, "state": {"fees": 0.0, "slippage": 0.0}})
    assert got["difference"] == {"mean_daily": 0.0, "t": None, "days": 6} and got["decision"] == "KEEP" and got["cheaper"] is False


# ---------------------------------------------------------------------- the single reading, made by the program itself
def test_the_reading_waits_for_its_day_is_made_once_and_ends_the_record(tmp_path, monkeypatch):
    days, load = books(tmp_path, monkeypatch, n=6)
    tb.record(tmp_path, "KR", load, now=lambda: AT)
    with pytest.raises(tb.NotDue):
        tb.evaluate_once(tmp_path, "KR")
    assert tb.read_when_due(tmp_path, "KR") is None and not (tmp_path / tb.REPORTS["KR"]).exists() and tb.status(tmp_path, "KR")["left"] == 1
    days, load = books(tmp_path, monkeypatch, n=7)
    tb.record(tmp_path, "KR", load, now=lambda: AT)
    seen = tb.status(tmp_path, "KR")
    assert seen["status"] == "RECORDING" and seen["records"] == 5 and seen["left"] == 0 and seen["rule_counts"]["STOPS"] == 1 and seen["rule_counts"]["REENTRY_WAIT"] == 4
    assert "decision" not in seen and not {"equity", "return_pct", "cost", "rules_book"} & set(json.dumps({k: v for k, v in seen.items() if k != "paper_book"}).replace('"', " ").split())
    assert seen["paper_book"]["rebuys_after_stop"] == 1 and seen["paper_book"]["sessions"] == 7 and "log_returns" not in seen["paper_book"]
    rep = tb.read_when_due(tmp_path, "KR", now=lambda: AT)
    assert rep["status"] == "REAL" and rep["first"] == days[2] and rep["last"] == days[6] and rep["seed_session"] == days[1] and rep["difference"]["days"] == 5
    assert rep["paper_book"]["rebuys_after_stop"] == 1 and rep["rules_book"]["rebuys_after_stop"] == 0 and rep["rules_book"]["fills"] == 0 and rep["paper_book"]["fills"] == 1
    assert rep["cheaper"] is True and rep["rules_book"]["cost_pct"] < rep["paper_book"]["cost_pct"]
    assert rep["decision"] == ("ADOPT" if rep["difference"]["mean_daily"] >= 0 else "KEEP") and rep["consequence"] and len(rep["why"]) == 4
    assert json.loads((tmp_path / tb.REPORTS["KR"]).read_text(encoding="utf-8")) == rep and tb.read_when_due(tmp_path, "KR") == rep
    with pytest.raises(RuntimeError, match="이미 읽었습니다"):
        tb.evaluate_once(tmp_path, "KR")
    assert tb.record(tmp_path, "KR", load, now=lambda: AT) == {"status": "DONE", "market": "KR", "written": []}
    done = tb.status(tmp_path, "KR")
    assert done["status"] == "DECIDED" and done["decision"]["decision"] == rep["decision"] and done["decision"]["why"] == rep["why"] and done["active"] is (rep["decision"] == "ADOPT")


def test_only_the_first_240_sessions_are_read_and_a_missing_paper_book_day_waits(tmp_path, monkeypatch):
    days, load = books(tmp_path, monkeypatch, n=9, read_at=4)
    tb.record(tmp_path, "KR", load, now=lambda: AT)
    rep = tb.evaluate_once(tmp_path, "KR", now=lambda: AT)
    assert rep["last"] == days[5] and rep["difference"]["days"] == 4
    (tmp_path / tb.REPORTS["KR"]).unlink()
    monkeypatch.setattr(kf, "read_index", lambda base, folder=None, real=kf.read_index: [r for r in real(base, folder) if folder != pb.FOLDERS["KR"] or r["session"] != days[4]])
    with pytest.raises(tb.NotDue, match="PAPER_BOOK_BEHIND"):
        tb.evaluate_once(tmp_path, "KR")


def test_a_broken_record_is_not_read_and_nothing_is_written(tmp_path, monkeypatch):
    days, load = books(tmp_path, monkeypatch, n=7)
    tb.record(tmp_path, "KR", load, now=lambda: AT)
    monkeypatch.setattr(kf, "verify", lambda base, store=None: {"status": "BROKEN"})
    got = tb.read_when_due(tmp_path, "KR")
    assert got["status"] == "NO_READING" and "검증에 실패" in got["reason"] and not (tmp_path / tb.REPORTS["KR"]).exists()
    assert "읽지 못했습니다" in tb.text(got) and "한국" in tb.text(got)


def test_the_daily_job_reads_tells_once_and_sends_an_undelivered_notice_again(tmp_path, monkeypatch):
    days, load = books(tmp_path, monkeypatch, n=6)
    tb.record(tmp_path, "KR", load, now=lambda: AT)
    d, sent, shown = daily(tmp_path, AT, tg="FAILED")
    st = {}
    assert d._turnover_reading(st) == {} and not sent                                    # not due: nothing is read, nothing is said
    days, load = books(tmp_path, monkeypatch, n=7)
    tb.record(tmp_path, "KR", load, now=lambda: AT)
    got = d._turnover_reading(st)
    assert got["KR"]["delivered"] is False and got["KR"]["decision"] in ("ADOPT", "KEEP") and len(sent) == 1 and (tmp_path / tb.REPORTS["KR"]).exists() and "US" not in got
    ok, sent2, _ = daily(tmp_path, AT)
    again = ok._turnover_reading(st)
    assert again["KR"]["delivered"] is True and len(sent2) == 1 and "[회전율 규칙 판정 · 한국] 결정:" in sent2[0] and ".env" in sent2[0] and "bp" in sent2[0]
    assert ok._turnover_reading(st)["KR"]["delivered"] is True and len(sent2) == 1       # never twice
    quiet, _, shown = daily(tmp_path, AT, tg="NOT_CONFIGURED")
    fresh = quiet._turnover_reading({})
    assert shown and shown[0][0] == "회전율 규칙 판정" and fresh["KR"]["delivered"] is True         # no Telegram: the Mac notice stands in, as for the other one-time notices


def test_a_record_that_cannot_be_read_is_told_once(tmp_path, monkeypatch):
    days, load = books(tmp_path, monkeypatch, n=7)
    tb.record(tmp_path, "KR", load, now=lambda: AT)
    monkeypatch.setattr(kf, "verify", lambda base, store=None: {"status": "BROKEN"})
    d, sent, _ = daily(tmp_path, AT)
    st = {}
    assert d._turnover_reading(st)["KR"] == {"decision": None, "at": AT.isoformat(), "warned": True, "delivered": False} and len(sent) == 1
    assert d._turnover_reading(st)["KR"]["warned"] is True and len(sent) == 1


# ---------------------------------------------------------------------- what an ADOPT changes, and the user's switch
def decided(tmp_path, decision):
    p = tmp_path / tb.REPORTS["US"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"status": "REAL", "market": "US", "decision": decision}), encoding="utf-8")


def test_the_rules_are_in_force_after_an_adopt_and_the_env_switch_overrules_the_reading(tmp_path, monkeypatch):
    assert tb.active_rules(tmp_path, "US") is None and tb.mode() == "auto"
    decided(tmp_path, "KEEP")
    assert tb.active_rules(tmp_path, "US") is None
    decided(tmp_path, "ADOPT")
    assert tb.active_rules(tmp_path, "US") == tb.RULES and tb.active_rules(tmp_path, "KR") is None                 # each market by its own reading
    monkeypatch.setenv(tb.ENV, "off")
    assert tb.active_rules(tmp_path, "US") is None
    monkeypatch.setenv(tb.ENV, " ON ")
    assert tb.active_rules(tmp_path, "KR") == tb.RULES and tb.status(tmp_path, "KR")["mode"] == "on"
    monkeypatch.setenv(tb.ENV, "sometimes")
    assert tb.mode() == "auto"                                                                                      # an unknown value changes nothing
    (tmp_path / tb.REPORTS["US"]).write_text("{cut", encoding="utf-8")
    assert tb.active_rules(tmp_path, "US") is None


def test_after_an_adopt_the_paper_book_writes_pb3_under_the_rules(tmp_path, monkeypatch):
    days, load = books(tmp_path, monkeypatch, n=3)
    FakeLedger.days = calendar(5)
    series = {"005930": [(d, 100, 100) for d in FakeLedger.days], "A": [(FakeLedger.days[0], 10_000, 10_000), (FakeLedger.days[1], 10_000, 10_000), (FakeLedger.days[2], 10_000, 9_550)] + [(d, 9_500, 9_500) for d in FakeLedger.days[3:]]}
    FakeLedger.extra = {d: [snap("A", price=9_500.0, atr=200.0, session=d, adv=1e11)] for d in FakeLedger.days[3:]}
    got = pb.record(tmp_path, "KR", loader_of(series), now=lambda: AT, rules=dict(tb.RULES), version=tb.ADOPTED_VERSION)
    assert got["written"] == FakeLedger.days[3:]
    docs = [kf._read_day(tmp_path / pb.FOLDERS["KR"], d) for d in FakeLedger.days]
    assert [d["rules"] for d in docs] == ["PB-2", "PB-2", "PB-2", "PB-3", "PB-3"] and "rule_events" not in docs[2] and docs[3]["exits"][0]["reason"] == "STOP"
    assert docs[3]["plan"]["orders"] == [] and docs[3]["rule_events"][0]["rule"] == "REENTRY_WAIT" and docs[4]["fills"] == [] and pb.status(tmp_path, "KR")["version"] == "PB-3"
    assert kf.verify(tmp_path, pb.FOLDERS["KR"])["status"] == "OK"


def test_the_real_plan_reads_a_recent_loss_sale_as_the_stock_that_waits():
    step = holding.stepper("US")
    closed = [{"ticker": "AAA", "date": "2026-11-02", "pnl": -50.0}, {"ticker": "BBB", "date": "2026-11-02", "pnl": 10.0}, {"ticker": "CCC", "date": "2026-09-01", "pnl": -5.0},
              {"ticker": "AAA", "date": "2026-10-01", "pnl": -1.0}, {"ticker": "DDD", "date": "2026-11-13", "pnl": None}]
    assert tb.loss_sales(closed, "US", "2026-11-13", step, 20) == {"AAA": "2026-11-02"}
    last_blocked = holding.add_sessions(date(2026, 11, 2), 19, step).isoformat()
    assert "AAA" in tb.loss_sales(closed[:1], "US", last_blocked, step, 20)
    assert tb.loss_sales(closed[:1], "US", holding.add_sessions(date(2026, 11, 2), 20, step).isoformat(), step, 20) == {}


def test_the_holding_reading_keeps_a_swing_past_thirty_sessions_only_under_the_rules():
    r, c = run()
    assert r["actionability"] == "ACTIONABLE" and r["score"] is not None
    pos = {"opened": "2026-09-15"}                                  # between 30 and 60 sessions before the day read
    today = date(2026, 11, 5)
    assert holding.evaluate_exit(r, c, pos, today)["action"] == "TIME_STOP_REVIEW"
    assert holding.evaluate_exit(r, c, {**pos, "hold_rules": None}, today)["action"] == "TIME_STOP_REVIEW"
    kept = holding.evaluate_exit(r, c, {**pos, "hold_rules": {**tb.RULES, "hold_score": r["score"] - 1}}, today)
    assert kept["action"] == "HOLD" and "계속 보유로 읽습니다" in kept["reason"] and "회전율 규칙" in kept["reason"] and [h["code"] for h in kept["conditions"]] == ["TIME_STOP_EXTENDED"]
    assert holding.evaluate_exit(r, c, {**pos, "hold_rules": {**tb.RULES, "hold_score": r["score"] + 1}}, today)["action"] == "TIME_STOP_REVIEW"
    assert holding.evaluate_exit(r, c, {"opened": "2026-07-01", "hold_rules": {**tb.RULES, "hold_score": 0.0}}, today)["action"] == "TIME_STOP_REVIEW"      # past the cap
    stopped = holding.evaluate_exit(r, c, {**pos, "stop": r["price"] * 1.01, "hold_rules": {**tb.RULES, "hold_score": 0.0}}, today)
    assert stopped["action"] == "EXIT"                              # a stop is never softened by the rule


# ---------------------------------------------------------------------- wiring
def test_the_comparison_is_recorded_backed_up_shown_and_read_without_a_person():
    from terminal import automation
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert app.count("_turnover_book_record(market, q, info, bench)") == 1 and app.index("res = paper_book.record(") < app.index('res["turnover_book"] = _turnover_book_record(')
    assert "rank_book.paper_rules(PROJECT_ROOT, market)" in app and '"turnover-book-status": _qsf_turnover_book' in app
    assert {"turnover_book_kr", "turnover_book_us"} <= set(automation.FORWARD_STORES)
    assert sum("turnover_book_" in g for g in automation.BACKUP_GLOBS) == 2 and "reports/qsf/QSF_TURNOVER_*.json" in automation.BACKUP_GLOBS
    job = (ROOT / "terminal" / "automation.py").read_text(encoding="utf-8")
    assert job.index("self._earnings_gap(st, steps)\n") < job.index("self._turnover_reading(st)\n") < job.index("alerts = self._alerts()")
    assert '("GET", "/api/qsf/turnover-book")' in (ROOT / "terminal" / "server.py").read_text(encoding="utf-8")
    js = (ROOT / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "/api/qsf/turnover-book?market=" in js and "회전율 규칙 비교" in js and "QSF_TURNOVER_RULES" in js
    plan = (ROOT / tb.PROTOCOL).read_text(encoding="utf-8")
    for words in ("20거래일", "55 이상", "60거래일", "240개", "Newey-West t(지연 20)", "`ADOPT`", "`KEEP`", "PB-3", "QSF_TURNOVER_RULES", "최근 20거래일 안에 손실로 판 종목"):
        assert words in plan
    assert tb.RULES == {"reentry_wait": 20, "hold_score": 55.0, "hold_cap": 60} and tb.READ_AT == 240 and tb.LAG == 20 and tb.MIN_T == 2.0 and tb.FIRST == "2026-11-16"
