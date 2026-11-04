"""TERMINAL-2 offline tests: append-only hash-chained journal, moving-average cost, validation (no oversell,
no negative cash, no future dates), VOID, valuation with missing prices (never 0), alerts, TWR vs flows,
position sizing limits, settings bounds, model-plan scaling (read-only), API round trip."""
import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest

from terminal import portfolio as pf, server
from terminal.services import Terminal, clean_ticker
from tests.test_terminal_1 import AFTER, bars, fake_src

NOW = AFTER                       # 2026-11-04 17:00 ET
TODAY = NOW.date()
_ORIG_CREATE_CONNECTION = socket.create_connection


def j(tmp_path):
    return pf.Journal(tmp_path / "journal.jsonl")


def add(journal, **raw):
    return journal.append(pf.normalize(raw, TODAY, clean_ticker), NOW)


def basic(tmp_path):
    jr = j(tmp_path)
    add(jr, kind="DEPOSIT", date="2026-01-02", amount=10000)
    add(jr, kind="BUY", date="2026-01-05", ticker="aapl", qty=10, price=100, fee=1, stop=90, target=130)
    add(jr, kind="BUY", date="2026-02-02", ticker="AAPL", qty=10, price=120, fee=1)
    add(jr, kind="SELL", date="2026-03-02", ticker="AAPL", qty=5, price=130, fee=1)
    return jr


# ----------------------------------------------------------------------------- journal
def test_moving_average_cost_and_realized(tmp_path):
    recs, integ = basic(tmp_path).read()
    assert integ == {"status": "OK", "records": 4}
    st = pf.replay(recs)
    p = st["positions"]["AAPL"]
    avg = (10 * 100 + 1 + 10 * 120 + 1) / 20
    assert p["qty"] == 15 and p["avg"] == pytest.approx(avg)
    assert st["realized"] == pytest.approx((130 - avg) * 5 - 1)
    assert st["cash"] == pytest.approx(10000 - 1001 - 1201 + 650 - 1)
    assert st["plans"]["AAPL"] == {"stop": 90.0, "target": 130.0, "date": "2026-01-05"}
    assert st["closed"][0]["hold_days"] == 56


def test_rejections_keep_file_unchanged(tmp_path):
    jr = basic(tmp_path)
    before = jr.path.read_bytes()
    cases = [dict(kind="SELL", date="2026-03-03", ticker="AAPL", qty=16, price=1),            # oversell
             dict(kind="BUY", date="2026-03-03", ticker="MSFT", qty=1000, price=100),          # no cash
             dict(kind="WITHDRAW", date="2026-01-03", amount=10001),                            # negative cash
             dict(kind="SELL", date="2026-01-04", ticker="AAPL", qty=1, price=1),              # backdated oversell
             dict(kind="PLAN", date="2026-03-03", ticker="MSFT", stop=10)]                      # not held
    for c in cases:
        with pytest.raises(pf.JournalError):
            add(jr, **c)
    for raw in (dict(kind="BUY", date="2026-11-05", ticker="X", qty=1, price=1),               # future (ET)
                dict(kind="BUY", date="2026-03-03", ticker="X", qty=0, price=1),
                dict(kind="BUY", date="2026-03-03", ticker="X", qty=1, price=-1),
                dict(kind="BUY", date="2026-03-03", ticker="X", qty=1, price=10, stop=11),
                dict(kind="BUY", date="2026-03-03", ticker="X", qty="nan", price=1),
                dict(kind="HACK", date="2026-03-03"), dict(kind="DEPOSIT", date="03/03/2026", amount=1),
                dict(kind="PLAN", date="2026-03-03", ticker="AAPL", stop=150, target=140)):
        with pytest.raises(pf.JournalError):
            pf.normalize(raw, TODAY, clean_ticker)
    assert jr.path.read_bytes() == before


def test_void_is_append_only(tmp_path):
    jr = basic(tmp_path)
    recs, _ = jr.read()
    sell = recs[-1]
    jr.append({"kind": "VOID", "ref": sell["id"]}, NOW)
    recs, integ = jr.read()
    assert len(recs) == 5 and integ["status"] == "OK"
    assert pf.replay(recs)["positions"]["AAPL"]["qty"] == 20 and pf.replay(recs)["realized"] == 0
    with pytest.raises(pf.JournalError):
        jr.append({"kind": "VOID", "ref": sell["id"]}, NOW)              # already voided
    with pytest.raises(pf.JournalError):
        jr.append({"kind": "VOID", "ref": "nope"}, NOW)
    # voiding the deposit would make the account invalid -> rejected
    with pytest.raises(pf.JournalError):
        jr.append({"kind": "VOID", "ref": recs[0]["id"]}, NOW)


def test_hash_chain_detects_tampering(tmp_path):
    jr = basic(tmp_path)
    lines = jr.path.read_text().splitlines()
    rec = json.loads(lines[1])
    rec["price"] = 1.0
    lines[1] = json.dumps(rec, sort_keys=True)
    jr.path.write_text("\n".join(lines) + "\n")
    recs, integ = jr.read()
    assert integ["status"] == "BROKEN" and integ["line"] == 2 and len(recs) == 1
    with pytest.raises(pf.JournalError):
        add(jr, kind="DEPOSIT", date="2026-03-03", amount=1)


def test_sell_all_clears_plan_and_dividend(tmp_path):
    jr = basic(tmp_path)
    add(jr, kind="DIVIDEND", date="2026-03-05", ticker="AAPL", amount=3.5)
    add(jr, kind="SELL", date="2026-03-06", ticker="AAPL", qty=15, price=110)
    st = pf.replay(jr.read()[0])
    assert "AAPL" not in st["positions"] and "AAPL" not in st["plans"] and st["dividends"] == 3.5


# ----------------------------------------------------------------------------- valuation & alerts
def test_valuation_missing_price_never_zero(tmp_path):
    jr = basic(tmp_path)
    add(jr, kind="BUY", date="2026-03-03", ticker="MSFT", qty=2, price=400)
    st = pf.replay(jr.read()[0])
    v = pf.valuation(st, {"AAPL": {"close": 140.0, "change_pct": 1.0, "date": "2026-11-04", "status": "REAL"}},
                     {"AAPL": "Technology"}, dict(pf.DEFAULT_SETTINGS))
    s = v["summary"]
    assert s["complete"] is False and s["equity"] is None and s["market_value"] is None
    assert s["missing_prices"] == ["MSFT"]
    msft = next(h for h in v["holdings"] if h["ticker"] == "MSFT")
    assert msft["value"] is None and msft["unrealized"] is None and msft["weight_pct"] is None
    assert any(a["code"] == "NO_PRICE" and a["ticker"] == "MSFT" for a in v["alerts"])


def test_valuation_alerts_and_risk(tmp_path):
    st = pf.replay(basic(tmp_path).read()[0])
    settings = dict(pf.DEFAULT_SETTINGS, max_position_pct=10.0, max_sector_pct=10.0)
    v = pf.valuation(st, {"AAPL": {"close": 92.0, "change_pct": -2.0, "date": "2026-11-04", "status": "REAL"}},
                     {"AAPL": "Technology"}, settings)
    s = v["summary"]
    assert s["complete"] and s["equity"] == pytest.approx(st["cash"] + 15 * 92)
    assert s["risk_to_stops"] == pytest.approx((92 - 90) * 15)
    codes = {a["code"] for a in v["alerts"]}
    assert {"NEAR_STOP", "OVERWEIGHT", "SECTOR_OVER"} <= codes and "STOP_HIT" not in codes
    v2 = pf.valuation(st, {"AAPL": {"close": 89.0, "change_pct": 0.0}}, {}, dict(pf.DEFAULT_SETTINGS))
    assert v2["alerts"][0]["code"] == "STOP_HIT" and v2["holdings"][0]["risk_to_stop"] == 0.0
    v3 = pf.valuation(st, {"AAPL": {"close": 131.0, "change_pct": 0.0}}, {}, dict(pf.DEFAULT_SETTINGS))
    assert "TARGET_HIT" in {a["code"] for a in v3["alerts"]}


def test_trade_stats_small_sample():
    s = pf.trade_stats([{"pnl": 10.0}, {"pnl": -5.0}, {"pnl": 20.0}])
    assert s["count"] == 3 and s["win_rate_pct"] == pytest.approx(200 / 3) and s["payoff"] == pytest.approx(3.0)
    assert s["small_sample"] is True
    assert pf.trade_stats([])["win_rate_pct"] is None


# ----------------------------------------------------------------------------- equity curve
def _bench(dates, closes):
    return [{"date": d, "close": c} for d, c in zip(dates, closes)]


def test_twr_removes_cash_flows(tmp_path):
    jr = j(tmp_path)
    add(jr, kind="DEPOSIT", date="2026-01-03", amount=1000)                # Saturday -> counts Monday
    add(jr, kind="BUY", date="2026-01-05", ticker="X", qty=10, price=100)
    add(jr, kind="DEPOSIT", date="2026-01-07", amount=5000)                # big deposit: must not look like gain
    days = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    hist = {"X": _bench(days, [100, 110, 110, 121])}
    c = pf.equity_curve(jr.read()[0], hist, _bench(days, [500, 505, 510, 515]))
    vals = [p["value"] for p in c["points"]]
    assert vals == [1000, 1100, 6100, 6210]
    assert c["twr_pct"] == pytest.approx((1.1 * 1.0 * (6210 / 6100) - 1) * 100)
    assert c["bench_pct"] == pytest.approx(3.0)


def test_equity_curve_missing_price_is_unknown(tmp_path):
    jr = j(tmp_path)
    add(jr, kind="DEPOSIT", date="2026-01-05", amount=1000)
    add(jr, kind="BUY", date="2026-01-05", ticker="X", qty=1, price=100)
    days = ["2026-01-05", "2026-01-06"]
    c = pf.equity_curve(jr.read()[0], {"X": []}, _bench(days, [1, 1]))
    assert all(p["value"] is None for p in c["points"]) and c["twr_pct"] is None


# ----------------------------------------------------------------------------- sizing & settings
def test_position_size_binding_limits():
    st = dict(pf.DEFAULT_SETTINGS)
    r = pf.position_size(100000, 100000, 100, 95, st)                     # risk 1000 / 5 = 200; weight 200
    assert r["shares"] == 200 and r["limits"] == {"RISK": 200, "WEIGHT": 200, "CASH": 1000}
    r = pf.position_size(100000, 100000, 100, 98, st)                     # risk 500 sh; weight 200 binds
    assert r["shares"] == 200 and r["binding"] == "WEIGHT"
    r = pf.position_size(100000, 5000, 100, 90, st)                       # cash binds
    assert r["shares"] == 50 and r["binding"] == "CASH"
    r = pf.position_size(100000, 100000, 100, 80, st)
    assert r["binding"] == "RISK" and r["shares"] == 50 and r["risk_amount"] == 1000
    for bad in ((100000, 1, 100, 100), (100000, 1, 100, 120), (0, 0, 100, 90), (None, 0, 100, 90)):
        with pytest.raises(pf.JournalError):
            pf.position_size(*bad, st)


def test_atr():
    b = [{"high": 11, "low": 9, "close": 10}] * 15
    assert pf.atr(b) == pytest.approx(2.0)
    assert pf.atr(b[:5]) is None


def test_settings_bounds_and_persistence(tmp_path):
    t = Terminal(tmp_path, src=fake_src(), now=lambda: NOW)
    assert t.settings() == pf.DEFAULT_SETTINGS
    assert t.settings_set({"risk_per_trade_pct": "0.5"})["risk_per_trade_pct"] == 0.5
    assert Terminal(tmp_path, src=fake_src(), now=lambda: NOW).settings()["risk_per_trade_pct"] == 0.5
    for bad in ({"risk_per_trade_pct": 50}, {"max_position_pct": "x"}, {"near_stop_pct": 0}):
        with pytest.raises(pf.JournalError):
            t.settings_set(bad)


# ----------------------------------------------------------------------------- services
def _seed(t):
    t.journal_add({"kind": "DEPOSIT", "date": "2026-01-02", "amount": "20000"})
    t.journal_add({"kind": "BUY", "date": "2026-10-01", "ticker": "AAPL", "qty": "10", "price": "150", "stop": "140"})


def test_portfolio_service(tmp_path):
    t = Terminal(tmp_path, src=fake_src(), now=lambda: NOW)
    _seed(t)
    d = t.portfolio()
    h = d["holdings"][0]
    assert h["ticker"] == "AAPL" and h["close"] == 159.0 and h["stop"] == 140.0
    assert d["summary"]["equity"] == pytest.approx(20000 - 1500 + 1590)
    assert d["fx"]["usdkrw"] == 159.0                    # fake source prices every symbol the same way
    assert d["journal"][0]["kind"] == "BUY" and d["integrity"]["status"] == "OK"
    e = t.equity()
    assert e["points"] and e["points"][-1]["value"] is not None


def test_sizing_service_suggests_2atr_stop(tmp_path):
    t = Terminal(tmp_path, src=fake_src(), now=lambda: NOW)
    _seed(t)
    d = t.sizing("AAPL")
    assert d["last_close"] == 159.0 and d["atr14"] == pytest.approx(2.0)
    assert d["suggested_stop"] == pytest.approx(155.0) and d["stop_source"].startswith("2 ATR")
    assert d["result"]["shares"] >= 0 and d["held_qty"] == 10
    assert t.sizing("", "100", "90")["result"]["entry"] == 100.0
    assert t.sizing()["result"] is None
    empty = Terminal(tmp_path / "e", src=fake_src(), now=lambda: NOW)
    with pytest.raises(pf.JournalError):
        empty.sizing("AAPL")
    d = empty.sizing("AAPL", "100", "95", "50000")
    assert d["equity_source"] == "입력값" and d["result"]["shares"] == 100 and d["result"]["binding"] == "RISK"


def test_model_plan_scales_to_equity_read_only(tmp_path):
    run = tmp_path / "runs" / "20261104T000000Z_market_scan_x"
    run.mkdir(parents=True)
    (run / "validation_result.json").write_text(json.dumps({
        "run_id": "R1", "mode": "market_scan", "validation_scope": "full", "executed_at": "2026-11-04T14:30:00+00:00",
        "recommendations": [{"recommendation_rank": 1, "ticker": "CL", "close": 95.0, "target_weight": 0.2,
                             "entry_1_weight": 0.08, "hard_stop": 92.0, "horizon_days": 30}]}))
    t = Terminal(tmp_path, src=fake_src(), now=lambda: NOW)
    t.journal_add({"kind": "DEPOSIT", "date": "2026-01-02", "amount": "10000"})
    before = (run / "validation_result.json").read_bytes()
    d = t.model_plan()
    assert (run / "validation_result.json").read_bytes() == before
    it = d["items"][0]
    assert d["status"] == "REAL" and d["equity"] == 10000
    assert it["target_shares"] == 21 and it["entry1_shares"] == 8 and it["hard_stop"] == 92.0 and it["held_qty"] is None
    later = Terminal(tmp_path, src=fake_src(), now=lambda: datetime(2026, 11, 20, tzinfo=timezone.utc))
    assert later.model_plan()["status"] == "STALE"


# ----------------------------------------------------------------------------- API
@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda a, *x, **k: _ORIG_CREATE_CONNECTION(a, *x, **k)
                        if a[0] == "127.0.0.1" else (_ for _ in ()).throw(OSError("blocked")))
    t = Terminal(tmp_path, src=fake_src(), now=lambda: NOW)
    httpd = server.serve(port=0, terminal=t, background=True)
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def _req(url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_journal_round_trip(live):
    assert _req(live + "/api/journal/add", {"kind": "DEPOSIT", "date": "2026-01-02", "amount": 5000})[0] == 200
    code, body = _req(live + "/api/journal/add", {"kind": "BUY", "date": "2026-01-05", "ticker": "AAPL",
                                                  "qty": 1000, "price": 100})
    assert code == 400 and "현금" in body["error"]
    code, body = _req(live + "/api/journal/add", {"kind": "BUY", "date": "2026-01-05", "ticker": "AAPL",
                                                  "qty": 10, "price": 100})
    assert code == 200
    code, p = _req(live + "/api/portfolio")
    assert code == 200 and p["holdings"][0]["qty"] == 10
    assert _req(live + "/api/journal/void", {"ref": body["entry"]["id"]})[0] == 200
    assert _req(live + "/api/portfolio")[1]["holdings"] == []
    for path in ("/api/portfolio/equity", "/api/settings", "/api/sizing?t=AAPL", "/api/model/plan"):
        assert _req(live + path)[0] == 200, path
    assert _req(live + "/api/settings", {"risk_per_trade_pct": 99})[0] == 400
    code, body = _req(live + "/api/journal/add", ["not", "an", "object"])
    assert code == 400 and body["error"] == "BAD_JSON"


def test_portfolio_js_has_no_external_resources():
    text = (server.STATIC / "portfolio.js").read_text(encoding="utf-8")
    assert "http://" not in text and "https://" not in text
    assert "portfolio.js" in (server.STATIC / "index.html").read_text(encoding="utf-8")
