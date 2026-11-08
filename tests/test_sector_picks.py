"""Sector picks: the top-3 rule of the tracked picks, inside one sector fund's stocks, read from the scan as recorded."""
import pytest

from terminal.qsf import sector_picks as sp


def row(t, strategy, score, sector, name=None, session="2026-11-06", **kw):
    return {"ticker": t, "name": name or t, "strategy": strategy, "score": score, "sector": sector, "industry": sector, "data_date": session,
            "actionability": kw.pop("actionability", "ACTIONABLE"), "band": kw.pop("band", "HOLD_WATCH"), "gates": [], **kw}


def latest(rows):
    return {"status": "REAL", "session": "2026-11-06", "model_version": "QSF-1.1.7", "rows": rows}


def test_us_top3_follows_tracked_rule():
    rows = [row("A", "SWING", 60, "Technology"), row("B", "SWING", 70, "Technology"), row("C", "SWING", 65, "Technology"),
            row("D", "SWING", 90, "Technology", actionability="INSUFFICIENT_DATA"), row("E", "SWING", 99, "Energy"),
            row("F", "SWING", 80, "Technology", session="2026-11-05"), row("G", "SWING", 50, "Technology"), row("H", "SWING", None, "Technology"),
            row("B", "LONG_TERM", 75, "Technology", band="BUY_CANDIDATE")]
    d = sp.picks(latest(rows), "US", "XLK")
    s = d["strategies"]["SWING"]
    assert [p["ticker"] for p in s["top"]] == ["B", "C", "A"] and s["ranked"] == 4 and s["n"] == 7
    assert d["strategies"]["LONG_TERM"]["buy_candidates"] == 1 and d["strategies"]["LONG_TERM"]["top"][0]["rank"] == 1


def test_kr_matches_industry_and_named_holding_companies():
    rows = [row("105560", "SWING", 50, "기타 금융업", "KB금융"), row("055550", "SWING", 49, "기타 금융업", "신한지주"),
            row("003550", "SWING", 70, "기타 금융업", "LG"), row("071050", "SWING", 60, "기타 금융업", "한국금융지주"),
            row("024110", "SWING", 40, "은행 및 저축기관", "기업은행")]
    bank = [p["ticker"] for p in sp.picks(latest(rows), "KR", "091170.KS")["strategies"]["SWING"]["top"]]
    assert bank == ["105560", "055550", "024110"]                       # LG and the securities holding company are not banks
    assert [p["ticker"] for p in sp.picks(latest(rows), "KR", "102970.KS")["strategies"]["SWING"]["top"]] == ["071050"]
    assert "근사치" in sp.rule_text("KR", "091170.KS")


def test_unknown_fund_and_missing_scan():
    with pytest.raises(ValueError):
        sp.picks(latest([]), "US", "QQQ")
    assert sp.picks({"status": "UNAVAILABLE", "rows": []}, "KR", "091160.KS")["status"] == "UNAVAILABLE"


def test_every_rotation_fund_has_a_pick_rule():
    from terminal.services import Terminal
    from terminal.qsf import sector_picks as sp
    for market, (_, _, funds) in Terminal.ROTATION.items():
        for sym, _ in funds:
            assert sp.rule_text(market, sym), (market, sym)
    from terminal import kr_etf_holdings as kh
    assert set(kh.FUNDS) <= {sp.fund_code(s) for s, _ in Terminal.ROTATION["KR"][2]}
