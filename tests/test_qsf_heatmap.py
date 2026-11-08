"""Market map: sector, market value, price change and score per scanned stock; a missing value stays missing."""
import pytest

from terminal.cache import FileCache
from terminal.qsf.service import QSF

DAYS = [f"2026-10-{d:02d}" for d in range(1, 31)] + ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]


def svc(tmp_path, market, rows, bars, shares=None):
    s = QSF.__new__(QSF)
    s.base, s.dir, s.cache = tmp_path, tmp_path, FileCache(tmp_path / "cache")
    s.screen_rows = lambda m: {"status": "REAL", "session": "2026-11-06", "model_version": "V", "rows": rows}
    s._scan_loader = lambda m: (lambda t: bars.get(t, []))
    s._krx_shares = lambda day: shares or {}
    return s


def closes(vals):
    return [{"date": d, "close": v} for d, v in zip(DAYS[-len(vals):], vals)]


def test_us_change_cap_and_missing(tmp_path):
    rows = [{"ticker": t, "name": t, "strategy": st, "score": 70.0, "sector": "Technology", "band": "B", "band_label": "b"} for t in ("A", "B", "C") for st in ("SWING", "LONG_TERM")]
    bars = {"A": closes([100.0] * 20 + [110.0, 121.0]), "B": closes([50.0, 55.0])[:1], "C": closes([10.0] * 30)}
    bars["B"] = [{"date": "2026-11-05", "close": 50.0}]                       # no bar on the scan day: stale, so no change
    s = svc(tmp_path, "US", rows, bars)
    s.cache.write("info:A", {"marketCap": 2e12})
    s.cache.write("info:C", {"marketCap": 0})
    d = s._heatmap("US", "SWING")
    by = {i["ticker"]: i for i in d["items"]}
    assert len(d["items"]) == 3 and d["without_cap"] == ["B", "C"]
    assert by["A"]["market_cap"] == 2e12 and by["A"]["change"]["1d"] == pytest.approx(0.1) and by["A"]["change"]["5d"] == pytest.approx(0.21)
    assert by["A"]["change"]["1m"] == pytest.approx(0.21)
    assert by["B"]["change"] == {"1d": None, "5d": None, "1m": None} and by["C"]["change"]["1m"] == 0.0


def test_korea_cap_is_listed_shares_times_close(tmp_path):
    rows = [{"ticker": "005930", "name": "삼성전자", "strategy": "SWING", "score": 44.0, "sector": "통신 및 방송 장비 제조업"},
            {"ticker": "000660", "name": "SK하이닉스", "strategy": "SWING", "score": 50.0, "sector": "반도체 제조업"}]
    s = svc(tmp_path, "KR", rows, {"005930": closes([90000.0, 100000.0]), "000660": closes([1.0, 2.0])}, {"005930": 5e9})
    d = s._heatmap("KR", "SWING")
    assert d["items"][0]["market_cap"] == 5e14 and d["without_cap"] == ["000660"]


def test_bad_strategy_and_no_scan(tmp_path):
    s = svc(tmp_path, "US", [], {})
    with pytest.raises(ValueError):
        s.heatmap("US", "DAY")
    s.screen_rows = lambda m: {"status": "UNAVAILABLE", "reason": "NO_SCAN"}
    assert s._heatmap("US", "SWING")["status"] == "UNAVAILABLE"
