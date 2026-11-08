"""KODEX holdings snapshots: parse the feed, stop at the first refusal without saving, and feed sector picks."""
from datetime import date, datetime, timezone

import pytest

from terminal import kr_etf_holdings as kh
from terminal.qsf import sector_picks as sp

NOW = lambda: datetime(2026, 11, 9, 1, 0, tzinfo=timezone.utc)      # noqa: E731


def doc(symbol, codes):
    return {"info": {"stkCd": symbol}, "pdf": {"gijunYMD": "20261106", "totalCnt": str(len(codes)),
            "list": [{"itmNo": "KRD010010001", "secNm": "원화예금", "ratio": None}, {"itmNo": "KR4101VC0004", "secNm": "선물", "ratio": "1"}] + [{"itmNo": c, "secNm": f"n{c}", "ratio": "10.5"} for c in codes]}}


def feed(blocked_at=None):
    calls = []
    by_id = {fid: sym for sym, (fid, _) in kh.FUNDS.items()}

    def get(url):
        fid = url.rsplit("/", 1)[1][:-3]
        calls.append(fid)
        if blocked_at and len(calls) == blocked_at:
            raise kh.Blocked("HTTP 429")
        return doc(by_id[fid], ["000660", "005930"] if by_id[fid] == "091160" else ["111111"])
    return get, calls


def test_parse_drops_cash_and_checks_the_fund():
    got = kh.parse(doc("091160", ["000660"]), "091160")
    assert got["holdings"] == [{"code": "000660", "name": "n000660", "weight_pct": 10.5}] and got["as_of"] == "2026-11-06"
    with pytest.raises(ValueError):
        kh.parse(doc("091170", ["000660"]), "091160")
    with pytest.raises(ValueError):
        kh.parse(doc("091160", []), "091160")


def test_refusal_stops_at_once_and_keeps_nothing_partial(tmp_path):
    get, calls = feed(blocked_at=3)
    res = kh.refresh(tmp_path, get=get, pause=0, now=NOW)
    assert res["status"] == "BLOCKED" and len(calls) == 3 and res["fetched"] == 2
    assert kh.load(tmp_path) is None and kh.status(tmp_path) == {"status": "NONE"}


def test_full_refresh_saves_and_serves_members(tmp_path):
    get, calls = feed()
    assert kh.refresh(tmp_path, get=get, pause=0, now=NOW)["status"] == "OK" and len(calls) == len(kh.FUNDS)
    m = kh.members(tmp_path, "091160")
    assert m["codes"] == ["000660", "005930"] and m["fund"] == "KODEX 반도체"
    assert kh.status(tmp_path, date(2026, 11, 20))["status"] == "OK"
    assert kh.status(tmp_path, date(2027, 7, 1))["status"] == "STALE"
    get2, _ = feed(blocked_at=1)
    kh.refresh(tmp_path, get=get2, pause=0, now=NOW)
    assert kh.members(tmp_path, "091160")["codes"] == ["000660", "005930"]          # a refused refresh keeps the old snapshot


def test_picks_use_holdings_when_given(tmp_path):
    rows = [{"ticker": t, "name": t, "strategy": "SWING", "score": s, "sector": "기술", "industry": ind, "data_date": "2026-11-06",
             "actionability": "ACTIONABLE", "band": "HOLD_WATCH", "gates": []}
            for t, s, ind in [("000660", 50, "반도체 제조업"), ("005930", 60, "통신 및 방송 장비 제조업"), ("042700", 70, "특수 목적용 기계 제조업")]]
    latest = {"status": "REAL", "session": "2026-11-06", "rows": rows}
    get, _ = feed()
    kh.refresh(tmp_path, get=get, pause=0, now=NOW)
    d = sp.picks(latest, "KR", "091160.KS", kh.members(tmp_path, "091160"))
    assert [p["ticker"] for p in d["strategies"]["SWING"]["top"]] == ["005930", "000660"] and d["basis_kind"] == "HOLDINGS"
    assert "실제 보유 종목" in d["rule"]
    approx = sp.picks(latest, "KR", "091160.KS")
    assert approx["basis_kind"] == "MATCH" and [p["ticker"] for p in approx["strategies"]["SWING"]["top"]] == ["042700", "000660"]
