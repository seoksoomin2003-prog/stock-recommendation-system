"""A stock's recorded score history: read from the ledger as stored, in session order, version changes marked, nothing written."""
import json

from terminal.qsf import history as hi
from terminal.qsf.ledger import Ledger


def card(t, strategy="SWING", score=60.0, version="QSF-1.1.7", action="WATCH", market="KR"):
    dom = {d: {"points": 1.0, "score_100": 50.0, "coverage": 1.0} for d in ("TECHNICAL", "FUNDAMENTAL", "RISK", "EVENTS", "REGIME")}
    return {"market": market, "ticker": t, "strategy": strategy, "model_version": version, "score": score, "action": action, "band": "NEUTRAL", "price": 100.0,
            "domains": dom, "factors": [], "levels": {"target": None, "stop": None}}


def test_sessions_in_order_with_version_changes_marked(tmp_path):
    led = Ledger(tmp_path)
    led.append("2026-11-05", "KR", [card("A", score=55.0, version="QSF-1.1.2"), card("B")])
    led.append("2026-11-03", "KR", [card("A", score=50.0, version="QSF-1.1.2")])
    led.append("2026-11-06", "KR", [card("A", score=70.0), card("A", "LONG_TERM", 40.0)])
    led.append("2026-11-06", "US", [card("A", score=99.0, market="US")])
    out = hi.history(led, "KR", "A")
    sw = out["strategies"]["SWING"]
    assert out["status"] == "REAL" and [r["session"] for r in sw] == ["2026-11-03", "2026-11-05", "2026-11-06"]
    assert [r["score"] for r in sw] == [50.0, 55.0, 70.0] and [r["model_changed"] for r in sw] == [False, False, True]
    assert [r["score"] for r in out["strategies"]["LONG_TERM"]] == [40.0] and sw[0]["domains"]["TECHNICAL"] == 50.0


def test_first_record_of_a_session_stands(tmp_path):
    led = Ledger(tmp_path)
    led.append("2026-11-06", "KR", [card("A", score=60.0)])
    led.append("2026-11-06", "KR", [card("A", score=99.0), card("B")])     # the ledger keeps the first; the history agrees
    assert [r["score"] for r in hi.history(led, "KR", "A")["strategies"]["SWING"]] == [60.0]


def test_a_voided_shard_is_left_out(tmp_path):
    led = Ledger(tmp_path)
    first = led.append("2026-11-05", "KR", [card("A", score=10.0)])["file"]
    led.append("2026-11-06", "KR", [card("A", score=70.0)])
    led.void_shard(first, "test")
    assert [r["session"] for r in hi.history(led, "KR", "A")["strategies"]["SWING"]] == ["2026-11-06"]


def test_no_record_is_not_an_empty_success(tmp_path):
    out = hi.history(Ledger(tmp_path), "KR", "A")
    assert out["status"] == "NO_RECORD" and out["strategies"] == {} and out["reason"]


def test_a_broken_ledger_shows_nothing(tmp_path):
    led = Ledger(tmp_path)
    name = led.append("2026-11-06", "KR", [card("A")])["file"]
    (led.dir / name).write_bytes(b"tampered")
    assert hi.history(led, "KR", "A")["status"] == "UNAVAILABLE"


def test_reading_writes_nothing(tmp_path):
    led = Ledger(tmp_path)
    led.append("2026-11-06", "KR", [card("A")])
    before = {p.name: p.read_bytes() for p in led.dir.iterdir()}
    hi.history(led, "KR", "A")
    assert {p.name: p.read_bytes() for p in led.dir.iterdir()} == before


def test_the_route_passes_ticker_and_market():
    from terminal.server import routes

    class T:
        def qsf_history(self, t, market):
            return {"t": t, "market": market}
    fn = routes(T())[("GET", "/api/qsf/history")]
    assert fn({"t": "005930", "market": "KR"}, {}) == {"t": "005930", "market": "KR"}
    assert json.dumps(fn({"t": "AAPL"}, {})) == json.dumps({"t": "AAPL", "market": "US"})


def test_the_service_refuses_a_bad_ticker_or_market(tmp_path):
    import pytest

    from terminal.services import Terminal
    t = Terminal.__new__(Terminal)

    class Q:
        ledger = Ledger(tmp_path)
    t._qsf = Q()
    assert t.qsf_history("005930", "KR")["status"] == "NO_RECORD" and t.qsf_history("aapl", "US")["ticker"] == "AAPL"
    for bad in [("../x", "KR"), ("12345", "KR"), ("AAPL", "JP")]:
        with pytest.raises(ValueError):
            t.qsf_history(*bad)
