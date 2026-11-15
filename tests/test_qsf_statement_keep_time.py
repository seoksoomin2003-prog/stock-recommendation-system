"""How long extracted annual statements are kept: US one day (20 hours), Korea seven days.  No network."""
from datetime import datetime, timezone

import pytest

from terminal.qsf import service
from terminal.qsf.service import QSF

NOW = datetime(2026, 11, 11, 22, 0, tzinfo=timezone.utc)
HOUR = 3600.0


def _rows(vals, last=2025):
    first = last - len(vals) + 1
    return [{"end": f"{first + i}-12-31", "val": v, "filed": f"{first + i + 1}-02-15"} for i, v in enumerate(vals)]


class Src:
    def sec_cik(self, t):
        return "0000000001"

    def yahoo_info(self, t):
        return {"longName": "Test Co", "sharesOutstanding": 10.0}


def _us(tmp_path, monkeypatch, annual):
    q = QSF(tmp_path, src=Src(), now=lambda: NOW)
    clock = [1_000_000.0]
    q.cache.clock = lambda: clock[0]
    monkeypatch.setattr(q, "_annual", annual)
    monkeypatch.setattr(q, "_us_subm", lambda cik: {"sic": "7372", "name": "Test Co"})
    return q, clock


def _statement(net_income):
    return {"revenue": _rows([80.0, 90.0, 100.0, 120.0]), "net_income": _rows([8.0, 9.0, 10.0, net_income]), "equity": _rows([40.0, 45.0, 50.0, 60.0]), "assets": _rows([100.0] * 4)}


def test_us_statements_are_read_again_at_the_next_days_run(tmp_path, monkeypatch):
    calls = []

    def annual(ticker, cik):
        calls.append(ticker)
        return _statement(12.0 if len(calls) == 1 else 24.0)          # a new annual report arrived before the second read

    q, clock = _us(tmp_path, monkeypatch, annual)
    bars = [{"date": "2026-11-10", "close": 10.0}]
    first = q._us_fund("AAA", bars, "2026-11-10")
    clock[0] += 2 * HOUR
    assert q._us_fund("AAA", bars, "2026-11-10") == first and len(calls) == 1      # the same day: the stored copy
    clock[0] += 21 * HOUR + 55 * 60                                               # 23 h 55 min after storing: the next morning's run
    second = q._us_fund("AAA", bars, "2026-11-11")
    assert len(calls) == 2 and second != first


def test_a_failed_read_keeps_the_stored_us_statement(tmp_path, monkeypatch):
    calls = []

    def annual(ticker, cik):
        calls.append(ticker)
        if len(calls) > 1:
            raise RuntimeError("SEC HTTP_503")
        return _statement(12.0)

    q, clock = _us(tmp_path, monkeypatch, annual)
    bars = [{"date": "2026-11-10", "close": 10.0}]
    first = q._us_fund("AAA", bars, "2026-11-10")
    clock[0] += 30 * HOUR
    again = q._us_fund("AAA", bars, "2026-11-10")
    # the same figures as before, now with a mark saying that a stored copy stood in for the failed read (2026-11-15)
    mark = again.pop("stale_inputs")
    assert len(calls) == 2 and again == first and again.get("status") != "UNAVAILABLE" and "stale_inputs" not in first
    assert [(x["what"], x["error"], x["age_days"]) for x in mark] == [("SEC 재무제표", "RuntimeError", 1.2)]


def test_korean_statements_keep_seven_days_and_us_one(tmp_path, monkeypatch):
    assert service.TTL["facts"] == 20 * HOUR and service.TTL["kr_facts"] == 7 * 24 * HOUR

    class Dart:
        configured = True

    class Stop(Exception):
        pass

    q = QSF(tmp_path, src=Src(), now=lambda: NOW, dart=Dart())
    seen = {}

    def cached(key, ttl, fetch):
        seen[key.split(":")[0]] = ttl
        raise Stop

    monkeypatch.setattr(q.cache, "cached", cached)
    monkeypatch.setattr(q, "_corp_code", lambda code: "00000001")
    with pytest.raises(Stop):
        q._kr_fund_events("005930", {"industry_class": "NON_FINANCIAL", "yahoo_symbol": "005930.KS"}, [{"date": "2026-11-10", "close": 100.0}], "2026-11-10")
    with pytest.raises(Stop):
        q._us_fund("AAA", [{"date": "2026-11-10", "close": 10.0}], "2026-11-10")
    assert seen == {"krfund3": 7 * 24 * HOUR, "annual4": 20 * HOUR}
