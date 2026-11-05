"""Long-term and swing tagging: journal rules, per-style limits, target weight, exit readings and alerts."""
from datetime import date, datetime, timezone

import pytest

from terminal import portfolio as pf
from terminal.automation import exit_alerts
from terminal.services import Terminal, clean_ticker

NOW = datetime(2026, 11, 5, 21, 0, tzinfo=timezone.utc)
TODAY = date(2026, 11, 5)


def book(tmp_path, *entries):
    j = pf.Journal(tmp_path / "j.jsonl")
    for e in entries:
        j.append(pf.normalize(e, TODAY, clean_ticker), NOW)
    return j.read()[0]


CASH = dict(kind="DEPOSIT", date="2026-01-02", amount=100000)


def buy(t="AAPL", d="2026-01-05", qty=100, price=100, **kw):
    return dict(kind="BUY", date=d, ticker=t, qty=qty, price=price, **kw)


def test_style_is_stored_and_later_buys_inherit_it(tmp_path):
    st = pf.replay(book(tmp_path, CASH, buy(style="long"), buy(d="2026-01-06")))
    assert st["positions"]["AAPL"]["style"] == "LONG" and st["positions"]["AAPL"]["qty"] == 200


def test_one_ticker_cannot_hold_two_styles(tmp_path):
    j = pf.Journal(tmp_path / "j.jsonl")
    for e in (CASH, buy(style="LONG")):
        j.append(pf.normalize(e, TODAY, clean_ticker), NOW)
    with pytest.raises(pf.JournalError, match="구분 변경"):
        j.append(pf.normalize(buy(d="2026-01-06", style="SWING"), TODAY, clean_ticker), NOW)


def test_invalid_style_is_rejected():
    with pytest.raises(pf.JournalError):
        pf.normalize(buy(style="DAY"), TODAY, clean_ticker)
    with pytest.raises(pf.JournalError):
        pf.normalize(dict(kind="STYLE", date="2026-01-06", ticker="AAPL"), TODAY, clean_ticker)


def test_style_change_is_recorded_and_resets_the_swing_clock(tmp_path):
    recs = book(tmp_path, CASH, buy(style="LONG"), dict(kind="STYLE", date="2026-03-02", ticker="AAPL", style="SWING"))
    p = pf.replay(recs)["positions"]["AAPL"]
    assert p["style"] == "SWING" and p["style_since"] == "2026-03-02" and p["opened"] == "2026-01-05"
    assert [r["kind"] for r in recs][-1] == "STYLE"      # history stays append-only


def test_style_change_needs_a_holding(tmp_path):
    j = pf.Journal(tmp_path / "j.jsonl")
    j.append(pf.normalize(CASH, TODAY, clean_ticker), NOW)
    with pytest.raises(pf.JournalError, match="보유 중이 아니"):
        j.append(pf.normalize(dict(kind="STYLE", date="2026-01-06", ticker="AAPL", style="LONG"), TODAY, clean_ticker), NOW)


def test_position_can_change_style_after_a_full_sale(tmp_path):
    st = pf.replay(book(tmp_path, CASH, buy(style="LONG"), dict(kind="SELL", date="2026-02-02", ticker="AAPL", qty=100, price=110), buy(d="2026-03-02", style="SWING")))
    assert st["positions"]["AAPL"]["style"] == "SWING" and st["closed"][0]["style"] == "LONG"


def test_chosen_limits_per_style():
    st = dict(pf.DEFAULT_SETTINGS)
    assert (pf.limits_for("LONG", st)["risk_per_trade_pct"], pf.limits_for("LONG", st)["max_position_pct"]) == (2.0, 25.0)
    assert (pf.limits_for("SWING", st)["risk_per_trade_pct"], pf.limits_for("SWING", st)["max_position_pct"]) == (1.0, 10.0)
    assert (pf.limits_for(None, st)["risk_per_trade_pct"], pf.limits_for(None, st)["max_position_pct"]) == (1.0, 20.0)


def value(tmp_path, *entries, quotes):
    return pf.valuation(pf.replay(book(tmp_path, *entries)), quotes, {}, dict(pf.DEFAULT_SETTINGS))


def q(close):
    return {"close": close, "change_pct": 0.0}


def test_overweight_uses_the_limit_of_the_style(tmp_path):
    v = value(tmp_path, dict(kind="DEPOSIT", date="2026-01-02", amount=1000), buy(qty=2, style="SWING", stop=50), quotes={"AAPL": q(100)})
    over = [a for a in v["alerts"] if a["code"] == "OVERWEIGHT"]
    assert len(over) == 1 and "10%" in over[0]["text"]


def test_no_stop_warns_for_long_positions_too(tmp_path):
    v = value(tmp_path, CASH, buy(style="LONG"), quotes={"AAPL": q(100)})
    assert "NO_STOP" in {a["code"] for a in v["alerts"]}


def test_target_weight_ignores_cash_and_warns_outside_the_band(tmp_path):
    v = value(tmp_path, CASH, buy("AAPL", qty=100, style="LONG"), buy("MSFT", qty=100, style="SWING"), quotes={"AAPL": q(100), "MSFT": q(100)})
    st = v["summary"]["styles"]
    assert st["LONG"]["share_pct"] == 50 and st["LONG"]["weight_pct"] == 10
    assert "STYLE_DRIFT" in {a["code"] for a in v["alerts"]}


def test_target_weight_inside_the_band_is_quiet(tmp_path):
    v = value(tmp_path, CASH, buy("AAPL", qty=70, style="LONG"), buy("MSFT", qty=30, style="SWING"), quotes={"AAPL": q(100), "MSFT": q(100)})
    assert "STYLE_DRIFT" not in {a["code"] for a in v["alerts"]}


def test_missing_price_gives_no_share_rather_than_zero(tmp_path):
    v = value(tmp_path, CASH, buy("AAPL", style="LONG"), buy("MSFT", style="SWING"), quotes={"AAPL": q(100), "MSFT": {}})
    st = v["summary"]["styles"]
    assert st["LONG"]["share_pct"] is None and st["SWING"]["value"] is None
    assert "STYLE_DRIFT" not in {a["code"] for a in v["alerts"]}


def test_untagged_position_is_flagged(tmp_path):
    v = value(tmp_path, CASH, buy(), quotes={"AAPL": q(100)})
    assert "NO_STYLE" in {a["code"] for a in v["alerts"]} and v["summary"]["styles"]["untagged"] == ["AAPL"]


def sig(action, conditions, ticker="AAPL"):
    return {"status": "REAL", "ticker": ticker, "exit": {"action": action, "conditions": conditions, "reason": "이유"}}


def test_only_actions_reach_telegram():
    c = [{"code": "X", "action": "EXIT"}]
    got = {a["code"] for a in exit_alerts([sig("EXIT", c, "A"), sig("THESIS_INVALIDATED", [], "B"), sig("REDUCE", [], "C"), sig("PARTIAL_TAKE_PROFIT", [], "D"), sig("TIME_STOP_REVIEW", [], "E"),
                                          sig("HOLD_AND_REVIEW", [], "F"), sig("HOLD", [], "G"), {"status": "NO_STYLE", "ticker": "H"}])}
    assert got == {"QSF_EXIT", "QSF_THESIS_INVALIDATED", "QSF_REDUCE", "QSF_PARTIAL_TAKE_PROFIT", "QSF_TIME_STOP_REVIEW"}


def test_stop_breach_is_not_announced_twice():
    assert exit_alerts([sig("REDUCE", [{"code": "CONCENTRATION", "action": "REDUCE"}])]) == []
    assert exit_alerts([sig("EXIT", [{"code": "STOP_BREACH", "action": "EXIT"}])]) == []
    assert len(exit_alerts([sig("EXIT", [{"code": "STOP_BREACH", "action": "EXIT"}, {"code": "SEVERE_EVENT", "action": "EXIT"}])])) == 1
