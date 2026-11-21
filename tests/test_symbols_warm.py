"""Symbol lookup among the scanned stocks, and the warm-up of the first screen (terminal review of 2026-11-22)."""
import json
import urllib.request

from terminal import assistant as A
from terminal import symbols, warm
from tests.test_assistant import FakeTerminal
from tests.test_terminal_1 import _loopback_only, live  # noqa: F401  (fixtures: a local server on 127.0.0.1 only)

STOCKS = symbols.universe({"US": [{"ticker": "AAPL", "name": "Apple Inc."}, {"ticker": "AAPL", "name": "Apple Inc."}, {"ticker": "AAP", "name": "Advance Auto Parts"}, {"ticker": "APP", "name": "AppLovin"},
                                  {"ticker": "A", "name": "Agilent Technologies"}, {"ticker": "MSFT", "name": "Microsoft Corporation"}, {"ticker": "GOOGL", "name": "Alphabet Inc."}],
                           "KR": [{"ticker": "005930", "name": "삼성전자"}, {"ticker": "005935", "name": "삼성전자우"}, {"ticker": "035720", "name": "카카오"}]})


def test_a_mistyped_ticker_is_answered_with_the_stocks_it_may_have_meant():
    assert len(STOCKS) == 9                                                    # a stock listed once per strategy is one entry
    assert symbols.distance("APPL", "AAPL") == 1 and symbols.distance("AALP", "AAPL") == 1 and symbols.distance("MSFT", "AAPL") == 3 and symbols.distance("A", "AAPL") == 3
    got = symbols.suggest(STOCKS, "appl", "US")
    assert got["exact"] is None and [(x["ticker"], x["match"]) for x in got["items"]] == [("APP", "NAME_START"), ("AAPL", "NAME_START")]      # AppLovin and Apple both begin with it; AAP does not
    assert [(x["ticker"], x["match"]) for x in symbols.suggest(STOCKS, "MSTF", "US")["items"]] == [("MSFT", "NEAR")]      # two letters swapped
    assert [(x["ticker"], x["match"]) for x in symbols.suggest(STOCKS, "GOOGK", "US")["items"]] == [("GOOGL", "NEAR")]
    near = symbols.suggest(STOCKS + [{"ticker": "MSF", "name": "Zeta", "market": "US"}], "MSTF", "US")["items"]
    assert [x["ticker"] for x in near] == ["MSFT", "MSF"]                                                               # among near misses the same length comes first
    exact = symbols.suggest(STOCKS, "aapl", "US")
    assert exact["exact"] == {"ticker": "AAPL", "name": "Apple Inc.", "market": "US"} and exact["items"][0]["match"] == "EXACT"
    assert [x["ticker"] for x in symbols.suggest(STOCKS, "AA", "US")["items"]][:2] == ["AAP", "AAPL"]                 # prefix, shorter first
    assert symbols.suggest(STOCKS, "apple", "US")["items"][0] == {"ticker": "AAPL", "name": "Apple Inc.", "market": "US", "match": "NAME_START"}
    assert [x["ticker"] for x in symbols.suggest(STOCKS, "soft", "US")["items"]] == ["MSFT"]                           # inside the name
    kr = symbols.suggest(STOCKS, "삼성", "US")
    assert [x["ticker"] for x in kr["items"]] == ["005930", "005935"] and kr["items"][0]["market"] == "KR"            # found across markets
    assert [x["ticker"] for x in symbols.suggest(STOCKS, "00593", "KR")["items"]] == ["005930", "005935"]
    assert symbols.suggest(STOCKS, "005931", "KR")["items"] == []                                                     # a wrong digit is another company: no near match for codes
    assert symbols.suggest(STOCKS, "  ", "US") == {"query": "", "market": "US", "exact": None, "items": []} and symbols.suggest(STOCKS, "ZZZZZZZ", "US")["items"] == []
    assert symbols.suggest(STOCKS, "a", "KR")["items"][0]["ticker"] == "A"                                            # an exact ticker comes first even on the other market's screen


def test_the_server_answers_symbol_questions_and_the_assistant_offers_what_was_meant(live, tmp_path):
    url, _ = live
    with urllib.request.urlopen(f"{url}/api/symbols?q=zz&market=US", timeout=5) as r:
        got = json.loads(r.read())
    assert got["query"] == "zz" and got["items"] == [] and got["exact"] is None                                        # no scan in this scratch terminal: nothing to offer, no error
    term = FakeTerminal(tmp_path)
    ans = A.answer(term, "APPL 분석해 줘", "US")
    assert ans["status"] == "UNKNOWN_STOCK" and ans["sections"][0]["title"] == "혹시 이 종목인가요" and ans["sections"][0]["lines"][0].startswith("AAPL Apple Inc.(미국)")
    assert ans["follow"][0] == "AAPL 분석해 줘" and ans["suggestions"][0]["ticker"] == "AAPL" and "비슷한 종목" in ans["summary"]
    none = A.answer(term, "QQQQQ 분석해 줘", "US")
    assert none["status"] == "UNKNOWN_STOCK" and none["follow"] == [] and none["sections"][0]["title"] == "할 수 있는 것"


def test_the_first_screen_is_computed_once_per_scan_and_a_failure_is_tried_again(tmp_path, monkeypatch):
    term = FakeTerminal(tmp_path)
    calls = []
    monkeypatch.setattr(A, "briefing", lambda t, market: calls.append(market) or {})
    seen = {}
    assert set(warm.warm_once(term, seen)) == {"US", "KR"} and calls == ["US", "KR"] and seen["US"] == term.qsf.latest("US")["session"]
    assert warm.warm_once(term, seen) == {} and calls == ["US", "KR"]                                                 # the same scan is not computed again

    def broken(t, market):
        raise RuntimeError("no")
    monkeypatch.setattr(A, "briefing", broken)
    seen.clear()
    assert warm.warm_once(term, seen) == {} and seen == {}                                                            # nothing is marked as done, so the next turn tries again
    naps = []
    monkeypatch.setattr(A, "briefing", lambda t, market: calls.append(market) or {})
    thread = warm.start(term, every=7, sleep=naps.append, turns=2)
    thread.join(timeout=5)
    assert not thread.is_alive() and naps == [7, 7] and calls[-2:] == ["US", "KR"] and thread.daemon
