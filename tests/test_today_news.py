"""Same-day check and news record: feeds are read safely, failures stay visible, nothing reaches a score.  No network."""
import gzip
import json
from datetime import datetime, timezone

import pytest

from terminal import news, today

NOW = datetime(2027, 1, 5, 12, 0, tzinfo=timezone.utc)


def rss(*items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{d}</pubDate>{s}</item>" for t, l, d, s in items)
    return f"<rss><channel>{body}</channel></rss>".encode()


class Resp:
    def __init__(self, content=b"<rss/>", code=200):
        self.content, self.status_code = content, code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(str(self.status_code))


class Http:
    def __init__(self, fn):
        self.fn, self.urls = fn, []

    def get(self, url, headers=None, timeout=None):
        self.urls.append(url)
        assert "@" not in headers["User-Agent"]
        return self.fn(url)


def universe(tmp_path, market="US", tickers=("AAA", "BBB", "CCC")):
    (tmp_path / "data" / "qsf").mkdir(parents=True, exist_ok=True)
    rows = [{"ticker": t, "name": f"{t} 회사", "strategy": s} for t in tickers for s in ("SWING", "LONG_TERM")]
    (tmp_path / "data" / "qsf" / f"latest_{market}.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")


def stored(tmp_path, market="US"):
    p = tmp_path / "data" / "news" / market / "2027-01-05.jsonl.gz"
    return [json.loads(x) for x in gzip.open(p, "rt", encoding="utf-8")] if p.exists() else []


GOOD = rss(("새 소식 - 한경", "https://a.example/1", "Tue, 05 Jan 2027 10:00:00 GMT", "<source>한경</source>"), ("옛 소식", "http://a.example/2", "Mon, 04 Jan 2027 10:00:00 +0900", ""))


def test_parse_orders_newest_first_and_strips_the_publisher_suffix():
    items = news.parse_rss(GOOD, "P")
    assert [i["title"] for i in items] == ["새 소식", "옛 소식"]
    assert items[0]["source"] == "한경" and items[1]["source"] == "P"
    assert items[1]["published"] == "2027-01-04T01:00:00+00:00"


def test_a_link_that_is_not_http_never_reaches_the_screen():
    items = news.parse_rss(rss(("x", "javascript:alert(1)", "", ""), ("y", "https://ok.example", "", "")), "P")
    assert [i["title"] for i in items] == ["y"] and items[0]["published"] is None


def test_a_feed_with_a_dtd_is_refused():
    with pytest.raises(ValueError):
        news.parse_rss(b'<!DOCTYPE lolz [<!ENTITY a "a">]><rss/>', "P")


def test_markets_use_their_own_feed_and_kr_searches_the_exact_name():
    assert "s=AAPL" in news.feed_url("AAPL", "US")
    url = news.feed_url("005930", "KR", "삼성전자")
    assert url.startswith(news.GOOGLE_RSS) and "%22%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90%22" in url


def test_record_covers_every_ticker_and_does_not_store_a_headline_twice(tmp_path):
    universe(tmp_path)
    http = Http(lambda u: Resp(GOOD))
    res = news.record(tmp_path, "US", http, lambda: NOW, sleep=lambda s: None)
    assert res["status"] == "OK" and res["ok"] == 3 and res["new_items"] == 6 and len(http.urls) == 3
    assert stored(tmp_path)[0]["first_seen_at"] == NOW.isoformat()
    again = news.record(tmp_path, "US", http, lambda: NOW, sleep=lambda s: None)
    assert again["new_items"] == 0 and len(stored(tmp_path)) == 6
    assert len((tmp_path / "data/news/US/runs.jsonl").read_text().splitlines()) == 2


def test_a_quiet_stock_is_not_a_failure(tmp_path):
    universe(tmp_path)
    res = news.record(tmp_path, "US", Http(lambda u: Resp(b"<rss><channel/></rss>")), lambda: NOW, sleep=lambda s: None)
    assert res["status"] == "OK" and res["new_items"] == 0 and res["failed"] == 0


def test_a_refusal_stops_at_once_and_keeps_what_was_collected(tmp_path):
    universe(tmp_path)
    http = Http(lambda u: Resp(GOOD) if "AAA" in u else Resp(code=429))
    res = news.record(tmp_path, "US", http, lambda: NOW, sleep=lambda s: None)
    assert res["status"] == "FAILED" and res["stopped"] == "REFUSED_429" and res["not_asked"] == 1 and len(http.urls) == 2
    assert len(stored(tmp_path)) == 2


def test_repeated_failures_stop_the_run(tmp_path):
    universe(tmp_path, tickers=tuple(f"T{i}" for i in range(40)))
    http = Http(lambda u: Resp(code=500))
    res = news.record(tmp_path, "US", http, lambda: NOW, sleep=lambda s: None)
    assert res["status"] == "FAILED" and res["stopped"] == "TOO_MANY_FAILURES" and len(http.urls) == news.ABORT_AFTER


def test_no_scan_yet_means_nothing_is_recorded(tmp_path):
    assert news.record(tmp_path, "US", Http(lambda u: Resp()), lambda: NOW)["status"] == "NO_UNIVERSE"


# ---------------------------------------------------------------------- same-day check
def bars(n=25, vol=100, last_vol=300):
    out = [{"date": f"2026-12-{i + 1:02d}", "open": 10.0, "close": 10.0, "volume": vol} for i in range(n - 1)]
    return out + [{"date": "2027-01-05", "open": 11.0, "close": 12.0, "volume": last_vol}]


def test_a_finished_day_is_the_score_session_and_gets_a_volume_ratio():
    q = today.quote_section({"bars": bars(), "last": {"intraday": False}, "status": "REAL"})
    assert q["score_session"] == "2027-01-05" and q["volume_ratio"] == 3 and q["gap_pct"] == pytest.approx(10) and q["change_pct"] == pytest.approx(20)


def test_an_unfinished_day_is_after_the_score_and_gets_no_volume_ratio():
    q = today.quote_section({"bars": bars(), "last": {"intraday": True}, "status": "REAL"})
    assert q["score_session"] == "2026-12-24" and q["intraday"] and q["volume_ratio"] is None and q["volume"] == 300


def test_no_bars_is_unavailable_not_zero():
    assert today.quote_section({"bars": []}) == {"status": "UNAVAILABLE", "score_session": None}


def test_missing_volume_history_gives_no_ratio():
    q = today.quote_section({"bars": bars(n=5), "last": {"intraday": False}, "status": "REAL"})
    assert q["average_volume"] is None and q["volume_ratio"] is None


def test_only_events_after_the_score_session_are_new():
    out = today.new_warnings({"severe": [{"label": "파산", "date": "2027-01-05"}], "negative": [{"label": "옛 악재", "date": "2027-01-04"}]}, "2027-01-04")
    assert out == [{"level": "bad", "label": "파산", "date": "2027-01-05"}]


class FakeCache:
    def cached(self, key, ttl, fn):
        try:
            return {"status": "REAL", "data": fn(), "fetched_at": "t", "error": None}
        except Exception as exc:
            return {"status": "UNAVAILABLE", "data": None, "fetched_at": None, "error": type(exc).__name__}


class FakeQsf:
    now = staticmethod(lambda: NOW)

    def latest(self, market):
        return {"rows": []}

    def _us_events(self, cik, as_of):
        raise RuntimeError("SEC down")

    def _kr_identity(self, code):
        return None

    def kr_company(self, code):
        return {"reports": None}


class FakeTerminal:
    qsf, cache = FakeQsf(), FakeCache()

    def _cik(self, t):
        return "1"

    def chart(self, t, rng):
        return {"bars": bars(), "last": {"intraday": False}, "status": "REAL", "cache": {}}

    def filings(self, t):
        raise RuntimeError("down")


def test_the_market_is_read_on_the_stocks_own_day_and_a_lag_is_reported():
    bars_ = [{"date": "2027-01-04", "close": 100.0}, {"date": "2027-01-05", "close": 90.0}, {"date": "2027-01-06", "close": 80.0}]
    bench, behind, last = today.bench_section({"bars": bars_}, "2027-01-05", "M")
    assert bench["change_pct"] == pytest.approx(-10) and bench["date"] == "2027-01-05" and behind == 1 and last == "2027-01-06"


def test_no_market_bar_that_day_compares_nothing():
    bars_ = [{"date": "2027-01-05", "close": 90.0}, {"date": "2027-01-06", "close": 80.0}]
    assert today.bench_section({"bars": bars_}, "2027-01-04", "M")[0] is None
    assert today.bench_section({"bars": bars_}, "2027-01-05", "M")[0] is None      # no earlier bar to compare with
    assert today.bench_section({"bars": []}, "2027-01-05", "M") == (None, None, None)


def test_each_section_fails_alone_and_says_so(monkeypatch):
    monkeypatch.setattr(news, "fetch", lambda *a, **k: {"items": [], "provider": "P"})
    d = today.build(FakeTerminal(), "AAPL", "US")
    assert d["quote"]["price"] == 12 and d["events_status"] == "UNAVAILABLE" and d["warnings"] == []
    assert d["filings"]["status"] == "UNAVAILABLE" and d["news"]["status"] == "REAL" and d["news"]["items"] == []
    assert d["bench"]["change_pct"] == pytest.approx(20)


def test_a_failed_feed_is_unavailable_not_empty(monkeypatch):
    def boom(*a, **k):
        raise news.FeedRefused("429")
    monkeypatch.setattr(news, "fetch", boom)
    assert today.build(FakeTerminal(), "AAPL", "US")["news"]["status"] == "UNAVAILABLE"


def test_kr_without_a_name_does_not_search_by_bare_code(monkeypatch):
    monkeypatch.setattr(news, "fetch", lambda *a, **k: pytest.fail("searched without a name"))
    assert today.build(FakeTerminal(), "005930", "KR")["news"]["error"] == "NO_NAME"


@pytest.mark.parametrize("t,m", [("../etc", "US"), ("005930", "US"), ("AAPL", "KR"), ("", "US")])
def test_bad_tickers_are_refused(t, m):
    with pytest.raises(ValueError):
        today.build(FakeTerminal(), t, m)


def test_the_check_carries_no_score_and_never_judges_a_headline(monkeypatch):
    monkeypatch.setattr(news, "fetch", lambda *a, **k: {"items": news.parse_rss(GOOD, "P"), "provider": "P"})
    d = today.build(FakeTerminal(), "AAPL", "US")
    assert "score" not in d and not any(k in d["news"]["items"][0] for k in ("sentiment", "score", "tone"))
