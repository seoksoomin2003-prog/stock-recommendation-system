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


# ---------------------------------------------------------------- peers: grades within the industry, ratios only from live-version records
from terminal.qsf import config                     # noqa: E402
from terminal.qsf.ledger import Ledger               # noqa: E402


def peer_svc(tmp_path, n=8):
    rows = []
    for i in range(n):
        t = f"T{i}"
        for st in ("SWING", "LONG_TERM"):
            rows.append({"ticker": t, "name": t, "strategy": st, "score": 40.0 + 5 * i, "sector": "Technology" if i < n - 1 else "Energy", "band_label": "b",
                         "domains": {"TECHNICAL": 10.0 * i, "FUNDAMENTAL": None if i == 0 else 50.0, "RISK": 50.0, "EVENTS": 50.0}})
    s = svc(tmp_path, "US", rows, {})
    s.ledger = Ledger(tmp_path)
    s._stamp = lambda keys: (1,)
    s.heatmap = lambda m, st: {"items": [{"ticker": f"T{i}", "market_cap": 1e9 * (i + 1), "change": {"1m": 0.01 * i}} for i in range(n)]}
    for i in range(n):
        s.cache.write(f"info:T{i}", {"industry": "Semis" if i < 3 else "Software"})
    return s


def card(t, version, pe, day):
    return {"ticker": t, "strategy": "LONG_TERM", "model_version": version, "data_date": day, "benchmark": "SPY", "entry_session": "2026-11-10", "domains": {}, "levels": {},
            "factors": [{"factor": "valuation", "status": "REAL", "raw": {"pe": pe, "pb": float("nan"), "fcf_yield": None}},
                        {"factor": "business_quality", "status": "MISSING", "raw": {"op_margin": 0.3}}]}


def test_peers_group_grades_and_live_version_ratios(tmp_path):
    s = peer_svc(tmp_path)
    d = s._peers("T6", "US")
    assert d["basis"] == "업종" and d["group"] == "Technology" and len(d["peers"]) == 7 and d["ratio_session"] is None   # Semis has 3 < 6: the sector
    g = d["grades"]["SWING"]
    assert g["SCORE"]["grade"] == "A" and g["SCORE"]["n"] == 7 and g["TECHNICAL"]["percentile"] == pytest.approx(13 / 14)
    assert g["FUNDAMENTAL"]["grade"] == "C" and g["FUNDAMENTAL"]["n"] == 6                       # T0 has none: left out, never 0
    assert d["peers"][0]["ticker"] == "T6" and d["peers"][0]["ratios"] is None
    Ledger(tmp_path).append("2026-11-06", "US", [card("T6", "QSF-OLD", 10.0, "2026-11-06")])
    s._memos = {}
    assert s._peers("T6", "US")["ratio_session"] is None                                            # an older model's record is not used
    Ledger(tmp_path).append("2026-11-09", "US", [card("T6", config.MODEL_VERSION, 25.0, "2026-11-09")])
    s._memos = {}
    r = s._peers("T6", "US")
    assert r["ratio_session"] == "2026-11-09" and r["peers"][0]["ratios"] == {"pe": 25.0, "pb": None, "fcf_yield": None, "op_margin": None, "roe": None}
    assert s._peers("ZZ", "US")["status"] == "NOT_SCANNED"


def test_a_small_group_gets_no_grade(tmp_path):
    s = peer_svc(tmp_path, n=4)
    g = s._peers("T1", "US")["grades"]["LONG_TERM"]["SCORE"]
    assert g["grade"] is None and g["n"] == 3 and s.grade(0.8) == "A" and s.grade(0.19) == "F"
