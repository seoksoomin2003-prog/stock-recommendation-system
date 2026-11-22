"""QSF-1.4.1 (user decision 2026-11-17, reports/QSF_INPUTS_3_2026_11_17.md): the whole Korean filing list, a US share count that
matches the price's basis, and the company's SEC number in new US records.  No network."""
from pathlib import Path

import pytest

from terminal.cache import FileCache
from terminal.qsf import config, events, fundamentals as f, ledger as lg
from terminal.qsf.service import QSF

ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-11-13"


# ---------------------------------------------------------------------- the whole Korean filing list
def dart(pages, status="000"):
    """A stand-in for the client's request: ``pages`` are lists of rows; notes every call."""
    calls = []

    class Reply:
        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

    def get(endpoint, **params):
        calls.append(params)
        n = params["page_no"]
        if status != "000":
            return Reply({"status": status, "message": "x"})
        return Reply({"status": "000", "page_no": n, "total_page": len(pages), "list": pages[n - 1]})
    return get, calls


def row(name, day):
    return {"report_nm": name, "rcept_dt": day, "rcept_no": day + "000001"}


def test_every_page_of_the_year_is_read():
    filler = [row("증권발행실적보고서", "20261110")] * 100
    get, calls = dart([filler, filler, [row("유상증자결정", "20261001")]])
    got = events.kr_filings(get, "00126380", "20251113", "20261113")
    assert [c["page_no"] for c in calls] == [1, 2, 3] and all(c["page_count"] == 100 and c["corp_code"] == "00126380" for c in calls)
    assert len(got["rows"]) == 201 and got["complete"] is True and got["pages"] == 3
    seen = events.classify_kr_list(got, AS_OF)
    first_page_only = events.classify_kr(filler, AS_OF)                    # what was scored before: the financing decision was on page 3
    assert seen["status"] == "REAL" and [x["label"] for x in seen["negative"]] and not first_page_only["negative"]


def test_no_filings_is_an_empty_list_and_a_refusal_is_an_error():
    get, calls = dart([], status="013")
    assert events.kr_filings(get, "1", "20251113", "20261113") == {"rows": [], "complete": True, "pages": 1, "total_pages": 1} and len(calls) == 1
    get, _ = dart([], status="020")                                        # request limit: it used to read as "no filings"
    with pytest.raises(RuntimeError, match="DART_STATUS_020"):
        events.kr_filings(get, "1", "20251113", "20261113")


def test_a_list_too_long_to_read_whole_is_unavailable_not_clean():
    get, calls = dart([[row("증권발행실적보고서", "20261110")] * 100] * 5)
    got = events.kr_filings(get, "1", "20251113", "20261113", max_pages=2)
    assert len(calls) == 2 and got["complete"] is False and got["pages"] == 2 and got["total_pages"] == 5
    ev = events.classify_kr_list(got, AS_OF)
    assert ev["status"] == "UNAVAILABLE" and "365일을 덮지 못합니다" in ev["reason"] and "5쪽 중 2쪽" in ev["reason"]
    assert events.classify_kr_list(None, AS_OF) == {"status": "UNAVAILABLE", "reason": "DART 공시 조회 실패"}
    assert events.KR_LIST_PAGES == 60


def test_the_scan_and_the_stock_screen_read_the_whole_list():
    src = (ROOT / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")
    assert src.count("events.kr_filings(self.dart._get, corp, bgn,") == 2 and src.count('f"krlist2:{corp}"') == 3 and 'f"krlist:{corp}"' not in src          # the scan, the stock screen, the earnings-date estimate
    assert 'ev = events.classify_kr_list(rep["data"], as_of)' in src


# ---------------------------------------------------------------------- a share count on the price's basis
def rows(vals, last=2025):
    first = last - len(vals) + 1
    return [{"end": f"{first + i}-12-31", "val": v, "filed": f"{first + i + 1}-02-15"} for i, v in enumerate(vals) if v is not None]


def annual():
    return {"revenue": rows([80.0, 90.0, 100.0, 120.0]), "net_income": rows([8.0, 9.0, 10.0, 12.0]), "equity": rows([40.0, 45.0, 50.0, 60.0]), "assets": rows([100.0] * 4),
            "eps": rows([0.8, 0.9, 1.0, 1.2]), "shares_avg": rows([10.0] * 4)}


def test_the_price_basis_check():
    assert f.price_basis_moved({"currentPrice": 1000.0}, 100.0) and f.price_basis_moved({"regularMarketPrice": 100.0}, 1000.0)     # 10:1 either way
    assert f.price_basis_moved({"currentPrice": 150.0}, 100.0)                                                                     # a 3:2 split
    assert not f.price_basis_moved({"currentPrice": 100.0}, 120.0) and not f.price_basis_moved({"currentPrice": 100.0}, 80.0)      # a week's ordinary move
    assert not f.price_basis_moved({}, 100.0) and not f.price_basis_moved({"currentPrice": 100.0}, None)                           # nothing to check: as before


def test_an_unknown_count_gives_no_market_value_and_no_per():
    known = f.metrics(annual(), 10.0, "2026-06-01", shares=10.0)
    assert known["market_cap"] == pytest.approx(100.0) and known["pe"] is not None and known["pb"] is not None
    unknown = f.metrics(annual(), 1.0, "2026-06-01", shares=10.0, count_unknown=True)        # the price after a 10:1 split, every count from before it
    assert unknown["market_cap"] is None and unknown["pe"] is None and unknown["pb"] is None and unknown["eps"] is None and unknown["fcf_yield"] is None
    assert unknown["roe"] == known["roe"] and unknown["rev_growth"] == known["rev_growth"]  # what does not need a share count is untouched


class Src:
    def __init__(self, fresh=None, fail=False):
        self.fresh, self.fail, self.asked = fresh, fail, 0

    def yahoo_info(self, ticker):
        self.asked += 1
        if self.fail:
            raise OSError("no network")
        return self.fresh


def service(tmp_path, src):
    q = QSF.__new__(QSF)
    q.cache, q.src = FileCache(tmp_path), src
    return q


def test_a_record_from_before_a_split_is_asked_again(tmp_path):
    old = {"sharesOutstanding": 10.0, "currentPrice": 1000.0, "marketCap": 10_000.0}
    new = {"sharesOutstanding": 100.0, "currentPrice": 100.0, "marketCap": 10_000.0}
    q = service(tmp_path, Src(new))
    q.cache.write("info:XYZ", old)                                         # stored last Thursday; within its 7 days
    assert q._us_info("XYZ", 990.0) == (old, False) and q.src.asked == 0   # an ordinary day: the stored record, no request
    assert q._us_info("XYZ", 100.0) == (new, False) and q.src.asked == 1   # the bar is on the new basis: asked again, and it has caught up
    assert q._us_info("XYZ", 101.0) == (new, False) and q.src.asked == 1   # the fresh record is kept as any other


def test_when_the_record_cannot_be_refreshed_the_count_is_not_used(tmp_path):
    old = {"sharesOutstanding": 10.0, "currentPrice": 1000.0, "marketCap": 10_000.0}
    q = service(tmp_path, Src(fail=True))
    q.cache.write("info:XYZ", old)
    info, moved = q._us_info("XYZ", 100.0)
    assert moved is True and info == old and q.src.asked == 1
    behind = service(tmp_path / "b", Src(old))                             # the provider itself still serves the old record
    behind.cache.write("info:XYZ", old)
    assert behind._us_info("XYZ", 100.0)[1] is True
    src = (ROOT / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")
    assert 'info, moved = self._us_info(ticker, bars[-1]["close"])' in src and "count_unknown=moved)" in src


# ---------------------------------------------------------------------- the company, whatever its ticker becomes
def card(**more):
    return {"market": "US", "ticker": "XYZ", "strategy": "SWING", "domains": {}, "factors": [], "levels": {}, **more}


def test_a_us_record_carries_the_sec_number_and_a_korean_one_is_as_before():
    assert lg.snapshot(card(cik="0000320193"))["cik"] == "0000320193"
    assert "cik" not in lg.snapshot(card()) and "cik" not in lg.snapshot(card(market="KR", ticker="005930", cik=None))
    src = (ROOT / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")
    assert 'out["cik"] = ctx["fund"]["cik"]' in src


def test_the_version_names_the_input_change():
    assert config.MODEL_VERSION == "QSF-1.5.1" and (ROOT / "reports" / "QSF_INPUTS_3_2026_11_17.md").exists()
