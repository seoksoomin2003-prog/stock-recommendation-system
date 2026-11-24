"""2026-11-24: the trade forms' automatic price (terminal/price_fill.py, /api/price) and the deal pin (terminal/qsf/deal_pin.py,
decision 14 (가) delegated by the user).  No network."""
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from terminal import price_fill
from terminal.qsf import deal_pin, engine, holding, ledger
from tests.test_qsf import ctx

ROOT = Path(__file__).resolve().parents[1]
DEAL = [{"form": "DEFM14A", "date": "2026-08-20", "label": "합병 주주총회 위임장"}]


def src(*parts):
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


# ---------------------------------------------------------------------- price for the forms
def test_pick_takes_the_last_close_on_or_before_the_day():
    rows = [{"date": "2026-11-19", "close": 10.0}, {"date": "2026-11-20", "close": 11.0}, {"date": "2026-11-23", "close": 12.0}]
    today = date(2026, 11, 24)
    assert price_fill.pick(rows, None, today) == {"status": "REAL", "close": 12.0, "date": "2026-11-23", "exact": False}
    got = price_fill.pick(rows, date(2026, 11, 22), today)                     # a Sunday: the Friday close, said to be the day before
    assert got["close"] == 11.0 and got["date"] == "2026-11-20" and got["exact"] is False
    assert price_fill.pick(rows, date(2026, 11, 20), today)["exact"] is True


def test_pick_never_invents_a_price():
    rows = [{"date": "2026-11-19", "close": 10.0}]
    assert price_fill.pick(rows, date(2020, 1, 2), date(2026, 11, 24)) == {"status": "UNAVAILABLE", "close": None, "date": None, "reason": "BEFORE_HISTORY"}
    assert price_fill.pick([], None, date(2026, 11, 24))["reason"] == "NO_PRICE"
    assert price_fill.pick(rows, None, date(2026, 12, 24))["status"] == "STALE"            # a feed that stopped is named as old
    with pytest.raises(ValueError, match="INVALID_DATE"):
        price_fill.parse_day("24/11/2026")


def test_korean_closes_are_the_traded_prices_not_the_adjusted_ones():
    data = np.full((6, 3, 1), np.nan)
    data[4, :, 0] = [195100.0, np.nan, 191900.0]                      # row 4 = CLOSE in kr_bars; a halted day has none
    pan = {"codes": {"005930": 0}, "dates": ["2026-03-03", "2026-03-04", "2026-11-23"], "data": data}
    assert price_fill.kr_raw_closes("005930", pan, 4) == [{"date": "2026-03-03", "close": 195100.0}, {"date": "2026-11-23", "close": 191900.0}]
    assert price_fill.kr_raw_closes("000660", pan, 4) == []


def test_coin_close_is_the_last_bar_closed_by_the_end_of_the_korean_day():
    h = 4 * 3600 * 1000
    start = 1763910000000                                     # 2025-11-24 00:00 KST, in ms
    bars = np.array([[start + i * h, 1, 1, 1, 100.0 + i, 1] for i in range(12)])
    got = price_fill.coin_close(bars, 1.0, h, date(2025, 11, 24), date(2025, 11, 26))
    assert got["usd"] == 105.0 and got["date"] == "2025-11-25" and got["at"] == "2025-11-25 00:00"
    assert price_fill.coin_close(None, 1.0, h, None, date(2025, 11, 26)) is None


def test_the_forms_fill_only_untouched_prices_and_say_where_the_price_came_from():
    app = src("terminal", "static", "app.js")
    assert "function priceAuto(form, opts)" in app and 'e.isTrusted' in app and "실제 체결가와 다르면 고쳐 쓰세요" in app
    assert 'INVALID_DATE: "' in app                           # the error has its sentence
    assert 'priceAuto(form, { kinds: ["BUY", "SELL"]' in src("terminal", "static", "paper.js")
    assert 'priceAuto(f, { kinds: ["BUY", "SELL", "HOLD"], market: () => f.market.value' in src("terminal", "static", "account.js")
    assert '("GET", "/api/price")' in src("terminal", "server.py")


# ---------------------------------------------------------------------- deal pin
def _bars(step):
    return [{"close": 72.0 * (1 + step * (1 if i % 2 else -1))} for i in range(30)]


def test_a_deal_filing_alone_does_not_pin_a_stock():
    assert deal_pin.pin(DEAL, _bars(0.02)) is None            # a buyer's filing beside a moving price: not pinned
    assert deal_pin.pin([], _bars(0.0001)) is None            # a still price without a filing: not pinned
    assert deal_pin.pin(DEAL, _bars(0.0001))["vol20"] < deal_pin.PIN_VOL
    assert deal_pin.PIN_VOL == 10.0 and deal_pin.WINDOW == 20


def test_a_pinned_stock_keeps_its_score_but_gets_no_buy_band_and_no_entry():
    plain = engine.score(ctx(), "SWING")
    c = ctx()
    c["deal_pin"] = {"form": "DEFM14A", "date": "2026-08-20", "label": "합병 주주총회 위임장", "vol20": 1.6}
    r = engine.score(c, "SWING")
    assert r["score"] == plain["score"]                                       # the score is never touched
    assert plain["band"] in engine.BUY_CODES and plain["actionability"] == "ACTIONABLE"          # the fixture reaches the buy band
    assert r["band"] == "HOLD_WATCH" and r["deal_held"] is True and "합병 절차로 가격이 묶여" in r["band_label"] and r["raw_action"] != "BUY"
    e = holding.entry_status(r, c)
    assert e["status"] == "NO_VALID_ENTRY_SETUP" and "인수 가격까지뿐" in e["reason"]
    assert "deal_pin" in ledger.FIELDS and "deal_held" in ledger.FIELDS
    assert plain["deal_pin"] is None and plain["deal_held"] is False


def test_the_top_three_record_is_not_changed_by_the_pin():
    assert "deal" not in src("terminal", "qsf", "top_picks.py")
