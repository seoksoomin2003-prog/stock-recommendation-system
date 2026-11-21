"""The coin screen on a machine without the predictor's files: public market data (terminal/coin_source.py) and the plain rank the
bridge makes from it.  A made-up exchange, no network."""
import json
from pathlib import Path

import numpy as np
import pytest

from terminal import assistant as A, coin_bridge as cb, coin_source as cs, server

ROOT = Path(__file__).resolve().parents[1]
H = cs.BAR_MS
CLOSE = 1_795_233_600_000                     # a four-hour close
NOW = CLOSE + 3600_000                        # an hour into the next bar
OLD = CLOSE - 400 * 86400_000
NAMES = ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "TRX", "LTC", "LINK", "DOT", "AVAX", "UNI", "ATOM", "1000SHIB"]


class Exchange:
    """A stand-in for the four public endpoints.  Coin k is more volatile, moves more with the market and pays more funding than
    coin k-1, so the plain rank must put the coins in this order."""
    def __init__(self, names=NAMES, bars=400):
        self.names, self.bars, self.calls, self.down = names, bars, [], False

    def get(self, path, params):
        self.calls.append(path)
        if self.down:
            raise ConnectionError("https://host.example/secret?key=1")
        if path.endswith("exchangeInfo"):
            good = [{"symbol": f"{n}USDT", "baseAsset": n, "quoteAsset": "USDT", "contractType": "PERPETUAL", "status": "TRADING", "underlyingType": "COIN", "onboardDate": OLD} for n in self.names]
            return {"symbols": good + [
                {"symbol": "NEWUSDT", "baseAsset": "NEW", "quoteAsset": "USDT", "contractType": "PERPETUAL", "status": "TRADING", "underlyingType": "COIN", "onboardDate": NOW - 30 * 86400_000},
                {"symbol": "USDCUSDT", "baseAsset": "USDC", "quoteAsset": "USDT", "contractType": "PERPETUAL", "status": "TRADING", "underlyingType": "COIN", "onboardDate": OLD},
                {"symbol": "BTCDOMUSDT", "baseAsset": "BTCDOM", "quoteAsset": "USDT", "contractType": "PERPETUAL", "status": "TRADING", "underlyingType": "INDEX", "onboardDate": OLD},
                {"symbol": "GONEUSDT", "baseAsset": "GONE", "quoteAsset": "USDT", "contractType": "PERPETUAL", "status": "SETTLING", "underlyingType": "COIN", "onboardDate": OLD},
                {"symbol": "BTCUSDT_270326", "baseAsset": "BTC", "quoteAsset": "USDT", "contractType": "CURRENT_QUARTER", "status": "TRADING", "underlyingType": "COIN", "onboardDate": OLD},
                {"symbol": "BTCUSDC", "baseAsset": "BTC", "quoteAsset": "USDC", "contractType": "PERPETUAL", "status": "TRADING", "underlyingType": "COIN", "onboardDate": OLD}]}
        if path.endswith("ticker/24hr"):
            every = [f"{n}USDT" for n in self.names] + ["NEWUSDT", "USDCUSDT", "BTCDOMUSDT", "GONEUSDT", "BTCUSDT_270326", "BTCUSDC"]
            return [{"symbol": s, "quoteVolume": str(9e12 if k >= len(self.names) else 1e9 * (len(self.names) - k))} for k, s in enumerate(every)]
        k = self.names.index(params["symbol"][:-4])
        if path.endswith("klines"):
            assert params["interval"] == "4h" and params["limit"] == cs.BARS
            rng = np.random.default_rng(11)
            market = rng.normal(0, 0.01, self.bars + 1)
            px = 100.0 * (k + 1) * np.exp(np.cumsum((0.4 + 0.1 * k) * market + np.random.default_rng(100 + k).normal(0, 0.001 * (k + 1), self.bars + 1)))
            t = CLOSE - H * (self.bars - np.arange(self.bars + 1))          # the last row opens at CLOSE: that bar is still open
            return [[int(a), f"{p:.8f}", f"{p * 1.01:.8f}", f"{p * 0.99:.8f}", f"{p:.8f}", "1000", int(a) + H - 1, "0", 1, "0", "0", "0"] for a, p in zip(t, px)]
        if path.endswith("fundingRate"):
            return [{"symbol": params["symbol"], "fundingTime": int(CLOSE - 2 * H * (30 - j)), "fundingRate": f"{0.00002 * (k - 5):.8f}"} for j in range(31)]
        raise AssertionError(path)


@pytest.fixture(autouse=True)
def no_real_exchange(monkeypatch):
    monkeypatch.delenv(cb.PUBLIC_OFF, raising=False)
    monkeypatch.setattr(cs, "_http_get", lambda path, params: (_ for _ in ()).throw(AssertionError("a test reached the real exchange")))
    monkeypatch.setattr(cs, "_FAILED", {})


def load(ex, base, now=NOW):
    return cs.load(base, now, get=ex.get, sleep=lambda s: None)


def test_the_universe_is_the_most_traded_usdt_perpetuals_on_coins():
    ex = Exchange()
    info, tickers = ex.get("/fapi/v1/exchangeInfo", {}), ex.get("/fapi/v1/ticker/24hr", {})
    assert cs.pick(info, tickers, NOW) == [f"{n}USDT" for n in NAMES]            # a new listing, a stablecoin, an index, a settling contract, a quarterly and a USDC pair are left out
    assert cs.pick(info, tickers, NOW, 3) == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert cs.latest_close(NOW) == CLOSE and cs.latest_close(CLOSE) == CLOSE and cs.latest_close(CLOSE - 1) == CLOSE - H


def test_one_refresh_per_close_is_kept_on_disk_and_holds_closed_bars_only(tmp_path):
    ex = Exchange()
    got = load(ex, tmp_path)
    assert got["close_ms"] == CLOSE and got["symbols"][0] == "BTCUSDT" and len(got["symbols"]) == 15 and "error" not in got
    bars = got["arrays"]["bars"]["BTCUSDT"]
    assert bars.shape == (400, 6) and bars[-1, 0] == CLOSE - H                   # the bar that opened at CLOSE had not closed
    assert got["arrays"]["funding"]["BTCUSDT"].shape == (31, 2)
    assert len(ex.calls) == 2 + 2 * 15 and (tmp_path / cs.CACHE).exists()
    again = load(ex, tmp_path, NOW + 2 * 3600_000)
    assert len(ex.calls) == 32 and again["close_ms"] == CLOSE                    # same close: the stored reply, no request
    load(ex, tmp_path, NOW + 4 * 3600_000)
    assert len(ex.calls) == 64                                                   # the next close: one more refresh
    with pytest.raises(ValueError):
        cs.fetch(Exchange(names=NAMES[:5]).get, NOW, lambda s: None)             # too few coins is a failure, not a short list


def test_a_refused_refresh_shows_the_stored_reply_and_is_not_tried_harder(tmp_path):
    ex = Exchange()
    load(ex, tmp_path)
    ex.down = True
    later = NOW + 4 * 3600_000
    old = load(ex, tmp_path, later)
    assert old["close_ms"] == CLOSE and old["error"] == "ConnectionError" and len(ex.calls) == 33
    assert "host.example" not in json.dumps({k: v for k, v in old.items() if k != "arrays"})          # the failure's type, never its text
    load(ex, tmp_path, later + 60_000)
    assert len(ex.calls) == 33                                                   # nothing asked for ten minutes
    load(ex, tmp_path, later + cs.RETRY_AFTER_S * 1000)
    assert len(ex.calls) == 34
    ex.down = False
    assert "error" not in load(ex, tmp_path, later + 2 * cs.RETRY_AFTER_S * 1000)
    none = Exchange()
    none.down = True
    assert load(none, tmp_path / "fresh") == {"error": "ConnectionError"} and load(none, tmp_path / "fresh", NOW + 1000) == {"error": "ConnectionError"} and len(none.calls) == 1
    (tmp_path / "torn" / cs.CACHE).parent.mkdir(parents=True)
    (tmp_path / "torn" / cs.CACHE).write_text('{"close_ms": 17', encoding="utf-8")
    assert load(Exchange(), tmp_path / "torn")["close_ms"] == CLOSE              # an unreadable stored reply is fetched again


def test_the_plain_rank_weighs_the_three_signals_the_same_and_needs_two_of_them():
    low, mid, high = {"A": 1.0, "B": 2.0, "C": 3.0}, {"A": 2.0, "B": 1.0, "C": 3.0}, {"A": 1.0, "B": 2.0, "C": None}
    got = cb.simple_rank(low, mid, high)
    assert got["A"] == pytest.approx((1.0 + 0.5 + 1.0) / 3) and got["B"] == pytest.approx((0.5 + 1.0 + 0.0) / 3) and got["C"] == pytest.approx(0.0)      # C: two signals, last in both
    assert cb.simple_rank({"A": 1.0, "B": 2.0}, {"A": None, "B": None}, {"A": None, "B": None}) == {"A": None, "B": None}
    assert cb.simple_rank({"A": 1.0, "B": 1.0, "C": 2.0}, {"A": 1.0, "B": 1.0, "C": 2.0}, {"A": 1.0, "B": 1.0, "C": 2.0})["A"] == pytest.approx(0.75)   # a tie shares its places


def test_without_the_predictor_the_bridge_ranks_public_data_and_says_what_it_is(tmp_path, monkeypatch):
    ex = Exchange()
    public = lambda base, now: cs.load(base, now, get=ex.get, sleep=lambda s: None)      # noqa: E731
    d = cb.read(now_ms=NOW, folder=tmp_path / "no-predictor", base=tmp_path, public=public)
    assert d["status"] == "REAL" and d["mode"] == "SIMPLE" and d["version"] is None and d["close_ms"] == CLOSE and d["caveats"] == cb.SIMPLE_CAVEATS and d["mode_note"] == cb.SIMPLE_NOTE
    assert "등록된 점수(α)가 아닙니다" in d["mode_note"] and "시험한 적이 없습니다" in d["mode_note"] and "터미널이 직접 받음" in d["source"]
    rows = d["rows"]
    assert [r["coin"] for r in rows] == [cb.coin_of(n + "USDT") for n in NAMES] and rows[-1]["per_thousand"] is True
    assert all(r["alpha"] is None and r["beats_cost"] is None for r in rows) and rows[0]["score"] == 100.0 and rows[-1]["score"] == 0.0
    assert [r["score"] for r in rows] == sorted((r["score"] for r in rows), reverse=True) and rows[0]["rank"] == 1 and rows[0]["of"] == 15
    assert rows[0]["sigma_place"] == 1 and rows[0]["beta_place"] == 1 and rows[0]["funding_place"] == 1 and rows[0]["price"] is not None and rows[0]["change_7d"] is not None
    assert d["market"]["coins"] == 15 and d["market"]["btc_price"] == rows[0]["price"]
    assert cb.read(now_ms=NOW + 10 * 3600_000, folder=tmp_path / "no-predictor", base=tmp_path, public=lambda b, n: {**cs.load(b, NOW, get=ex.get), "error": "Timeout"})["status"] == "STALE"
    failed = cb.read(now_ms=NOW, folder=tmp_path / "no-predictor", base=tmp_path / "x", public=lambda b, n: {"error": "ConnectionError"})
    assert failed["status"] == "UNAVAILABLE" and "ConnectionError" in failed["reason"] and "공개 시세도 받지 못했습니다" in failed["reason"]
    assert cb.read(now_ms=NOW, folder=tmp_path / "no-predictor")["status"] == "UNAVAILABLE"            # no base folder given: nothing is fetched
    monkeypatch.setenv(cb.PUBLIC_OFF, "1")
    calls = len(ex.calls)
    off = cb.read(now_ms=NOW + 8 * 3600_000, folder=tmp_path / "no-predictor", base=tmp_path, public=public)
    assert off["status"] == "UNAVAILABLE" and len(ex.calls) == calls                                    # the switch: the exchange is not asked


def test_the_predictors_files_win_and_the_exchange_is_not_asked(tmp_path):
    from tests.test_coin_bridge import CLOSE as SCORED, make
    folder = make(tmp_path / "p")
    asked = []
    d = cb.read(now_ms=SCORED + H, folder=folder, base=tmp_path, public=lambda b, n: asked.append(1) or {"error": "x"})
    assert d["mode"] == "REGISTERED" and d["status"] == "REAL" and d["rows"][0]["alpha"] is not None and d["caveats"] == cb.CAVEATS and not asked and "mode_note" not in d


class Clock:
    base = Path(".")

    @staticmethod
    def now():
        from datetime import datetime, timezone
        return datetime(2026, 11, 21, 12, tzinfo=timezone.utc)


def test_the_assistant_speaks_of_a_plain_rank_and_never_of_an_expected_return(tmp_path, monkeypatch):
    ex = Exchange()
    state = {"now": NOW}
    monkeypatch.setattr(A, "_coin_read", lambda terminal=None: cb.read(now_ms=state["now"], folder=tmp_path / "none", base=tmp_path, public=lambda b, n: cs.load(b, NOW, get=ex.get, sleep=lambda s: None)))
    b = A.briefing(Clock(), "COIN")
    assert [i["kind"] for i in b["items"]] == ["COIN_SIMPLE", "COIN_MARKET", "COIN_TOP", "COIN_CAVEAT"] and "간이 순위" in b["note"] and "등록된 점수 아님" in b["note"]
    assert b["items"][0]["text"] == cb.SIMPLE_NOTE and "간이 순위 상위 3개" in b["items"][2]["text"] and "비트코인(BTC) 간이 점수 100점" in b["items"][2]["text"] and "기대수익이 아니며" in b["items"][2]["text"]
    assert "현물을 사는 사람" in b["items"][3]["text"] and "-62.7%" in b["items"][3]["text"]
    note = A.answer(Clock(), "솔라나 점수 왜 이래?", "COIN")
    assert note["intent"] == "COIN_NOTE" and "간이 순위는 대상 15개 중 3위" in note["summary"] and "기대수익과 비용 비교가 없습니다" in note["summary"] and "등록된 점수 아님" in note["basis"]
    by = {s["title"]: s["lines"] for s in note["sections"]}
    assert "거래소 공개 시세에서" in by["점수를 만든 신호 셋"][-1] and by["이 점수가 말하지 않는 것"] == cb.SIMPLE_CAVEATS
    top = A.answer(Clock(), "코인 상위는?", "COIN")
    assert top["title"] == "코인 간이 순위" and top["summary"].startswith("간이 순위 1위는 비트코인(BTC)입니다(간이 점수 100점)") and "등록된 점수가 아니고" in top["summary"]
    trust = A.answer(Clock(), "이 코인 점수 믿어도 돼?", "COIN")
    assert trust["intent"] == "COIN_TRUST" and "수익으로 시험한 적이 없어" in trust["summary"] and trust["sections"][0]["lines"] == [cb.SIMPLE_NOTE]
    assert all("터미널은 그 값을 읽어 보여 줄 뿐" not in x for x in trust["lines"])
    assert "최근 거래대금이 큰 30개" in A.answer(Clock(), "help", "COIN")["summary"]
    for q in A.COIN_EXAMPLES:
        text = json.dumps(A.answer(Clock(), q, "COIN"), ensure_ascii=False)
        assert '"status": "REAL"' in text, q
        for word in ("사세요", "매수하세요", "파세요", "오를 것입니다", "상승할 것", "기대 상대 폭", "None", "NaN", "horizon_bot_beta 점수 v"):
            assert word not in text, (q, word)
    state["now"] = NOW + 12 * 3600_000
    stale = A.briefing(Clock(), "COIN")["items"][0]
    assert stale["kind"] == "COIN_STALE" and "거래소에서 새 시세를 받지 못해" in stale["text"] and "run_predictor" not in stale["text"]


def test_the_public_source_asks_for_market_data_only_and_is_wired_in():
    src = (ROOT / "terminal" / "coin_source.py").read_text(encoding="utf-8")
    assert src.count("https://") == 1 and 'HOST = "https://fapi.binance.com"' in src
    for banned in ("apiKey", "X-MBX", "signature", "/order", "/account", "/balance", "/leverage", "os.environ", "SEC_USER_AGENT", "@"):
        assert banned not in src, banned
    assert set(__import__("re").findall(r'"(/fapi/[^"]+)"', src)) == {"/fapi/v1/exchangeInfo", "/fapi/v1/ticker/24hr", "/fapi/v1/klines", "/fapi/v1/fundingRate"}
    assert "coin_bridge.read(base=t.base)" in (ROOT / "terminal" / "server.py").read_text(encoding="utf-8")
    coin = (server.STATIC / "coin.js").read_text(encoding="utf-8")
    assert 'const simple = d.mode === "SIMPLE";' in coin and "등록된 점수가 아닌 간이 순위입니다" in coin and "esc(d.mode_note" in coin and "esc(d.fetch_error)" in coin
    design = (ROOT / "reports" / "CRYPTO_ENGINE_DESIGN_2026_11_21.md").read_text(encoding="utf-8")
    assert "예측기 파일이 없는 기기" in design and "간이 순위" in design and "robots.txt" in design
