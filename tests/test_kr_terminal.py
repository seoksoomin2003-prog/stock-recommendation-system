"""Korean market in the terminal: separate won account, limits, quotes, ECOS, name search.  No network."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from terminal import portfolio as pf, services, sources

NOW = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)      # 17:00 KST, after both closes of the previous US day
DATES = [f"2026-11-0{d}" for d in range(2, 6)]


def bars(close):
    return [{"date": d, "open": close, "high": close, "low": close, "close": close, "adj_close": close, "volume": 1000} for d in DATES]


class FakeSrc:
    """Yahoo stand-in that answers only the symbols in ``prices``: an unknown symbol has no data."""
    def __init__(self, prices):
        self.prices, self.asked = prices, []

    def yahoo_history(self, symbols, period="1y"):
        self.asked += list(symbols)
        return {s: bars(self.prices[s]) for s in symbols if s in self.prices}

    def yahoo_info(self, symbol):
        return {"longName": symbol, "sector": "반도체"}

    def __getattr__(self, name):
        return getattr(sources, name)


@pytest.fixture
def term(tmp_path):
    def make(prices):
        t = services.Terminal(tmp_path, src=FakeSrc(prices), now=lambda: NOW)
        master = pd.DataFrame([{"canonical_ticker": "005930", "yahoo_symbol": "005930.KS", "company_name": "삼성전자", "market": "KOSPI", "industry_class": "NON_FINANCIAL"},
                               {"canonical_ticker": "005935", "yahoo_symbol": "005935.KS", "company_name": "삼성전자우", "market": "KOSPI", "industry_class": "NON_FINANCIAL"},
                               {"canonical_ticker": "035720", "yahoo_symbol": "035720.KS", "company_name": "카카오", "market": "KOSPI", "industry_class": "NON_FINANCIAL"}])
        t.qsf._kr_master = master
        return t
    return make


def add(t, **raw):
    return t.journal_add({"date": "2026-11-02", **raw})


# ---------------------------------------------------------------- journal
def test_market_of():
    assert pf.market_of("005930") == "KR" and pf.market_of("0035S0") == "KR"
    assert pf.market_of("AAPL") == "US" and pf.market_of("BRK.B") == "US" and pf.market_of("^KS11") == "US"


def test_won_and_dollar_cash_are_separate(term):
    t = term({"KRW=X": 1400.0, "005930.KS": 60000.0, "AAPL": 100.0})
    add(t, kind="DEPOSIT", amount=1000)
    add(t, kind="DEPOSIT", amount=1000000, market="KR")
    assert t.portfolio()["summary"]["cash"] == 1000
    assert t.portfolio("KR")["summary"]["cash"] == 1000000
    with pytest.raises(pf.JournalError):                        # dollars cannot pay for a Korean stock
        add(t, kind="BUY", ticker="005930", qty=100, price=60000, style="LONG", stop=50000)
    add(t, kind="BUY", ticker="005930", qty=10, price=60000, style="LONG", stop=50000)
    assert t.portfolio("KR")["summary"]["cash"] == 400000
    assert t.portfolio()["summary"]["cash"] == 1000
    assert [h["ticker"] for h in t.portfolio("KR")["holdings"]] == ["005930"]
    assert t.portfolio("KR")["holdings"][0]["name"] == "삼성전자"
    assert t.portfolio()["holdings"] == []


def test_us_records_have_no_market_field_and_chain_stays_valid(term):
    t = term({"KRW=X": 1400.0})
    add(t, kind="DEPOSIT", amount=1000)
    add(t, kind="DEPOSIT", amount=5000, market="KR")
    recs, integ = t.journal.read()
    assert integ["status"] == "OK"
    assert "market" not in recs[0] and recs[1]["market"] == "KR"


def test_void_follows_the_target_market(term):
    t = term({"KRW=X": 1400.0})
    r = add(t, kind="DEPOSIT", amount=5000, market="KR")
    t.journal_void(r["entry"]["id"])
    assert t.portfolio("KR")["summary"]["cash"] == 0
    assert t.portfolio()["summary"]["cash"] == 0


def test_invalid_market_is_rejected(term):
    t = term({"KRW=X": 1400.0})
    with pytest.raises(pf.JournalError):
        add(t, kind="DEPOSIT", amount=5000, market="JP")


# ---------------------------------------------------------------- limits
def test_korean_limits_are_stricter():
    st = pf.DEFAULT_SETTINGS
    assert pf.limits_for("LONG", st, "KR")["risk_per_trade_pct"] == 1.0
    assert pf.limits_for("LONG", st, "KR")["max_position_pct"] == 20.0
    assert pf.limits_for("SWING", st, "KR")["risk_per_trade_pct"] == 0.5
    assert pf.limits_for("SWING", st, "KR")["max_position_pct"] == 10.0
    assert pf.limits_for("LONG", st)["risk_per_trade_pct"] == 2.0
    assert pf.limits_for(None, st, "KR")["risk_per_trade_pct"] == st["risk_per_trade_pct"]


def test_korean_sizing_uses_korean_limits(term):
    t = term({"KRW=X": 1400.0, "005930.KS": 60000.0})
    add(t, kind="DEPOSIT", amount=10000000, market="KR")
    d = t.sizing("005930", entry=60000, stop=50000, style="SWING")
    assert d["market"] == "KR" and d["settings"]["risk_per_trade_pct"] == 0.5
    assert d["result"]["shares"] == 5           # 0.5% of 10,000,000 = 50,000 at risk; 10,000 per share


def test_korean_alert_price_has_no_decimals(term):
    t = term({"KRW=X": 1400.0, "005930.KS": 45000.0})
    add(t, kind="DEPOSIT", amount=10000000, market="KR")
    add(t, kind="BUY", ticker="005930", qty=10, price=60000, style="LONG", stop=50000)
    stop = [a for a in t.portfolio("KR")["alerts"] if a["code"] == "STOP_HIT"]
    assert stop and "45,000원" in stop[0]["text"] and "50,000원" in stop[0]["text"]


# ---------------------------------------------------------------- total
def test_total_converts_to_won(term):
    t = term({"KRW=X": 1400.0})
    add(t, kind="DEPOSIT", amount=1000)
    add(t, kind="DEPOSIT", amount=500000, market="KR")
    total = t.portfolio("KR")["total"]
    assert total["krw"] == 500000 + 1000 * 1400
    assert t.portfolio()["total"]["krw"] == total["krw"]


def test_total_is_empty_without_fx(term):
    t = term({})
    add(t, kind="DEPOSIT", amount=1000)
    assert t.portfolio()["total"]["krw"] is None


def test_total_is_empty_with_a_missing_price(term):
    t = term({"KRW=X": 1400.0})
    add(t, kind="DEPOSIT", amount=1000000, market="KR")
    add(t, kind="BUY", ticker="005930", qty=1, price=60000, style="LONG", stop=50000)
    assert t.portfolio("KR")["total"]["krw"] is None


# ---------------------------------------------------------------- market data
def test_overview_kr_uses_korean_symbols(term):
    t = term({"^KS11": 2600.0, "091160.KS": 30000.0})
    d = t.overview("KR")
    assert d["market"] == "KR" and "^KS11" in t.src.asked and "SPY" not in t.src.asked
    items = {i["symbol"]: i for g in d["groups"] for i in g["items"]}
    assert items["^KS11"]["close"] == 2600.0
    assert items["091160.KS"]["ticker"] == "091160"
    assert items["^KQ11"]["close"] is None                  # missing stays missing, never 0


def test_chart_maps_code_to_yahoo_symbol(term):
    t = term({"005930.KS": 60000.0})
    c = t.chart("005930", "1y")
    assert c["market"] == "KR" and c["last"]["close"] == 60000.0
    assert t.src.asked == ["005930.KS"]


def test_etf_code_not_on_master_falls_back_to_kospi_symbol(term):
    t = term({"069500.KS": 40000.0})
    assert t.chart("069500", "1y")["last"]["close"] == 40000.0


def test_intraday_uses_korean_close():
    kst_open = datetime(2026, 11, 5, 5, 0, tzinfo=timezone.utc)      # 14:00 KST
    kst_done = datetime(2026, 11, 5, 7, 0, tzinfo=timezone.utc)      # 16:00 KST
    t = SimpleNamespace(now=lambda: kst_open)
    assert services.Terminal._intraday(t, "2026-11-05", "KR") is True
    t = SimpleNamespace(now=lambda: kst_done)
    assert services.Terminal._intraday(t, "2026-11-05", "KR") is False


def test_watchlist_is_split_by_market(term):
    t = term({"AAPL": 100.0, "005930.KS": 60000.0})
    t.watchlist_add("AAPL")
    t.watchlist_add("005930")
    us, kr = t.watchlist_quotes("US"), t.watchlist_quotes("KR")
    assert "AAPL" in us["tickers"] and "005930" not in us["tickers"] and kr["tickers"] == ["005930"]
    assert kr["items"][0]["symbol"] == "005930" and kr["items"][0]["close"] == 60000.0 and kr["items"][0]["name"] == "삼성전자"
    assert kr["items"][0]["qsf"] is None and kr["qsf_scan"]["status"] == "UNAVAILABLE"       # no scan: nothing, never a made-up score


def test_watchlist_shows_scores_from_the_newest_scan_as_stored(term):
    import json
    t = term({"AAPL": 100.0, "005930.KS": 60000.0, "000660.KS": 100000.0})
    for code in ("005930", "000660"):
        t.watchlist_add(code)
    scan = {"status": "REAL", "market": "KR", "session": "2026-11-06", "model_version": "QSF-1.1.7", "rows": [
        {"ticker": "005930", "strategy": "SWING", "score": 44.6, "action": "AVOID", "action_label": "신규 진입 회피", "confidence": "MEDIUM"},
        {"ticker": "005930", "strategy": "LONG_TERM", "score": 62.5, "action": "WATCH", "action_label": "관찰", "confidence": "HIGH"}]}
    path = t.qsf.dir / "latest_KR.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scan), encoding="utf-8")
    before = path.read_bytes()
    kr = t.watchlist_quotes("KR")
    got = {i["symbol"]: i["qsf"] for i in kr["items"]}
    assert got["005930"]["SWING"]["score"] == 44.6 and got["005930"]["LONG_TERM"]["action"] == "WATCH" and got["000660"] is None
    assert kr["qsf_scan"] == {"status": "REAL", "session": "2026-11-06", "model_version": "QSF-1.1.7"} and path.read_bytes() == before


def test_name_search_prefers_exact_match(term):
    t = term({})
    names = [x["name"] for x in t.qsf.kr_search("삼성전자")]
    assert names == ["삼성전자", "삼성전자우"]
    assert t.qsf.kr_search("없는회사") == [] and t.qsf.kr_search("  ") == []


def test_filings_without_dart_key_are_unavailable(term):
    t = term({})
    f = t.filings("005930")
    assert f["status"] == "UNAVAILABLE" and f["market"] == "KR" and f["items"] == []


# ---------------------------------------------------------------- ECOS
class FakeHttp:
    def __init__(self, body=None, exc=None):
        self.body, self.exc, self.url = body, exc, None

    def get(self, url, timeout=None):
        self.url = url
        if self.exc:
            raise self.exc
        return SimpleNamespace(json=lambda: self.body)


def test_ecos_parses_daily_and_monthly():
    daily = FakeHttp({"StatisticSearch": {"row": [{"TIME": "20261104", "DATA_VALUE": "2.50"}]}})
    assert sources.ecos_series("722Y001", "D", "20261101", "20261105", ["0101000"], http=daily, key="k") == [["2026-11-04", 2.5]]
    monthly = FakeHttp({"StatisticSearch": {"row": [{"TIME": "202610", "DATA_VALUE": "118.1"}]}})
    assert sources.ecos_series("901Y009", "M", "202601", "202611", ["0"], http=monthly, key="k") == [["2026-10-01", 118.1]]
    assert monthly.url.endswith("/901Y009/M/202601/202611/0")


def test_ecos_missing_value_is_not_zero():
    h = FakeHttp({"StatisticSearch": {"row": [{"TIME": "20261104", "DATA_VALUE": ""}]}})
    assert sources.ecos_series("722Y001", "D", "a", "b", ["0"], http=h, key="k") == [["2026-11-04", None]]


@pytest.mark.parametrize("http", [FakeHttp(exc=ConnectionError("https://ecos.bok.or.kr/api/StatisticSearch/SECRETKEY/json")),
                                  FakeHttp({"RESULT": {"CODE": "INFO-100", "MESSAGE": "SECRETKEY"}})])
def test_ecos_errors_never_show_the_key(http):
    with pytest.raises(RuntimeError) as e:
        sources.ecos_series("722Y001", "D", "a", "b", ["0"], http=http, key="SECRETKEY")
    assert "SECRETKEY" not in str(e.value) and e.value.__cause__ is None


def test_macro_without_key_is_unavailable_with_reason(term, monkeypatch):
    monkeypatch.delenv("ECOS_API_KEY", raising=False)
    t = term({"KRW=X": 1400.0})
    d = t.macro("KR")
    by = {m["id"]: m for m in d["items"]}
    assert d["configured"] is False and "ECOS_API_KEY" in d["reason"]
    assert by["BOK_RATE"]["status"] == "UNAVAILABLE" and by["BOK_RATE"]["value"] is None
    assert by["KTB10Y-3Y"]["value"] is None
    assert by["KRW=X"]["value"] == 1400.0                   # the rate comes from Yahoo and needs no key
    assert t.health()["ecos"] == "NOT_CONFIGURED"


def test_macro_spread_and_yoy(term, monkeypatch):
    monkeypatch.setenv("ECOS_API_KEY", "k")
    t = term({"KRW=X": 1400.0})
    data = {"817Y002:010210000": [["2026-11-03", 3.0], ["2026-11-04", 3.2]], "817Y002:010200000": [["2026-11-03", 2.5], ["2026-11-04", 2.6]],
            "901Y009:0": [["2025-10-01", 100.0], ["2026-10-01", 102.0]]}
    t.src.ecos_series = lambda stat, cycle, a, b, items: data.get(f"{stat}:{items[0]}", [])
    by = {m["id"]: m for m in t.macro("KR")["items"]}
    assert by["KTB10Y-3Y"]["value"] == pytest.approx(0.6)
    assert by["KR_CPI"]["value"] == pytest.approx(2.0)
    assert by["BOK_RATE"]["value"] is None


# ---------------------------------------------------------------- model
def test_model_kr_without_runs_is_labelled_experimental(term):
    d = term({}).model("KR")
    assert d["baseline"]["status"] == "EXPERIMENTAL" and "run_id" not in d["baseline"]
