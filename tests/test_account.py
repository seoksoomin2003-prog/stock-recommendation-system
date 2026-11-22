"""The unified account (US stocks, Korean stocks, coins kept in won) and the 'already held' entry (user request and decisions 2026-11-23)."""
from datetime import date

import numpy as np
import pytest

from terminal import coin_source, phone_view, portfolio as pf, server
from tests.test_kr_terminal import NOW, add, term  # noqa: F401  (term: fixture)

TODAY = date(2026, 11, 20)


def clean(t):
    return str(t).strip().upper()


def bars_of(*closes):
    """Four-hour bars [open time, open, high, low, close, volume] ending now."""
    step = 4 * 3600 * 1000
    return np.array([[1_795_000_000_000 + k * step, c, c, c, c, 1.0] for k, c in enumerate(closes)], dtype=float)


@pytest.fixture
def coins(monkeypatch):
    def use(prices, error=None):
        doc = {"arrays": {"bars": {s: bars_of(*v) for s, v in prices.items()}}, **({"error": error} if error else {})}
        monkeypatch.setattr(coin_source, "load", lambda base, *a, **k: doc)
    use({"BTCUSDT": [90_000.0] * 6 + [100_000.0], "1000SHIBUSDT": [0.02] * 7})
    return use


# ---------------------------------------------------------------------- the 'already held' entry
def test_an_already_held_stock_enters_with_its_own_date_and_price_and_no_deposit():
    e = pf.normalize({"kind": "HOLD", "date": "2025-03-04", "ticker": "aapl", "qty": "10", "price": "150", "style": "LONG", "stop": "300", "target": "400"}, TODAY, clean)
    assert e == {"kind": "HOLD", "date": "2025-03-04", "ticker": "AAPL", "qty": 10.0, "price": 150.0, "fee": 0.0, "style": "LONG", "stop": 300.0, "target": 400.0}      # the stop may stand above the old price
    state = pf.replay([{**e, "id": "a", "seq": 1}])
    p = state["positions"]["AAPL"]
    assert state["cash"] == 0.0 and state["deposits"] == 1500.0 and state["flows"] == [("2025-03-04", 1500.0)]              # its cost is money put in, not a profit
    assert (p["qty"], p["cost"], p["avg"], p["opened"], p["style"]) == (10.0, 1500.0, 150.0, "2025-03-04", "LONG") and state["plans"]["AAPL"] == {"stop": 300.0, "target": 400.0, "date": "2025-03-04"}
    sold = pf.replay([{**e, "id": "a", "seq": 1}, {"kind": "SELL", "date": "2026-11-02", "ticker": "AAPL", "qty": 4.0, "price": 200.0, "fee": 1.0, "id": "b", "seq": 2}])
    assert sold["cash"] == 799.0 and sold["realized"] == 199.0 and sold["positions"]["AAPL"]["qty"] == 6.0
    with pytest.raises(pf.JournalError, match="목표가는 손절가보다"):
        pf.normalize({"kind": "HOLD", "date": "2025-03-04", "ticker": "AAPL", "qty": 1, "price": 150, "stop": 300, "target": 290}, TODAY, clean)
    with pytest.raises(pf.JournalError, match="산 가격"):
        pf.normalize({"kind": "HOLD", "date": "2025-03-04", "ticker": "AAPL", "qty": 1}, TODAY, clean)
    with pytest.raises(pf.JournalError, match="현금이 부족"):                                                                 # a purchase still needs its cash
        pf.replay([{"kind": "BUY", "date": "2026-11-02", "ticker": "AAPL", "qty": 1.0, "price": 150.0, "fee": 0.0, "id": "c", "seq": 1}])
    assert "HOLD" in pf.KINDS and pf.POSITION_KINDS == ("BUY", "HOLD")


def test_a_coin_is_a_coin_because_the_entry_says_so():
    coin = pf.normalize({"kind": "HOLD", "date": "2026-01-05", "ticker": "sol", "qty": "2.5", "price": "250000", "market": "COIN", "style": "LONG"}, TODAY, clean)
    stock = pf.normalize({"kind": "HOLD", "date": "2026-01-05", "ticker": "SOL", "qty": "2", "price": "5", "style": "LONG"}, TODAY, clean)
    korean = pf.normalize({"kind": "HOLD", "date": "2026-01-05", "ticker": "005930", "qty": "3", "price": "60000", "style": "LONG", "market": "US"}, TODAY, clean)
    assert coin["market"] == "COIN" and coin["ticker"] == "SOL" and coin["qty"] == 2.5 and "market" not in stock and korean["market"] == "KR"      # a stock's market is read from its code
    assert pf.MARKETS == ("US", "KR", "COIN") and pf.STOCK_MARKETS == ("US", "KR")
    assert pf.coin_code(" btc ") == "BTC" and pf.coin_code("1000SHIB") == "1000SHIB"
    for bad in ("", "B", "BTC-USD", "비트코인"):
        with pytest.raises(pf.JournalError):
            pf.normalize({"kind": "HOLD", "date": "2026-01-05", "ticker": bad, "qty": 1, "price": 1, "market": "COIN"}, TODAY, clean)
    cash = pf.normalize({"kind": "DEPOSIT", "date": "2026-01-05", "amount": "500000", "market": "COIN"}, TODAY, clean)
    assert cash["market"] == "COIN" and cash["amount"] == 500000.0


# ---------------------------------------------------------------------- three accounts on one page
def test_the_three_accounts_keep_their_own_books_and_add_up_in_won(term, coins):  # noqa: F811
    t = term({"KRW=X": 1400.0, "005930.KS": 60000.0, "AAPL": 200.0})
    add(t, kind="HOLD", ticker="AAPL", qty=10, price=150, style="LONG", date="2025-03-04", stop=180)          # no deposit recorded anywhere
    add(t, kind="DEPOSIT", amount=1_000_000, market="KR")
    add(t, kind="BUY", ticker="005930", qty=10, price=50000, style="SWING", stop=45000)
    add(t, kind="HOLD", ticker="BTC", qty=0.1, price=120_000_000, market="COIN", style="LONG")
    add(t, kind="HOLD", ticker="SHIB", qty=1_000_000, price=0.03, market="COIN", style="SWING")
    add(t, kind="HOLD", ticker="XYZCOIN", qty=5, price=1000, market="COIN", style="SWING")                    # not among the thirty: no price
    d = t.account()
    by = {a["market"]: a for a in d["accounts"]}
    assert [a["market"] for a in d["accounts"]] == ["US", "KR", "COIN"] and [a["currency"] for a in d["accounts"]] == ["USD", "KRW", "KRW"]
    assert by["US"]["equity"] == 2000.0 and by["US"]["cash"] == 0.0 and by["US"]["total_pnl"] == 500.0 and by["US"]["equity_krw"] == 2_800_000.0
    assert by["KR"]["equity"] == 1_100_000.0 and by["KR"]["cash"] == 500_000.0
    rows = {(h["market"], h["ticker"]): h for h in d["holdings"]}
    btc, shib = rows[("COIN", "BTC")], rows[("COIN", "SHIB")]
    assert btc["close"] == 100_000.0 * 1400.0 and btc["usd"] == 100_000.0 and btc["value"] == pytest.approx(14_000_000.0) and btc["name"] == "비트코인"      # Binance dollars x the day's rate
    assert btc["change_pct"] == pytest.approx((100_000 / 90_000 - 1) * 100) and shib["close"] == pytest.approx(0.02 / 1000 * 1400)          # quoted per thousand
    assert rows[("COIN", "XYZCOIN")]["close"] is None and by["COIN"]["equity"] is None and by["COIN"]["missing_prices"] == ["XYZCOIN"]
    assert d["total"]["krw"] is None and d["total"]["missing"] == ["코인: XYZCOIN"]                                # never understated: an unknown price leaves the total empty
    assert d["total"]["usdkrw"] == 1400.0 and [c["coin"] for c in d["coins"]] == ["BTC", "SHIB"] and d["journal_count"] == 6 and {r["market"] for r in d["journal"]} == {"US", "KR", "COIN"}
    # the per-market pages still see only their own account
    assert [h["ticker"] for h in t.portfolio()["holdings"]] == ["AAPL"] and [h["ticker"] for h in t.portfolio("KR")["holdings"]] == ["005930"]


def test_the_total_is_complete_when_every_price_is_known(term, coins):  # noqa: F811
    t = term({"KRW=X": 1400.0, "AAPL": 200.0})
    add(t, kind="HOLD", ticker="AAPL", qty=10, price=150, style="LONG", date="2025-03-04")
    add(t, kind="HOLD", ticker="BTC", qty=0.1, price=120_000_000, market="COIN", style="LONG")
    d = t.account()
    assert d["total"]["krw"] == pytest.approx(2_800_000 + 14_000_000) and d["total"]["usd"] == pytest.approx(16_800_000 / 1400) and d["total"]["missing"] == []
    assert d["total"]["total_pnl_krw"] == pytest.approx(500 * 1400 + (14_000_000 - 12_000_000)) and d["total"]["net_deposits_krw"] == pytest.approx(1500 * 1400 + 12_000_000)
    top, second = d["holdings"]
    assert (top["ticker"], second["ticker"]) == ("BTC", "AAPL") and top["weight_total_pct"] + second["weight_total_pct"] == pytest.approx(100.0)
    kr = next(a for a in d["accounts"] if a["market"] == "KR")
    assert kr["records"] == 0 and kr["equity"] == 0.0                                                        # an account never used counts as nothing, not as unknown
    assert any("환율이 움직여 생긴 손익은 들어 있지 않습니다" in n for n in d["notes"]) and any("국내 거래소 가격과" in n for n in d["notes"])


def test_coins_without_a_rate_or_a_reply_are_unknown_not_zero(term, coins):  # noqa: F811
    t = term({"AAPL": 200.0})                                                                                # no won-per-dollar rate today
    add(t, kind="HOLD", ticker="BTC", qty=0.1, price=120_000_000, market="COIN", style="LONG")
    d = t.account()
    assert d["holdings"][0]["close"] is None and d["total"]["krw"] is None and d["total"]["usdkrw"] is None
    coins({}, error="TimeoutError")
    t2 = term({"KRW=X": 1400.0})
    assert t2.account()["coin_error"] == "TimeoutError" and t2.account()["holdings"][0]["status"] == "UNAVAILABLE"


def test_a_voided_coin_entry_stays_in_its_account_and_the_chain_holds(term, coins):  # noqa: F811
    t = term({"KRW=X": 1400.0})
    rec = add(t, kind="HOLD", ticker="BTC", qty=0.1, price=120_000_000, market="COIN", style="LONG")["entry"]
    t.journal_void(rec["id"])
    d = t.account()
    assert d["holdings"] == [] and d["integrity"]["status"] == "OK" and [r["market"] for r in d["journal"]] == ["COIN", "COIN"] and d["journal"][1]["voided"] is True


def test_the_account_page_is_one_request_and_a_phone_may_make_its_entries():
    posts = {path for (method, path) in server.routes(object()) if method == "POST"}
    assert ("GET", "/api/account") in server.routes(object()) and "/api/journal/add" in phone_view.PHONE_WRITES and "/api/journal/add" in posts
