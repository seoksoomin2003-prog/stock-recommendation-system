"""Alert center: rule checking on final closes, the rule store, and the daily run storing rule state only after delivery."""
from datetime import datetime, timezone

import pytest

from terminal import alert_rules
from terminal.automation import Daily
from terminal.portfolio import market_of

TUE_NIGHT = datetime(2026, 11, 3, 23, 0, tzinfo=timezone.utc)


def rule(**kw):
    return alert_rules.validate(kw, market_of)


def ctx(**kw):
    base = {"bars": {}, "watched": {"US": [], "KR": []}, "bands": {}, "earnings": {}, "today": "2026-11-09"}
    base.update(kw)
    return base


def test_validate_rejects_bad_input():
    for bad in ({"type": "NOPE"}, {"type": "PRICE_ABOVE", "value": 10}, {"type": "PRICE_ABOVE", "ticker": "AAPL", "value": -1},
                {"type": "PRICE_ABOVE", "ticker": "AAPL", "value": True}, {"type": "MOVE", "value": 80}, {"type": "EARNINGS_SOON", "value": 2.5},
                {"type": "BAND_CHANGE", "strategy": "DAY"}):
        with pytest.raises(ValueError):
            rule(**bad)
    assert rule(type="PRICE_BELOW", ticker="005930", value=50000, market="US")["market"] == "KR"     # the ticker decides the market


def test_price_rule_fires_once_and_missing_price_is_not_a_cross():
    r = rule(type="PRICE_ABOVE", ticker="AAPL", value=200)
    alerts, state, notes = alert_rules.evaluate([r], ctx())
    assert alerts == [] and notes[0]["reason"] == "NO_PRICE" and "status" not in state[r["id"]]
    alerts, state, _ = alert_rules.evaluate([r], ctx(bars={"AAPL": {"date": "2026-11-06", "close": 201.0, "prev_close": 190.0}}))
    assert len(alerts) == 1 and "2026-11-06" in alerts[0]["text"] and state[r["id"]]["status"] == "TRIGGERED"
    triggered = {**r, "status": "TRIGGERED"}
    assert alert_rules.evaluate([triggered], ctx(bars={"AAPL": {"date": "2026-11-09", "close": 250.0}}))[0] == []


def test_move_rule_on_watched_names_once_per_bar():
    r = rule(type="MOVE", value=5, market="US")
    c = ctx(watched={"US": ["AAPL", "MSFT"]}, bars={"AAPL": {"date": "2026-11-06", "close": 94.0, "prev_close": 100.0},
                                                   "MSFT": {"date": "2026-11-06", "close": 102.0, "prev_close": 100.0}})
    alerts, state, _ = alert_rules.evaluate([r], c)
    assert [a["ticker"] for a in alerts] == ["AAPL"] and "-6.0%" in alerts[0]["text"]
    again, _, _ = alert_rules.evaluate([{**r, "seen": state[r["id"]]["seen"]}], c)
    assert again == []                                      # the same bar never alerts twice


def test_band_change_needs_a_baseline_and_reports_the_change():
    r = rule(type="BAND_CHANGE", ticker="AAPL", strategy="SWING")
    book = lambda band, label: {"US": {"session": "2026-11-06", "by_ticker": {"AAPL": {"SWING": {"band": band, "band_label": label, "score": 71.2}}}}}  # noqa: E731
    alerts, state, _ = alert_rules.evaluate([r], ctx(bands=book("HOLD_WATCH", "보유·관찰")))
    assert alerts == []                                     # the first look only records where it stands
    seen = state[r["id"]]["seen"]
    alerts, _, _ = alert_rules.evaluate([{**r, "seen": seen}], ctx(bands=book("BUY_CANDIDATE", "매수 후보")))
    assert len(alerts) == 1 and "보유·관찰 → 매수 후보" in alerts[0]["text"]
    _, _, notes = alert_rules.evaluate([{**r, "seen": seen}], ctx(bands={"US": {"by_ticker": {}}}))
    assert notes[0]["reason"] == "NOT_SCANNED"


def test_earnings_rule_unknown_is_reported_not_silent():
    r = rule(type="EARNINGS_SOON", ticker="AAPL", value=7)
    _, _, notes = alert_rules.evaluate([r], ctx())
    assert notes[0]["reason"] == "NO_EARNINGS_DATE"
    alerts, state, _ = alert_rules.evaluate([r], ctx(earnings={"AAPL": ["2026-10-01", "2026-11-13"]}))
    assert len(alerts) == 1 and "2026-11-13" in alerts[0]["text"] and "4일" in alerts[0]["text"]
    assert alert_rules.evaluate([r], ctx(earnings={"AAPL": ["2026-12-30"]}))[0] == []


def test_store_add_dedupes_remove_rearm_and_commit(tmp_path):
    s = alert_rules.Store(tmp_path)
    a = s.add(rule(type="PRICE_ABOVE", ticker="AAPL", value=200))
    assert s.add(rule(type="PRICE_ABOVE", ticker="AAPL", value=200))["id"] == a["id"] and len(s.rules()) == 1
    b = s.add(rule(type="MOVE", value=5))
    s.remove(b["id"])
    s.commit({a["id"]: {"seen": {}, "status": "TRIGGERED", "triggered_at": "2026-11-06"}, b["id"]: {"seen": {"X": 1}}},
             [{"text": "AAPL 발동", "code": "RULE_PRICE_ABOVE"}], "2026-11-09T07:10:00")
    assert [x["status"] for x in s.rules()] == ["TRIGGERED"] and s.log()[0]["text"] == "AAPL 발동"   # a removed rule stays removed
    assert s.rearm(a["id"]) and s.rules()[0]["status"] == "ACTIVE"


class Term:
    def __init__(self, base, alerts):
        self.alerts, self.store = alerts, alert_rules.Store(base / "data" / "terminal")

    def portfolio(self, market="US"):
        return {"integrity": {"status": "OK"}, "alerts": [], "holdings": []}

    def alert_check(self):
        rules = self.store.rules()
        return {"alerts": self.alerts, "state": {r["id"]: {"seen": {}, "status": "TRIGGERED", "triggered_at": "2026-11-03"} for r in rules}, "notes": []}


@pytest.mark.parametrize("tg,stored", [("SENT", True), ("FAILED", False)])
def test_daily_run_stores_rule_state_only_after_delivery(tmp_path, monkeypatch, tg, stored):
    for k in ("QPP_CAPITAL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)
    store = alert_rules.Store(tmp_path / "data" / "terminal")
    r = store.add(rule(type="PRICE_ABOVE", ticker="AAPL", value=200))
    fired = [{"level": "info", "code": "RULE_PRICE_ABOVE", "ticker": "AAPL", "rule_id": r["id"], "market": "US", "text": "AAPL: 종가 $201.00"}]
    sent = []
    d = Daily(tmp_path, now=lambda: TUE_NIGHT, runner=lambda n, a: 0, telegram=lambda t: sent.append(t) or {"status": tg},
              macos=lambda t, b: {"status": "SENT"}, terminal=Term(tmp_path, fired), backup_dir=tmp_path / "bk")
    d.run()
    assert "[내 알림 조건]" in sent[0] and "AAPL: 종가 $201.00" in sent[0]
    assert (store.rules()[0]["status"] == "TRIGGERED") is stored
    assert (len(store.log()) == 1) is stored


def test_daily_run_without_rules_has_no_rule_section(tmp_path, monkeypatch):
    for k in ("QPP_CAPITAL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(k, raising=False)
    sent = []
    d = Daily(tmp_path, now=lambda: TUE_NIGHT, runner=lambda n, a: 0, telegram=lambda t: sent.append(t) or {"status": "SENT"},
              macos=lambda t, b: {"status": "SENT"}, terminal=Term(tmp_path, []), backup_dir=tmp_path / "bk")
    d.run()
    assert "[내 알림 조건]" not in sent[0]
