"""QSF-1.3.1: the next earnings date estimated from past dates, its label and the wider block it gets.  All offline."""
from datetime import datetime, timezone

import pytest

from terminal.qsf import config, earnings_estimate as ee, engine, factors
from terminal.qsf.service import QSF

NOW = datetime(2026, 11, 11, 3, 0, tzinfo=timezone.utc)
QUARTERS = ["2025-08-05", "2025-11-06", "2026-02-05", "2026-05-07", "2026-08-06"]


def test_the_estimate_is_the_same_quarter_a_year_on_and_stays_until_the_event_comes():
    assert ee.next_estimate(QUARTERS, "2026-10-20") == {"date": "2026-11-06", "from": "2025-11-06", "overdue": False}
    assert ee.next_estimate(QUARTERS, "2026-11-10") == {"date": "2026-11-06", "from": "2025-11-06", "overdue": True}       # the day passed, no event yet
    assert ee.next_estimate(QUARTERS + ["2026-11-09"], "2026-11-10") == {"date": "2027-02-05", "from": "2026-02-05", "overdue": False}     # the event came: on to the next
    assert ee.next_estimate(QUARTERS, "2026-11-21")["date"] == "2027-02-05"                                               # two weeks late and silent: given up
    assert ee.next_estimate(["2024-02-29"], "2024-12-01") == {"date": "2025-02-28", "from": "2024-02-29", "overdue": False}


def test_no_estimate_without_recent_events_or_from_a_monthly_pattern():
    assert ee.next_estimate([], "2026-11-10") is None and ee.next_estimate(["2024-05-01"], "2026-11-10") is None
    monthly = [f"2026-{m:02d}-03" for m in range(1, 11)]
    assert ee.next_estimate(monthly, "2026-11-10") is None                         # ten events in the window is not a quarterly company
    assert ee.next_estimate(["2026-11-30"], "2026-11-10") is None                  # a date after the as-of day is not a past event


def test_us_dates_are_8k_filings_with_the_results_item():
    filings = [{"form": "8-K", "date": "2026-08-01", "items": "2.02,9.01"}, {"form": "8-K", "date": "2026-08-20", "items": "5.02"}, {"form": "4", "date": "2026-08-03", "items": ""},
               {"form": "8-K", "date": "2026-05-02", "items": "7.01, 2.02"}, {"form": "8-K/A", "date": "2026-05-09", "items": "2.02"}, {"form": "8-K", "date": "2026-02-01", "items": "12.02"}]
    assert ee.us_result_dates(filings) == ["2026-05-02", "2026-08-01"] and ee.us_result_dates(None) == []


def test_korean_dates_prefer_the_consolidated_preliminary_title_and_fall_back_to_periodic_reports():
    rows = [{"report_nm": "연결재무제표기준영업(잠정)실적(공정공시)", "rcept_dt": "20260806"}, {"report_nm": "영업(잠정)실적(공정공시)", "rcept_dt": "20260903"},
            {"report_nm": "[기재정정]연결재무제표기준영업(잠정)실적(공정공시)", "rcept_dt": "20260810"}, {"report_nm": "분기보고서 (2026.03)", "rcept_dt": "20260515"}, {"report_nm": "", "rcept_dt": ""}]
    assert ee.kr_result_dates(rows) == {"dates": ["2026-08-06"], "kind": "PRELIMINARY"}          # the plain title (monthly sales for some) and the correction are left out
    assert ee.kr_result_dates(rows[1:2]) == {"dates": ["2026-09-03"], "kind": "PRELIMINARY"}
    periodic = [{"report_nm": "반기보고서 (2026.06)", "rcept_dt": "20260814"}, {"report_nm": "사업보고서 (2025.12)", "rcept_dt": "20260318"}, {"report_nm": "주요사항보고서(유상증자결정)", "rcept_dt": "20260701"}]
    assert ee.kr_result_dates(periodic) == {"dates": ["2026-03-18", "2026-08-14"], "kind": "PERIODIC"} and ee.kr_result_dates([]) == {"dates": [], "kind": "PERIODIC"}
    monthly = [{"report_nm": "영업(잠정)실적(공정공시)", "rcept_dt": f"2026{m:02d}10"} for m in range(1, 11)] + periodic
    assert ee.kr_result_dates(monthly, "2026-11-10") == {"dates": ["2026-03-18", "2026-08-14"], "kind": "PERIODIC"}        # monthly figures under the same title: the periodic reports are read
    assert ee.kr_result_dates(monthly)["kind"] == "PRELIMINARY" and ee.kr_result_dates(rows, "2026-11-10")["kind"] == "PRELIMINARY"


# ---------------------------------------------------------------------- the service
class Src:
    def __init__(self, calendar=None, filings=None):
        self.calendar, self.filings = calendar or [], filings

    def yahoo_earnings_dates(self, t):
        return self.calendar

    def sec_submissions(self, cik):
        f = self.filings or [("8-K", d, "2.02") for d in QUARTERS]
        return {"name": "Test Co", "sic": "7372", "filings": {"recent": {"form": [x[0] for x in f], "filingDate": [x[1] for x in f], "items": [x[2] for x in f],
                                                                         "accessionNumber": [f"1-{n}" for n in range(len(f))], "primaryDocument": ["d.htm"] * len(f)}}}


def test_a_calendar_date_stands_and_a_missing_one_is_estimated_from_sec_filings(tmp_path):
    cal = QSF(tmp_path / "a", src=Src(calendar=["2026-08-06", "2026-11-12"]), now=lambda: NOW)._earnings("AAA", "US", "2026-11-10", code="AAA", cik="0000000001")
    assert cal["date"] == "2026-11-12" and cal["sessions"] == 2 and "basis" not in cal
    est = QSF(tmp_path / "b", src=Src(calendar=["2026-08-06"]), now=lambda: NOW)._earnings("AAA", "US", "2026-10-28", code="AAA", cik="0000000001")
    assert est == {"date": "2026-11-06", "sessions": 7, "basis": "ESTIMATE", "from": "2025-11-06", "overdue": False, "source": "SEC 8-K 실적 공시일(항목 2.02) 기준 추정"}
    late = QSF(tmp_path / "c", src=Src(), now=lambda: NOW)._earnings("AAA", "US", "2026-11-10", code="AAA", cik="0000000001")
    assert late["overdue"] is True and late["sessions"] == 0 and late["basis"] == "ESTIMATE"
    assert QSF(tmp_path / "d", src=Src(), now=lambda: NOW)._earnings("AAA", "US", "2026-11-10", code="AAA", cik=None) == {"sessions": None}
    assert QSF(tmp_path / "e", src=Src(filings=[("4", "2026-08-01", "")]), now=lambda: NOW)._earnings("AAA", "US", "2026-11-10", cik="0000000001") == {"sessions": None}


class Dart:
    configured = True

    def __init__(self, status="000", prelim=True):
        self.status, self.prelim, self.calls = status, prelim, []

    def _get(self, endpoint, **params):
        self.calls.append(params)
        rows = []
        if params.get("pblntf_detail_ty") == "I002" and self.prelim:
            rows = [{"report_nm": "연결재무제표기준영업(잠정)실적(공정공시)", "rcept_dt": d.replace("-", "")} for d in QUARTERS]
        if params.get("pblntf_ty") == "A":
            rows = [{"report_nm": "분기보고서 (2025.09)", "rcept_dt": "20251114"}, {"report_nm": "사업보고서 (2025.12)", "rcept_dt": "20260318"}]
        body = {"status": self.status if rows or self.status != "000" else "013", "list": rows}

        class R:
            def json(self_inner):
                return body
        return R()


def kr(tmp_path, dart):
    q = QSF(tmp_path, src=Src(), now=lambda: NOW, dart=dart)
    q._corp_code = lambda code: "00000001"
    return q


def test_korea_reads_two_dart_lists_once_a_week_and_sees_the_new_disclosure_in_the_daily_list(tmp_path):
    d = Dart()
    q = kr(tmp_path, d)
    est = q._earnings("005930.KS", "KR", "2026-10-28", code="005930")
    assert est["date"] == "2026-11-06" and est["basis"] == "ESTIMATE" and est["source"] == "DART 잠정실적 공시일 기준 추정" and est["sessions"] == 7
    assert len(d.calls) == 2 and {c.get("pblntf_detail_ty") or c.get("pblntf_ty") for c in d.calls} == {"I002", "A"}
    q._earnings("005930.KS", "KR", "2026-10-29", code="005930")
    assert len(d.calls) == 2                                                             # kept for a week
    q.cache.write("krlist:00000001", [{"report_nm": "연결재무제표기준영업(잠정)실적(공정공시)", "rcept_dt": "20261105"}])
    assert q._earnings("005930.KS", "KR", "2026-11-06", code="005930")["date"] == "2027-02-05"       # the day's filing list shows the event came


def test_korea_without_preliminary_results_uses_periodic_reports_and_a_failed_answer_is_not_kept(tmp_path):
    q = kr(tmp_path / "a", Dart(prelim=False))
    est = q._earnings("000020.KS", "KR", "2026-11-05", code="000020")
    assert est["date"] == "2026-11-14" and est["source"] == "DART 정기보고서 제출일 기준 추정"
    bad = Dart(status="020")
    q2 = kr(tmp_path / "b", bad)
    assert q2._earnings("000020.KS", "KR", "2026-11-05", code="000020") == {"sessions": None} and q2.cache.read("krearn:00000001") is None
    assert kr(tmp_path / "c", type("NoKey", (), {"configured": False})())._earnings("000020.KS", "KR", "2026-11-05", code="000020") == {"sessions": None}


# ---------------------------------------------------------------------- the rules that read it
def gates(earn):
    tech = {"date": "2026-11-10", "n": 300, "close": 100.0, "adv_value": 1e12, "last_volume": 1.0, "max_move_5": 0.01}
    return [g for g in engine.hard_gates({"market": "US", "tech": tech, "earnings": earn}, "SWING") if g["code"] == "EARNINGS_IMMINENT"]


def test_an_estimated_date_blocks_a_swing_entry_five_sessions_ahead_and_while_overdue():
    assert config.EARNINGS_BLOCK_SESSIONS == 2 and config.EARNINGS_BLOCK_SESSIONS_ESTIMATE == 5
    assert gates({"date": "2026-11-13", "sessions": 3}) == [] and len(gates({"date": "2026-11-12", "sessions": 2})) == 1            # a calendar date: as before
    est = {"date": "2026-11-17", "basis": "ESTIMATE", "from": "2025-11-17"}
    assert len(gates({**est, "sessions": 5, "overdue": False})) == 1 and "추정일" in gates({**est, "sessions": 5, "overdue": False})[0]["text"]
    assert gates({**est, "sessions": 6, "overdue": False}) == []
    assert "아직 공시가 없어" in gates({**est, "sessions": 0, "overdue": True})[0]["text"]
    long_ = engine.hard_gates({"market": "US", "tech": {"date": "2026-11-10", "n": 300, "close": 100.0, "adv_value": 1e12, "last_volume": 1.0}, "earnings": {**est, "sessions": 1, "overdue": False}}, "LONG_TERM")
    assert all(g["code"] != "EARNINGS_IMMINENT" for g in long_)                              # the block is for swing entries only, as before


def test_the_factor_says_when_its_date_is_an_estimate():
    c = {"tech": {"date": "2026-11-10"}, "earnings": {"date": "2026-11-20", "sessions": 8, "basis": "ESTIMATE", "from": "2025-11-20", "overdue": False, "source": "SEC 8-K 실적 공시일(항목 2.02) 기준 추정"}}
    f = factors.earnings_calendar(c)
    assert f["status"] == "REAL" and "추정" in f["explanation"] and f["raw"]["basis"] == "ESTIMATE" and f["raw"]["from"] == "2025-11-20" and f["normalized"] == pytest.approx((8 - 2) / 13)
    late = factors.earnings_calendar({"tech": {"date": "2026-11-10"}, "earnings": {"date": "2026-11-06", "sessions": 0, "basis": "ESTIMATE", "from": "2025-11-06", "overdue": True}})
    assert late["normalized"] == 0.0 and "아직 공시 없음" in late["explanation"]
    plain = factors.earnings_calendar({"tech": {"date": "2026-11-10"}, "earnings": {"date": "2026-11-20", "sessions": 8}})
    assert "추정" not in plain["explanation"] and "basis" not in plain["raw"]
    assert factors.earnings_calendar({"tech": {"date": "2026-11-10"}, "earnings": {"sessions": None}})["status"] == "MISSING"
