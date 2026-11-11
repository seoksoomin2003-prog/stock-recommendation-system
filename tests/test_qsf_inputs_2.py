"""QSF-1.2.1: the inputs the 2026-11-11 audit left, and the Korean credit factor.  No network."""
from datetime import date, datetime, timezone

import pytest

from terminal.qsf import factors, fundamentals as f, service
from terminal.qsf.service import QSF

AS_OF = "2026-06-01"
NOW = datetime(2026, 11, 11, 3, 0, tzinfo=timezone.utc)


def rows(vals, last=2025, month_day="12-31", **more):
    first = last - len(vals) + 1
    return [{"end": f"{first + i}-{month_day}", "val": v, "filed": f"{first + i + 1}-02-15", **more} for i, v in enumerate(vals) if v is not None]


def us(**debt):
    d = {"revenue": rows([80.0, 90.0, 100.0, 120.0]), "net_income": rows([8.0, 9.0, 10.0, 12.0]), "equity": rows([40.0, 45.0, 50.0, 60.0]), "assets": rows([100.0] * 4),
         "liabilities": rows([60.0, 55.0, 50.0, 40.0]), "cash": rows([5.0] * 4), "ocf": rows([9.0, 10.0, 11.0, 15.0]), "debt_long": [], "debt_short": [], "debt_borrow": []}
    d.update(debt)
    return d


def m(d, **kw):
    return f.metrics(d, 10.0, AS_OF, shares=10.0, **kw)


# ---------------------------------------------------------------------- US debt
def test_debt_is_long_term_debt_its_current_part_and_short_term_borrowings():
    got = m(us(debt_long=rows([20.0] * 4, alias="LongTermDebtNoncurrent"), debt_short=rows([2.0] * 4, alias="LongTermDebtCurrent"), debt_borrow=rows([3.0] * 4, alias="CommercialPaper")))
    assert got["debt_equity"] == pytest.approx(25.0 / 60.0) and got["cash_debt"] == pytest.approx(5.0 / 25.0)


def test_a_long_term_figure_that_holds_the_current_part_is_not_given_it_again():
    got = m(us(debt_long=rows([22.0] * 4, alias="LongTermDebt"), debt_short=rows([2.0] * 4, alias="LongTermDebtCurrent"), debt_borrow=rows([3.0] * 4, alias="ShortTermBorrowings")))
    assert got["debt_equity"] == pytest.approx(25.0 / 60.0)            # 22 already holds the 2
    lease = m(us(debt_long=rows([20.0] * 4, alias="LongTermDebtAndCapitalLeaseObligations"), debt_short=rows([2.0] * 4, alias="LongTermDebtAndCapitalLeaseObligationsCurrent")))
    assert lease["debt_equity"] == pytest.approx(22.0 / 60.0)          # this long-term tag is the noncurrent part: the current part is added


def test_all_current_debt_already_holds_the_borrowings_and_a_total_holds_everything():
    cur = m(us(debt_long=rows([20.0] * 4, alias="LongTermDebtNoncurrent"), debt_short=rows([5.0] * 4, alias="DebtCurrent"), debt_borrow=rows([3.0] * 4, alias="ShortTermBorrowings")))
    assert cur["debt_equity"] == pytest.approx(25.0 / 60.0)
    own = {"debt_long": rows([20.0] * 4, alias="LongTermDebtNoncurrent"), "debt_short": rows([2.0] * 4, alias="LongTermDebtCurrent"), "debt_borrow": rows([3.0] * 4, alias="CommercialPaper")}
    total = m(us(debt_total=rows([30.0] * 4, alias="DebtLongtermAndShorttermCombinedAmount"), **own))
    assert total["debt_equity"] == pytest.approx(30.0 / 60.0) and total["debt_basis"] == "OWN_TOTAL"             # the company's own total stands before the parts
    assert m(us(debt_total=rows([30.0] * 4, alias="DebtLongtermAndShorttermCombinedAmount")))["debt_equity"] == pytest.approx(0.5)
    zero = m(us(debt_total=rows([0.0] * 4, alias="DebtLongtermAndShorttermCombinedAmount"), **own))
    assert zero["debt_equity"] == pytest.approx(25.0 / 60.0)              # a zero total next to positive parts is not a total
    small = m(us(debt_total=rows([0.5] * 4, alias="DebtLongtermAndShorttermCombinedAmount"), **own))
    assert small["debt_equity"] == pytest.approx(25.0 / 60.0)             # nor is a total below its own long-term part
    assert m(us(debt_total=rows([0.0] * 4, alias="DebtLongtermAndShorttermCombinedAmount")))["debt_basis"] == "TOTAL_LIABILITIES"       # a lone zero is not trusted
    none = {"debt_long": rows([0.0] * 4, alias="LongTermDebtNoncurrent")}
    assert m(us(debt_total=rows([0.0] * 4, alias="DebtLongtermAndShorttermCombinedAmount"), **none))["debt_equity"] == 0.0  # the parts say zero too
    old_total = m(us(debt_total=rows([30.0, 30.0, None, None], alias="DebtLongtermAndShorttermCombinedAmount"), **own))
    assert old_total["debt_equity"] == pytest.approx(25.0 / 60.0)         # a total of an older year is not this year's


def test_without_a_borrowings_figure_total_liabilities_stand_in_and_the_basis_says_so():
    got = m(us())
    assert got["debt_equity"] == pytest.approx(40.0 / 60.0) and got["debt_basis"] == "TOTAL_LIABILITIES"
    stopped = m(us(debt_long=rows([20.0, 20.0, None, None], alias="LongTermDebt"), debt_borrow=rows([3.0] * 4, alias="ShortTermBorrowings")))
    assert stopped["debt_basis"] == "TOTAL_LIABILITIES"                  # long-term debt stopped at an amount: the borrowings alone would understate it
    paper_only = m(us(debt_borrow=rows([3.0] * 4, alias="CommercialPaper")))
    assert paper_only["debt_equity"] == pytest.approx(40.0 / 60.0) and paper_only["debt_basis"] == "TOTAL_LIABILITIES"       # commercial paper alone is not the company's debt
    borrowings_only = m(us(debt_borrow=rows([3.0] * 4, alias="ShortTermBorrowings")))
    assert borrowings_only["debt_equity"] == pytest.approx(3.0 / 60.0) and borrowings_only["debt_basis"] == "PARTS"         # as before: a company with a small credit line and nothing else
    kr = {k: v for k, v in us().items() if not k.startswith("debt_")}
    assert m(kr, source="OpenDART 사업보고서")["debt_basis"] == "TOTAL_LIABILITIES"
    no_balance = {k: v for k, v in kr.items() if k != "liabilities"}
    assert m(no_balance)["debt_equity"] is None and m(no_balance)["debt_basis"] is None


def test_convertible_notes_are_long_term_debt_when_no_other_long_term_tag_exists():
    def fact(val):
        return {"units": {"USD": [{"end": "2025-12-31", "val": val, "filed": "2026-02-15", "form": "10-K"}]}}
    only = f.extract_us({"facts": {"us-gaap": {"ConvertibleLongTermNotesPayable": fact(4.0), "ConvertibleNotesPayableCurrent": fact(1.0), "Liabilities": fact(13.0)}}})
    assert only["debt_long"][0]["alias"] == "ConvertibleLongTermNotesPayable" and only["debt_short"][0]["alias"] == "ConvertibleNotesPayableCurrent"
    both = f.extract_us({"facts": {"us-gaap": {"ConvertibleLongTermNotesPayable": fact(4.0), "LongTermDebtNoncurrent": fact(9.0)}}})
    assert both["debt_long"][0] == {"end": "2025-12-31", "val": 9.0, "filed": "2026-02-15", "alias": "LongTermDebtNoncurrent"}      # the wider tag wins
    got = m(us(debt_long=rows([4.0] * 4, alias="ConvertibleLongTermNotesPayable"), debt_short=rows([1.0] * 4, alias="ConvertibleNotesPayableCurrent")))
    assert got["debt_equity"] == pytest.approx(5.0 / 60.0) and got["debt_basis"] == "PARTS"


def test_a_zero_left_untagged_is_still_zero_for_each_part():
    got = m(us(debt_long=rows([20.0] * 4, alias="LongTermDebtNoncurrent"), debt_short=rows([2.0, 2.0, 0.0, None], alias="LongTermDebtCurrent"), debt_borrow=rows([1.0, 0.0, 0.0, None], alias="ShortTermBorrowings")))
    assert got["debt_equity"] == pytest.approx(20.0 / 60.0)


def test_extraction_reads_the_three_parts_and_the_total_tags():
    def fact(val):
        return {"units": {"USD": [{"end": "2025-12-31", "val": val, "filed": "2026-02-15", "form": "10-K"}]}}
    out = f.extract_us({"facts": {"us-gaap": {"LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities": fact(50.0), "ShortTermBorrowings": fact(4.0), "CommercialPaper": fact(9.0),
                                              "LongTermDebtAndCapitalLeaseObligationsCurrent": fact(6.0), "DebtCurrent": fact(10.0)}}})
    assert out["debt_long"][0]["alias"] == "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities" and out["debt_borrow"][0] == {"end": "2025-12-31", "val": 4.0, "filed": "2026-02-15", "alias": "ShortTermBorrowings"}
    assert out["debt_total"] == [] and f.extract_us({"facts": {"us-gaap": {"DebtLongtermAndShorttermCombinedAmount": fact(7.0)}}})["debt_total"][0]["val"] == 7.0
    assert out["debt_short"][0]["alias"] == "LongTermDebtAndCapitalLeaseObligationsCurrent"
    gone = f.drop_stale_series({"revenue": rows([1.0] * 4), "debt_long": rows([5.0, 5.0, None, None]), "debt_short": rows([1.0] * 4), "debt_borrow": rows([1.0] * 4), "debt_total": rows([9.0] * 4)})
    assert gone["debt_long"] == [] and gone["debt_short"] == [] and gone["debt_borrow"] == [] and len(gone["debt_total"]) == 4


# ---------------------------------------------------------------------- stale figures, financial cash flow
def test_figures_are_stale_once_a_newer_annual_report_is_overdue():
    assert f.STALE_DAYS == 365 + 90 + 14
    d = us()                                                                         # fiscal year ended 2025-12-31
    assert f.metrics(d, 10.0, "2027-04-13", shares=10.0)["status"] == "REAL"         # 468 days
    assert f.metrics(d, 10.0, "2027-04-15", shares=10.0)["status"] == "STALE"        # 470 days: the 2026 report is overdue
    stale = {"market": "US", "fund": f.metrics(d, 10.0, "2027-04-15", shares=10.0)}
    assert factors.profitability(stale)["status"] == "STALE"


def test_a_financial_company_has_no_cash_flow_to_profit_ratio():
    assert m(us())["ocf_to_ni"] == pytest.approx(15.0 / 12.0)
    bank = m(us(), is_financial=True)
    assert bank["ocf_to_ni"] is None and bank["roe"] is not None
    with_growth = factors.earnings_revenue_quality({"market": "US", "fund": bank})
    assert with_growth["status"] == "REAL" and with_growth["raw"]["ocf_to_ni"] is None        # growth alone still gives the factor a value


# ---------------------------------------------------------------------- Korean business years
def test_the_newest_business_year_follows_the_settlement_month():
    assert f.last_business_year(date(2026, 11, 11), 12) == 2025 and f.last_business_year(date(2027, 1, 2), 12) == 2026
    assert f.last_business_year(date(2026, 6, 30), 6) == 2025 and f.last_business_year(date(2026, 7, 1), 6) == 2026
    assert f.last_business_year(date(2026, 3, 31), 3) == 2025 and f.last_business_year(date(2026, 4, 1), 3) == 2026
    assert [f.fiscal_month_of(x) for x in ("06월", "12월", 3, None, "", "13월", "결산")] == [6, 12, 3, 12, 12, 12, 12]
    assert service._kr_fund_key("005930", 12) == "krfund3:005930" and service._kr_fund_key("030960", 6) == "krfund3:030960:fm06"


class Dart:
    def __init__(self):
        self.asked = []

    def statements(self, corp, year, reprt, fs):
        self.asked.append((year, fs))
        if fs == "CFS":
            return {"status": "UNAVAILABLE", "list": []}
        return {"status": "REAL", "list": [{"rcept_no": f"{year}0910000001", "sj_div": "IS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": str(100 + year), "currency": "KRW"}]}


def test_a_june_company_is_read_up_to_the_year_that_ended_this_summer(monkeypatch):
    from markets.kr import dart
    seen = {}

    def normalize(rows_, *, corp_code, ticker, year, reprt_code, fs_div, fiscal_month=12, retrieved_at=""):
        seen[year] = dart.fiscal_period(year, reprt_code, fiscal_month)["period_end"]
        return [{"year": year}]
    monkeypatch.setattr(dart, "choose_basis", lambda fetched: {"rows": fetched["OFS"]["list"], "fs_div": "OFS"})
    monkeypatch.setattr(dart, "normalize_statements", normalize)
    c = Dart()
    got = f.load_kr_statements("00000001", "030960", "NON_FINANCIAL", date(2026, 11, 11), c, extract=lambda obs, klass: obs, fiscal_month=6)
    assert sorted(got) == [2023, 2024, 2025, 2026] and seen[2026] == "2026-06-30" and seen[2023] == "2023-06-30"
    c2 = Dart()
    dec = f.load_kr_statements("00000001", "005930", "NON_FINANCIAL", date(2026, 11, 11), c2, extract=lambda obs, klass: obs)
    assert sorted(dec) == [2022, 2023, 2024, 2025] and seen[2025] == "2025-12-31"            # a December company is read exactly as before


# ---------------------------------------------------------------------- Korean credit conditions
class Ecos:
    def __init__(self, spread_now=0.6, fail=False, days=400):
        self.spread_now, self.fail, self.days, self.calls = spread_now, fail, days, []

    def ecos_series(self, stat, cycle, start, end, items):
        self.calls.append((stat, cycle, tuple(items)))
        if self.fail:
            raise RuntimeError("ECOS request failed")
        out = []
        for i in range(self.days):
            d = date.fromordinal(date(2026, 11, 10).toordinal() - (self.days - 1 - i))
            gov = 3.0
            spread = self.spread_now if i == self.days - 1 else 0.4 + 0.8 * i / (self.days - 2)        # history runs from 0.4 to 1.2
            out.append([d.isoformat(), gov if items[0] == service.KR_CREDIT["treasury"] else gov + spread])
        return out


def test_korean_credit_is_the_corporate_spread_placed_in_its_own_history(tmp_path):
    src = Ecos(spread_now=0.6)
    got = QSF(tmp_path, src=src, now=lambda: NOW)._kr_credit()
    assert got["status"] == "REAL" and got["date"] == "2026-11-10" and got["value"] == pytest.approx(0.6) and got["n"] == 400
    assert got["percentile"] == pytest.approx(101 / 400, abs=0.01) and got["normalized"] == pytest.approx(1 - got["percentile"])      # a narrow spread scores high
    assert {c[2] for c in src.calls} == {("010300000",), ("010200000",)} and all(c[0] == "817Y002" and c[1] == "D" for c in src.calls)
    fac = factors.credit_liquidity({"regime": {"kr_credit": got}})
    assert fac["status"] == "REAL" and fac["normalized"] == pytest.approx(got["normalized"]) and "스프레드" in fac["explanation"] and fac["raw"]["window_obs"] == 400
    wide = QSF(tmp_path / "w", src=Ecos(spread_now=2.0), now=lambda: NOW)._kr_credit()
    assert wide["normalized"] == pytest.approx(0.0)


def test_korean_credit_is_missing_without_the_key_or_enough_history_and_stale_when_old(tmp_path):
    assert QSF(tmp_path / "a", src=Ecos(fail=True), now=lambda: NOW)._kr_credit()["status"] == "UNAVAILABLE"
    assert QSF(tmp_path / "b", src=object(), now=lambda: NOW)._kr_credit()["status"] == "UNAVAILABLE"           # a source without the Bank of Korea call
    short = QSF(tmp_path / "c", src=Ecos(days=100), now=lambda: NOW)._kr_credit()
    assert short["status"] == "UNAVAILABLE" and "이력" in short["reason"]
    assert factors.credit_liquidity({"regime": {"kr_credit": short}})["status"] == "MISSING"
    late = QSF(tmp_path / "d", src=Ecos(), now=lambda: datetime(2026, 11, 20, tzinfo=timezone.utc))._kr_credit()
    assert late["status"] == "STALE" and factors.credit_liquidity({"regime": {"kr_credit": late}})["status"] == "STALE"
