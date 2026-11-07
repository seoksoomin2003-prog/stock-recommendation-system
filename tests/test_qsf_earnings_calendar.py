"""Upcoming earnings: only stored dates, no network, a missing date is counted and never shown as 'no earnings'."""
import json
from datetime import date, datetime, timezone

import pytest

from terminal.qsf import earnings_calendar as ec

TODAY = date(2026, 11, 9)
NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc).timestamp()


def rec(*dates, age_days=1.0):
    return {"stored_at": NOW - age_days * 86400, "data": list(dates)}


def test_window_order_tags_and_counts():
    rows = [{"ticker": "A", "name": "A Inc", "strategy": "SWING", "action": "BUY"}, {"ticker": "A", "strategy": "LONG_TERM", "action": "WATCH"},
            {"ticker": "B", "strategy": "SWING", "action": "WATCH"}, {"ticker": "C", "strategy": "SWING", "action": "BUY"},
            {"ticker": "D", "strategy": "SWING", "action": "WATCH"}, {"ticker": "E", "strategy": "SWING"}]
    store = {"A": rec("2026-08-01", "2026-11-12"), "B": rec("2026-11-12"), "C": rec("2026-12-30"), "D": rec("2026-08-01"), "H": rec("2026-11-09", age_days=10)}
    out = ec.upcoming(rows, store.get, TODAY, NOW, 14, held={"H"}, watched={"B"})
    assert [i["ticker"] for i in out["items"]] == ["H", "B", "A"]
    a = out["items"][2]
    assert a["date"] == "2026-11-12" and a["days_away"] == 3 and a["buy"] == ["SWING"] and not a["held"] and a["name"] == "A Inc"
    assert out["items"][0]["held"] and out["items"][0]["stale"] and out["items"][1]["watched"]
    assert out["checked"] == 6 and out["no_date"] == 2 and out["stale"] == 1       # D has only a past date, E has none


def test_nothing_is_fetched_and_odd_values_are_skipped():
    calls = []

    def read(t):
        calls.append(t)
        return {"stored_at": NOW, "data": [None, 5, "bad-date"]} if t == "X" else None
    out = ec.upcoming([{"ticker": "X"}, {"ticker": "Y"}, {"ticker": None}], read, TODAY, NOW)
    assert out["items"] == [] and out["no_date"] == 2 and sorted(calls) == ["X", "Y"]


def test_service_reads_the_stored_dates_and_writes_nothing(tmp_path):
    from terminal.cache import FileCache
    from terminal.qsf.service import QSF
    svc = QSF.__new__(QSF)
    svc.base, svc.dir, svc.cache = tmp_path, tmp_path, FileCache(tmp_path / "cache")
    svc.now = lambda: datetime(2026, 11, 9, 1, tzinfo=timezone.utc)          # 10:00 KST, 20:00 ET the day before
    svc.cache.write("earn:005930.KS", ["2026-11-20"])
    svc.cache.write("earn:035720.KQ", ["2026-11-10"])
    svc.cache.write("earn:AAPL", ["2026-11-10"])
    (tmp_path / "latest_KR.json").write_text(json.dumps({"status": "REAL", "session": "2026-11-06", "rows": [{"ticker": "005930"}, {"ticker": "035720"}]}), encoding="utf-8")
    svc._high_risk = lambda m: {"session": None, "codes": set()}
    svc._filing_marks = lambda m: {"session": None, "financing": set(), "buyback": set(), "known": set()}

    class Term:
        def _book(self, market):
            raise OSError("no journal")

        def watchlist(self):
            return ["AAPL", "005930"]
    svc._terminal = Term()
    before = sorted((p.name, p.read_bytes()) for p in (tmp_path / "cache").iterdir())
    out = svc.earnings_upcoming("KR", 14)
    assert out["today"] == "2026-11-09" and [i["ticker"] for i in out["items"]] == ["035720", "005930"] and out["items"][1]["watched"]
    assert sorted((p.name, p.read_bytes()) for p in (tmp_path / "cache").iterdir()) == before
    assert svc.earnings_upcoming("US", 14)["status"] == "UNAVAILABLE"


def test_the_route_checks_days():
    from terminal.server import routes

    class Q:
        def earnings_upcoming(self, market, days):
            return {"market": market, "days": days}

    class T:
        qsf = Q()
    fn = routes(T())[("GET", "/api/qsf/earnings")]
    assert fn({"market": "KR"}, {}) == {"market": "KR", "days": 14} and fn({"days": "30"}, {})["days"] == 30
    for bad in ("0", "61", "x", "1.5"):
        with pytest.raises(ValueError):
            fn({"days": bad}, {})
