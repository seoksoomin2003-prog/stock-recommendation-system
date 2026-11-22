"""Trailing-four-quarter figures (terminal/qsf/fund_trailing.py) and the record of both scores (terminal/qsf/fund_period.py).
Rules: reports/QSF_FUND_PERIOD_PROTOCOL.md.  Made-up filings, no network."""
import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from terminal import automation, store_watch
from terminal.qsf import config, fund_period as fp, fund_trailing as ft, fundamentals as F, kr_forward as kf, ledger, readings as rd, service

NOW = datetime(2026, 11, 24, 22, 30, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------- US: made-up SEC facts
def row(start, end, val, form, filed):
    return {**({"start": start} if start else {}), "end": end, "val": val, "form": form, "filed": filed}


def flows(annual, q_now, q_before, with_three_months=True):
    """Fiscal years 2022..2025 (calendar), nine months of 2026 and of 2025.  ``annual``: {year: value}."""
    out = [row(f"{y}-01-01", f"{y}-12-31", v, "10-K", f"{y + 1}-02-10") for y, v in annual.items()]
    out += [row("2026-01-01", "2026-09-30", q_now, "10-Q", "2026-11-03"), row("2025-01-01", "2025-09-30", q_before, "10-Q", "2025-11-04")]
    if with_three_months:
        out += [row("2026-07-01", "2026-09-30", q_now / 3, "10-Q", "2026-11-03")]
    return out


def instants(annual, q_now, q_before):
    return [row(None, f"{y}-12-31", v, "10-K", f"{y + 1}-02-10") for y, v in annual.items()] + [row(None, "2026-09-30", q_now, "10-Q", "2026-11-03"), row(None, "2025-09-30", q_before, "10-Q", "2025-11-04")]


def facts(**over):
    years = {2022: 800.0, 2023: 900.0, 2024: 1000.0, 2025: 1200.0}
    gaap = {
        "Revenues": {"units": {"USD": flows(years, 1050.0, 870.0)}},
        "NetIncomeLoss": {"units": {"USD": flows({y: v / 10 for y, v in years.items()}, 120.0, 84.0)}},
        "OperatingIncomeLoss": {"units": {"USD": flows({y: v / 8 for y, v in years.items()}, 150.0, 105.0)}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": flows({y: v / 9 for y, v in years.items()}, 130.0, 90.0, with_three_months=False)}},
        "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": flows({y: 100.0 for y in years}, 98.0, 100.0, with_three_months=False) + [row("2026-07-01", "2026-09-30", 97.0, "10-Q", "2026-11-03"), row("2025-07-01", "2025-09-30", 100.0, "10-Q", "2025-11-04")]}},
        "StockholdersEquity": {"units": {"USD": instants({y: v / 2 for y, v in years.items()}, 700.0, 560.0)}},
        "Assets": {"units": {"USD": instants({y: v for y, v in years.items()}, 1400.0, 1150.0)}},
    }
    gaap.update(over)
    return {"facts": {"us-gaap": gaap}}


def test_a_trailing_flow_is_last_year_plus_this_year_to_date_less_the_same_months_a_year_before():
    periods = ft.us_periods(facts())
    v = ft.view(periods, "2026-11-20", "US")
    rev = {r["end"]: r for r in v["revenue"]}
    assert rev["2026-09-30"]["val"] == pytest.approx(1200 + 1050 - 870) and rev["2026-09-30"]["filed"] == "2026-11-03" and rev["2026-09-30"]["alias"] == "Revenues"
    assert [r["end"] for r in v["revenue"]] == ["2026-09-30"]            # a year before needs 2024's nine months, which are not on file: no point there, and no growth figure
    assert v["equity"][-1] == {"end": "2026-09-30", "val": 700.0, "filed": "2026-11-03", "alias": "StockholdersEquity"} and [r["end"] for r in v["equity"]] == ["2025-09-30", "2026-09-30"]
    assert v["shares_avg"][-1]["val"] == 97.0 and v["eps"][-1]["val"] == pytest.approx((120 + 120 - 84) / 97.0)       # trailing profit over the newest three months' count
    m = ft.metrics(periods, 50.0, "2026-11-20", "US")
    assert m["rev_growth"] is None and m["status"] == "REAL" and m["period_basis"] == "TRAILING" and m["fiscal_end"] == "2026-09-30" and m["filed"] == "2026-11-03" and m["source"] == ft.SOURCE["US"]
    assert m["roe"] == pytest.approx(156 / 700) and m["net_margin"] == pytest.approx(156 / 1380) and m["equity_assets"] == pytest.approx(0.5)
    a = F.metrics(F.drop_stale_series(F.extract_us(facts())), 50.0, "2026-11-20")
    assert a["fiscal_end"] == "2025-12-31" and a["roe"] == pytest.approx(120 / 600) and a["net_margin"] == pytest.approx(0.1)


def test_only_what_was_on_file_is_read_and_without_a_newer_quarter_the_figures_are_the_annual_ones():
    periods = ft.us_periods(facts())
    before = ft.metrics(periods, 50.0, "2026-11-02", "US")                   # the day before the 10-Q
    assert before["period_basis"] == "ANNUAL" and before["fiscal_end"] == "2025-12-31" and before["roe"] == pytest.approx(120 / 600)
    assert ft.fiscal_year_ends(periods, "2026-11-20") >= {"2025-12-31", "2024-12-31"} and "2026-09-30" not in ft.fiscal_year_ends(periods, "2026-11-20")
    amended = facts()
    amended["facts"]["us-gaap"]["Revenues"]["units"]["USD"].append(row("2026-01-01", "2026-09-30", 1100.0, "10-Q/A", "2026-11-18"))
    p2 = ft.us_periods(amended)
    assert ft.view(p2, "2026-11-20", "US")["revenue"][-1]["val"] == pytest.approx(1200 + 1100 - 870) and ft.view(p2, "2026-11-17", "US")["revenue"][-1]["val"] == pytest.approx(1380)
    assert ft.metrics({"flow": {}, "instant": {}}, 50.0, "2026-11-20", "US")["status"] == "UNAVAILABLE"


def test_a_flow_without_all_three_parts_is_empty_and_never_filled_from_the_annual_report():
    gone = facts()
    ocf = gone["facts"]["us-gaap"]["NetCashProvidedByUsedInOperatingActivities"]["units"]["USD"]
    ocf[:] = [r for r in ocf if r["end"] != "2025-09-30"]                    # last year's nine months of cash flow are not on file
    m = ft.metrics(ft.us_periods(gone), 50.0, "2026-11-20", "US")
    assert m["fiscal_end"] == "2026-09-30" and m["ocf_to_ni"] is None and m["roe"] is not None
    lone = [{"start": "2026-07-01", "end": "2026-09-30", "val": 5.0, "filed": "2026-11-03"}, {"start": "2025-01-01", "end": "2025-12-31", "val": 20.0, "filed": "2026-02-10"}]
    assert [p["end"] for p in ft.trailing_points(lone, "2026-11-20")] == ["2025-12-31"]      # three months alone are not a year to date
    two_kinds = [{"start": "2025-01-01", "end": "2025-12-31", "val": 20.0, "filed": "2026-02-10", "basis": "SEPARATE"}, {"start": "2026-01-01", "end": "2026-09-30", "val": 18.0, "filed": "2026-11-10", "basis": "CONSOLIDATED"},
                 {"start": "2025-01-01", "end": "2025-09-30", "val": 14.0, "filed": "2025-11-10", "basis": "CONSOLIDATED"}]
    assert [p["end"] for p in ft.trailing_points(two_kinds, "2026-11-20")] == ["2025-12-31"]  # a separate year is never added to consolidated quarters


def test_the_stored_rows_keep_recent_periods_and_the_newest_two_filings():
    many = facts()
    many["facts"]["us-gaap"]["Revenues"]["units"]["USD"] += [row("2026-01-01", "2026-09-30", 1060.0 + k, "10-Q/A", f"2026-11-{10 + k:02d}") for k in range(3)] + [row("2015-01-01", "2015-12-31", 1.0, "10-K", "2016-02-01")]
    rows = ft.us_periods(many)["flow"]["revenue"]
    assert [r["filed"] for r in rows if r["end"] == "2026-09-30" and r["start"] == "2026-01-01"] == ["2026-11-11", "2026-11-12"] and all(r["end"] >= "2020-01-01" for r in rows)
    assert ft.yearly([{"end": "2024-09-28", "val": 1}, {"end": "2025-06-30", "val": 2}, {"end": "2025-09-27", "val": 3}, {"end": "2026-09-26", "val": 4}]) == [{"end": "2024-09-28", "val": 1}, {"end": "2025-09-27", "val": 3}, {"end": "2026-09-26", "val": 4}]


# ---------------------------------------------------------------------- Korea
def kr_series(ends, scale, basis="CONSOLIDATED", eps=None, filed_after=75):
    def rows(values):
        return [{"end": e, "val": v, "filed": (date.fromisoformat(e).replace(day=1)).isoformat()[:8] + "28" if False else _later(e, filed_after), "basis": basis} for e, v in zip(ends, values)]
    out = {"revenue": rows([1000.0 * s for s in scale]), "op_income": rows([100.0 * s for s in scale]), "net_income": rows([80.0 * s for s in scale]), "equity": rows([500.0 * s for s in scale]),
           "assets": rows([1000.0 * s for s in scale]), "liabilities": rows([500.0 * s for s in scale]), "ocf": rows([90.0 * s for s in scale]), "capex": rows([30.0 * s for s in scale]),
           "eps": rows(eps or [800.0 * s for s in scale]), "dividends": [], "current_assets": [], "current_liabilities": [], "cash": [], "_bases": [basis]}
    return out


def _later(day, days):
    from datetime import timedelta
    return (date.fromisoformat(day) + timedelta(days=days)).isoformat()


ANNUAL_ENDS = ["2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"]
QUARTER_ENDS = ["2022-09-30", "2023-09-30", "2024-09-30", "2025-09-30", "2026-09-30"]


def test_korean_trailing_figures_come_from_the_fiscal_years_and_the_same_quarter_of_each_year():
    annual = kr_series(ANNUAL_ENDS, [1.0, 1.1, 1.2, 1.3])
    quarters = kr_series(QUARTER_ENDS, [0.7, 0.8, 0.85, 0.9, 1.2], filed_after=45)
    periods = ft.kr_periods(annual, quarters, 9)
    assert periods["flow"]["revenue"][0]["start"] == "2022-01-01" and {r["start"] for r in periods["flow"]["revenue"] if r["end"] == "2026-09-30"} == {"2026-01-01"}
    v = ft.view(periods, "2026-11-20", "KR")
    assert [r["end"] for r in v["revenue"]] == ["2023-09-30", "2024-09-30", "2025-09-30", "2026-09-30"]
    assert v["revenue"][-1]["val"] == pytest.approx(1000 * (1.3 + 1.2 - 0.9)) and v["revenue"][0]["val"] == pytest.approx(1000 * (1.0 + 0.8 - 0.7)) and v["revenue"][-1]["basis"] == "CONSOLIDATED"
    assert v["eps"][-1]["val"] == pytest.approx(800 * (1.3 + 1.2 - 0.9)) and v["equity"][-1]["val"] == pytest.approx(600.0)
    m = ft.metrics(periods, 20000.0, "2026-11-20", "KR", shares=1000.0)
    assert m["period_basis"] == "TRAILING" and m["fiscal_end"] == "2026-09-30" and m["basis"] == "CONSOLIDATED" and m["source"] == ft.SOURCE["KR"]
    assert m["rev_growth"] == pytest.approx(1.6 / (1.2 + 0.9 - 0.85) - 1) and m["rev_cagr3"] == pytest.approx((1.6 / 1.1) ** (1 / 3) - 1) and m["roe"] == pytest.approx(80 * 1.6 / 600)
    assert ft.metrics(periods, 20000.0, "2026-11-10", "KR", shares=1000.0)["period_basis"] == "ANNUAL"        # the third-quarter report arrived on 11-14


def test_a_summed_korean_eps_is_dropped_when_its_parts_stand_on_different_share_counts():
    annual = kr_series(ANNUAL_ENDS, [1.0, 1.1, 1.2, 1.3])
    split = kr_series(QUARTER_ENDS, [0.7, 0.8, 0.85, 0.9, 1.2], filed_after=45, eps=[800 * 0.7, 800 * 0.8, 800 * 0.85, 800 * 0.9, 800 * 1.2 / 5])      # five-for-one in 2026
    v = ft.view(ft.kr_periods(annual, split, 9), "2026-11-20", "KR")
    assert "2026-09-30" not in {r["end"] for r in v["eps"]} and v["net_income"][-1]["end"] == "2026-09-30"
    m = ft.metrics(ft.kr_periods(annual, split, 9), 20000.0, "2026-11-20", "KR", shares=1000.0)
    assert m["pe_basis"] == "MARKET_VALUE" and m["pe"] == pytest.approx(20000.0 * 1000 / (80 * 1.6)) and m["eps_growth"] is None
    other = kr_series(QUARTER_ENDS, [0.7, 0.8, 0.85, 0.9, 1.2], basis="SEPARATE", filed_after=45)
    assert ft.metrics(ft.kr_periods(annual, other, 9), 20000.0, "2026-11-20", "KR")["status"] == "UNAVAILABLE"          # quarters on another basis are not added to the years: no trailing figures at all
    # One set of reports split the parent's profit from the group's and the other did not: both are read as the group's.
    split_q = kr_series(QUARTER_ENDS, [0.7, 0.8, 0.85, 0.9, 1.2], filed_after=45)
    split_q["net_income_all"] = [{**r, "val": r["val"] * 1.25} for r in split_q["net_income"]]                          # the quarters: parent 80, group 100
    whole_a = kr_series(ANNUAL_ENDS, [1.0, 1.1, 1.2, 1.3])
    whole_a["net_income"] = [{**r, "val": r["val"] * 1.25} for r in whole_a["net_income"]]                              # the years have the group's figure only
    mixed = ft.view(ft.kr_periods(whole_a, split_q, 9), "2026-11-20", "KR")
    assert mixed["net_income"][-1]["val"] == pytest.approx(100 * (1.3 + 1.2 - 0.9)) and not mixed["net_income_all"] and "net_income_all" in split_q      # the caller's series are left as they were
    group_q = {k: v for k, v in split_q.items() if k != "net_income_all"}
    group_q["net_income"] = split_q["net_income_all"]                                                                   # the other way round: the quarters have the group's figure only
    split_a = {**annual, "net_income_all": [{**r, "val": r["val"] * 1.25} for r in annual["net_income"]]}
    assert ft.view(ft.kr_periods(split_a, group_q, 9), "2026-11-20", "KR")["net_income"][-1]["val"] == pytest.approx(100 * (1.3 + 1.2 - 0.9))


def test_which_korean_quarters_are_asked_and_how_a_report_is_kept():
    assert ft.kr_quarter_candidates(date(2026, 11, 22)) == [(2026, 9, "2026-09-30"), (2026, 6, "2026-06-30"), (2026, 3, "2026-03-31")]
    assert ft.kr_quarter_candidates(date(2026, 10, 20)) == [(2026, 6, "2026-06-30"), (2026, 3, "2026-03-31")]           # the third quarter ended 20 days ago
    assert ft.kr_quarter_candidates(date(2026, 2, 10)) == [] and ft.kr_quarter_candidates(date(2026, 4, 30)) == [(2026, 3, "2026-03-31")]
    assert ft.kr_quarter_candidates(date(2026, 11, 22), 6) == [(2027, 3, "2026-09-30")] and ft.kr_quarter_candidates(date(2026, 11, 22), 3)[0] == (2027, 6, "2026-09-30")
    assert ft._months_before("2026-09-30", 9) == "2026-01-01" and ft._months_before("2026-03-31", 12) == "2025-04-01" and ft.REPORT_OF_MONTHS == {9: "11014", 6: "11012", 3: "11013"}
    real = {"status": "REAL", "value": 5.0, "period_end": "2026-03-31", "receipt_date": "2026-05-15", "basis": "CONSOLIDATED", "currency": "KRW", "account_name": "매출", "rcept_no": "1"}
    filled = ft.fill_first_quarter({"revenue": {"status": "UNAVAILABLE"}, "total_assets": real}, {"revenue": real, "total_assets": {"status": "UNAVAILABLE"}})
    assert filled == {"revenue": real, "total_assets": real}
    assert ft.slim({"revenue": real, "capex": {"status": "UNAVAILABLE", "reason": "x"}}) == {"revenue": {k: real[k] for k in ft.KR_KEPT}}
    assert ft.latest_basis({"revenue": [{"end": "2024-12-31", "filed": "2025-03-01", "basis": "SEPARATE"}, {"end": "2025-12-31", "filed": "2026-03-01", "basis": "CONSOLIDATED"}], "_bases": ["CONSOLIDATED", "SEPARATE"]}) == "CONSOLIDATED"


# ---------------------------------------------------------------------- which period is live, and what a card keeps
def test_the_live_score_reads_annual_statements_until_the_one_reading_says_otherwise(tmp_path, monkeypatch):
    monkeypatch.delenv(fp.SWITCH, raising=False)
    assert fp.live_period(tmp_path, "US") == "ANNUAL" and fp.DEFAULT == "ANNUAL"
    (tmp_path / fp.REPORTS["US"]).parent.mkdir(parents=True)
    (tmp_path / fp.REPORTS["US"]).write_text(json.dumps({"verdict": "NOT_DISTINGUISHED"}), encoding="utf-8")
    assert fp.live_period(tmp_path, "US") == "ANNUAL"
    (tmp_path / fp.REPORTS["US"]).write_text(json.dumps({"verdict": "TRAILING_BETTER"}), encoding="utf-8")
    assert fp.live_period(tmp_path, "US") == "TRAILING" and fp.live_period(tmp_path, "KR") == "ANNUAL"                 # each market has its own reading
    monkeypatch.setenv(fp.SWITCH, "annual")
    assert fp.live_period(tmp_path, "US") == "ANNUAL"
    monkeypatch.setenv(fp.SWITCH, "TRAILING")
    assert fp.live_period(tmp_path, "KR") == "TRAILING"
    monkeypatch.setenv(fp.SWITCH, "nonsense")
    assert fp.live_period(tmp_path, "KR") == "ANNUAL"
    (tmp_path / fp.REPORTS["KR"]).write_text("{broken", encoding="utf-8")
    assert fp.live_period(tmp_path, "KR") == "ANNUAL"


def test_the_service_carries_the_other_periods_figures_and_a_card_keeps_both_scores(tmp_path, monkeypatch):
    monkeypatch.delenv(fp.SWITCH, raising=False)
    q = service.QSF(tmp_path)
    annual = {"status": "REAL", "fiscal_end": "2025-12-31", "filed": "2026-02-10", "roe": 0.10}
    trailing = {"status": "REAL", "fiscal_end": "2026-09-30", "filed": "2026-11-03", "roe": 0.18, "period_basis": "TRAILING"}
    got = q._with_other_period("US", annual, trailing)
    assert got["live_period"] == "ANNUAL" and got["period_basis"] == "ANNUAL" and got["roe"] == 0.10 and got["other_period"] == trailing
    same = q._with_other_period("US", annual, {**annual, "period_basis": "ANNUAL", "roe": 0.11})
    assert same["other_period"] == {**annual, "period_basis": "ANNUAL"}                                # no newer quarter: the annual figures stand for both
    for missing in (None, {"status": "UNAVAILABLE"}):       # no trailing figures: the stock is on annual ones under either rule, and the record says so
        assert q._with_other_period("US", annual, missing)["other_period"] == {**annual, "period_basis": "ANNUAL"}
    assert q._with_other_period("US", {"status": "UNAVAILABLE", "reason": "x"}, trailing) == {"status": "UNAVAILABLE", "reason": "x"}
    monkeypatch.setenv(fp.SWITCH, "TRAILING")
    live = q._with_other_period("US", annual, trailing)
    assert live["live_period"] == "TRAILING" and live["roe"] == 0.18 and live["other_period"]["roe"] == 0.10 and live["other_period"]["period_basis"] == "ANNUAL"
    assert q._with_other_period("US", annual, None)["live_period"] == "ANNUAL"                         # a stock without trailing figures stays on its annual ones
    field = fp.card_field("ANNUAL", 61.23456, got, 66.5, trailing)
    assert field == {"live": "ANNUAL", "annual": {"score": 61.235, "fiscal_end": "2025-12-31", "filed": "2026-02-10", "newer_quarter": False},
                     "trailing": {"score": 66.5, "fiscal_end": "2026-09-30", "filed": "2026-11-03", "newer_quarter": True}}
    assert fp.card_field("TRAILING", 66.5, trailing, None, None)["annual"] == {"score": None, "fiscal_end": None, "filed": None, "newer_quarter": False}
    card = {"domains": {}, "factors": [], "levels": {}, "fund_period": field}
    assert ledger.snapshot(card)["fund_period"] == field and "fund_period" not in ledger.snapshot({"domains": {}, "factors": [], "levels": {}})
    assert q._us_trailing("AAA", "1", 10.0, "2026-11-20", {}) is None                                  # no period rows kept yet
    q.cache.write("periods1:1", ft.us_periods(facts()))
    assert q._us_trailing("AAA", "1", 50.0, "2026-11-20", {})["period_basis"] == "TRAILING"


class FakeDart:
    configured = True

    def __init__(self, missing=()):
        self.asked, self.missing, self.fail = [], set(missing), False

    def statements(self, corp, year, reprt, fs):
        self.asked.append((year, reprt, fs))
        if self.fail:
            raise RuntimeError("down")
        return {"status": "UNAVAILABLE", "list": []} if (year, reprt) in self.missing else {"status": "REAL", "list": [{"year": year}]}


def test_korean_quarterly_reports_are_asked_newest_first_kept_and_not_asked_again(tmp_path, monkeypatch):
    from markets.kr import dart
    scale = {2022: 0.7, 2023: 0.8, 2024: 0.85, 2025: 0.9, 2026: 1.2}
    monkeypatch.setattr(dart, "normalize_statements", lambda rows, **kw: [{"year": kw["year"], "reprt": kw["reprt_code"], "basis": dart.FS_BASIS[kw["fs_div"]]}])

    def concepts(obs, klass, amount_type="FY"):
        y, s = obs[0]["year"], scale[obs[0]["year"]]
        end, filed = f"{y}-09-30", f"{y}-11-14"
        mk = lambda v: {"status": "REAL", "value": v, "period_end": end, "receipt_date": filed, "basis": obs[0]["basis"], "currency": "KRW", "account_name": "x"}      # noqa: E731
        return {"revenue": mk(1000 * s), "operating_income": mk(100 * s), "net_income": mk(80 * s), "total_equity": mk(500 * s), "total_assets": mk(1000 * s), "total_liabilities": mk(500 * s),
                "operating_cash_flow": mk(90 * s), "capex": mk(30 * s), "eps_basic": mk(800 * s)}
    monkeypatch.setattr(dart, "extract_concepts", concepts)
    annual = {k: v for k, v in kr_series(ANNUAL_ENDS, [1.0, 1.1, 1.2, 1.3]).items()}
    d = FakeDart()
    q = service.QSF(tmp_path, dart=d)
    m = q._kr_trailing("005930", "00126380", "NON_FINANCIAL", 12, "2026-11-20", annual, 20000.0, {"shares": 1000.0})
    assert m["period_basis"] == "TRAILING" and m["fiscal_end"] == "2026-09-30" and m["rev_growth"] == pytest.approx(1.6 / 1.25 - 1)
    assert d.asked == [(2026, "11014", "CFS"), (2022, "11014", "CFS"), (2023, "11014", "CFS"), (2024, "11014", "CFS"), (2025, "11014", "CFS")]
    q._kr_trailing("005930", "00126380", "NON_FINANCIAL", 12, "2026-11-21", annual, 20000.0, {"shares": 1000.0})
    assert len(d.asked) == 5                                                                           # every report is kept
    late = FakeDart(missing={(2026, "11014")})
    q2 = service.QSF(tmp_path / "b", dart=late)
    got = q2._kr_trailing("000001", "1", "NON_FINANCIAL", 12, "2026-11-20", annual, 20000.0, {})
    assert late.asked[:2] == [(2026, "11014", "CFS"), (2026, "11012", "CFS")] and got is not None      # the third quarter is not filed yet: the half year is the newest
    none = FakeDart(missing={(2026, "11014"), (2026, "11012"), (2026, "11013")})
    assert service.QSF(tmp_path / "c", dart=none)._kr_trailing("000002", "2", "NON_FINANCIAL", 12, "2026-11-20", annual, 20000.0, {}) == {"annual_only": True}
    down = FakeDart()
    down.fail = True
    assert service.QSF(tmp_path / "d", dart=down)._kr_trailing("000003", "3", "NON_FINANCIAL", 12, "2026-11-20", annual, 20000.0, {}) is None and len(down.asked) == 1      # could not be asked: no older quarter is taken for the newest
    assert service.QSF(tmp_path / "e", dart=FakeDart())._kr_trailing("000004", "4", "NON_FINANCIAL", 12, "2026-11-20", {"_bases": []}, 1.0, {}) is None


# ---------------------------------------------------------------------- the record
def snap(ticker, strategy, day, annual, trailing, market="US", newer=True, both=True):
    s = {"market": market, "ticker": ticker, "strategy": strategy, "data_date": day, "score": annual, "model_version": config.MODEL_VERSION, "entry_session": "2026-11-25", "actionability": "ACTIONABLE"}
    if both:
        s["fund_period"] = {"live": "ANNUAL", "annual": {"score": annual, "fiscal_end": "2025-12-31"}, "trailing": {"score": trailing, "fiscal_end": "2026-09-30" if newer else "2025-12-31", "newer_quarter": newer}}
    return s


def test_a_session_holds_both_scores_under_their_own_names():
    day = "2026-11-24"
    snaps = [snap(f"T{k:03d}", "SWING", day, 40 + k / 10, 45 + k / 10, newer=k % 2 == 0) for k in range(250)] + [snap(f"T{k:03d}", "LONG_TERM", day, 50.0, None) for k in range(100)] + [snap("OLD", "SWING", "2026-11-23", 1, 2)]
    doc = fp.score_session(snaps, day, "US")
    assert len(doc["rows"]) == 350 and doc["live_period"] == "ANNUAL" and doc["newer_quarter"] == 125 and doc["protocol"] == fp.PROTOCOL
    r = next(x for x in doc["rows"] if x["ticker"] == "T100" and x["strategy"] == "SWING")
    assert r == {"ticker": "T100", "strategy": "SWING", "annual": 50.0, "trailing": 55.0, "annual_end": "2025-12-31", "trailing_end": "2026-09-30", "newer_quarter": True, "entry_session": "2026-11-25", "actionability": "ACTIONABLE"}
    assert next(x for x in doc["rows"] if x["strategy"] == "LONG_TERM")["trailing"] is None
    with pytest.raises(fp.NotReady, match="TOO_FEW_STOCKS"):
        fp.score_session(snaps[:100], day, "US")
    with pytest.raises(fp.NotReady, match="NO_SECOND_SCORE"):
        fp.score_session([snap(f"T{k:03d}", "SWING", day, 50, 50, both=False) for k in range(250)], day, "US")


class FakeLedger:
    rows = [{"market": "US", "session": "2026-11-20"}, {"market": "US", "session": "2026-11-23"}, {"market": "US", "session": "2026-11-24"}, {"market": "US", "session": "2026-11-25"}, {"market": "KR", "session": "2026-11-24"}]

    def __init__(self, root):
        pass

    def verify(self):
        return {"status": "OK"}

    def _live_rows(self):
        return self.rows

    def _load(self, r):
        if r["session"] == "2026-11-23":                        # scored before the cards carried the second score
            return [snap(f"T{k:03d}", "SWING", r["session"], 50, 50, both=False) for k in range(250)]
        return [snap(f"T{k:03d}", "SWING", r["session"], 50, 52, market=r["market"]) for k in range(250 if r["session"] == "2026-11-24" else 50)]


def test_record_is_written_once_from_the_ledger_and_waits_on_a_partial_day(tmp_path, monkeypatch):
    monkeypatch.setattr(fp, "Ledger", FakeLedger)
    res = fp.record(tmp_path, "US", now=lambda: NOW)
    assert res["status"] == "WAITING" and res["written"] == ["2026-11-24"] and res["partial"] == ["2026-11-25"] and res["without_second_score"] == ["2026-11-23"] and res["sessions"] == 1
    assert kf.verify(tmp_path, fp.FOLDERS["US"])["status"] == "OK" and not (tmp_path / fp.FOLDERS["KR"]).exists()
    before = (tmp_path / fp.FOLDERS["US"] / "2026-11-24.json.gz").read_bytes()
    assert fp.record(tmp_path, "US", now=lambda: NOW)["written"] == [] and (tmp_path / fp.FOLDERS["US"] / "2026-11-24.json.gz").read_bytes() == before
    assert fp.record(tmp_path, "KR", now=lambda: NOW)["written"] == ["2026-11-24"]
    st = fp.status(tmp_path)["markets"]["US"]
    assert st["records"] == 1 and st["evaluated"] is False and st["verdict"] is None and st["live_period"] == "ANNUAL"

    class Broken(FakeLedger):
        def verify(self):
            return {"status": "BROKEN"}
    monkeypatch.setattr(fp, "Ledger", Broken)
    assert fp.record(tmp_path, "US", now=lambda: NOW) == {"status": "FAILED", "reason": "LEDGER_BROKEN"}


class Panel:
    """Prices where a stock's 20-session return is its number over a thousand, and the 63-session one twice that."""
    def __init__(self, n_days, tickers):
        self.dates = [f"D{k:04d}" for k in range(n_days)]
        self.col = {t: j for j, t in enumerate(tickers)}

    def forward(self, i, h):
        return np.array([(1 if h == 20 else 2) * int(t[1:]) / 1000 for t in self.col], dtype=float)


def docs_for(n, tickers, trailing_shift=10.0, every=1):
    out = []
    for k in range(n):
        shift = trailing_shift if k % every == 0 else 0.0
        rows = [{"ticker": t, "strategy": s, "annual": 50.0 + int(t[1:]) / 2, "trailing": 50.0 + int(t[1:]) / 2 + shift, "entry_session": f"D{k + 1:04d}", "actionability": "ACTIONABLE" if int(t[1:]) % 2 == 0 else "BLOCKED"}
                for t in tickers for s in ("SWING", "LONG_TERM")]
        out.append({"session": f"S{k:04d}", "market": "US", "rows": rows, "late": False})
    return out


def test_the_one_reading_compares_the_buy_bands_and_a_better_trailing_score_becomes_live(tmp_path, monkeypatch):
    monkeypatch.delenv(fp.SWITCH, raising=False)
    tickers = [f"T{k:03d}" for k in range(40)]
    cost = config.round_trip_cost("US")
    days = fp.measure(docs_for(3, tickers), Panel(400, tickers), "US")
    trailing = [int(t[1:]) / 1000 for t in tickers if 60 + int(t[1:]) / 2 >= 70 and int(t[1:]) % 2 == 0]
    assert len(days) == 3 and days[0]["trailing"] == {"names": 10, "ret": pytest.approx(np.mean(trailing) - cost)} and days[0]["annual"] == {"names": 0, "ret": 0.0} and days[0]["diff"] == pytest.approx(np.mean(trailing) - cost)
    enough = {"days_with_difference": fp.MIN_DIFF_DAYS}
    assert fp.MIN_T == 3.0 and fp.MIN_DIFF_DAYS == 120
    assert fp.verdict({"mean": 0.01, "t": 3.0, **enough}) == "TRAILING_BETTER" and fp.verdict({"mean": -0.01, "t": -3.1, **enough}) == "ANNUAL_BETTER"
    for diff in ({"mean": 0.01, "t": 2.9, **enough}, {"mean": 0.01, "t": None, **enough}, {"mean": 0.01, "t": 9.0, "days_with_difference": 119}, {"mean": 0.01, "t": 9.0}, {"mean": -0.01, "t": 3.5, **enough}):
        assert fp.verdict(diff) == "NOT_DISTINGUISHED", diff          # under the bar, no statistic, too few days, an old report without the count, sign and t disagree
    store = {}
    monkeypatch.setattr(fp.kf, "verify", lambda base, folder: {"status": "OK"})
    monkeypatch.setattr(fp.kf, "read_index", lambda base, folder: [{"session": d["session"]} for d in store["docs"]])
    monkeypatch.setattr(fp.kf, "_read_day", lambda folder, day: next(d for d in store["docs"] if d["session"] == day))
    store["docs"] = docs_for(100, tickers)
    with pytest.raises(RuntimeError, match="100개"):
        fp.evaluate_once(tmp_path, "US", Panel(500, tickers), log=lambda *_: None)
    assert fp.live_period(tmp_path, "US") == "ANNUAL"
    store["docs"] = docs_for(250, tickers, every=2)
    res = fp.evaluate_once(tmp_path, "US", Panel(500, tickers), log=lambda *_: None)
    assert res["verdict"] == "TRAILING_BETTER" and res["applies"] == "TRAILING" and res["swing"]["days"] == 240 and res["long"]["reading"] == "FIGURES_ONLY" and len(res["reasons"]) == 5 and "기준: 120일 이상" in res["reasons"][2] and res["swing"]["difference"]["days_with_difference"] >= 120
    assert "다음 스캔부터" in res["reasons"][-1] and fp.live_period(tmp_path, "US") == "TRAILING" and fp.live_period(tmp_path, "KR") == "ANNUAL"
    with pytest.raises(RuntimeError, match="다시 읽지 않습니다"):
        fp.evaluate_once(tmp_path, "US", Panel(500, tickers), log=lambda *_: None)
    store["docs"] = docs_for(250, tickers, trailing_shift=0.0)
    same = fp.evaluate_once(tmp_path, "KR", Panel(500, tickers), log=lambda *_: None)
    assert same["verdict"] == "NOT_DISTINGUISHED" and same["applies"] == "ANNUAL" and "연간 재무 그대로" in same["reasons"][-1] and fp.live_period(tmp_path, "KR") == "ANNUAL"


# ---------------------------------------------------------------------- wiring
def test_the_daily_job_the_backup_the_readings_and_the_documents_know_the_record():
    assert {"fund_period_kr", "fund_period_us"} <= set(automation.FORWARD_STORES) and sum("fund_period_" in g for g in automation.BACKUP_GLOBS) == 2 and "fund_period_us" in store_watch.NAMES_KO if hasattr(store_watch, "NAMES_KO") else True
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert app.count('_fund_period_record(res, "KR")') == 1 and app.count('_fund_period_record(res, "US")') == 1 and '"fund-period-evaluate": _qsf_fund_period' in app
    by = {e["key"]: e for e in rd.REGISTRY}
    for m in ("kr", "us"):
        e = by[f"fund_period_{m}"]
        assert e["applies"] is True and e["need"] == fp.READ_AT and e["store"] == f"fund_period_{m}" and e["report"] == fp.REPORTS[m.upper()].name and "QSF_FUND_PERIOD" in e["after"]
    assert sum(1 for e in rd.REGISTRY if e["applies"]) == 2 and rd.VERDICT_KO["TRAILING_BETTER"] and rd.VERDICT_KO["ANNUAL_BETTER"]
    src = (ROOT / "terminal" / "qsf" / "service.py").read_text(encoding="utf-8")
    assert 'f"periods1:' in src and 'f"krq1:' in src and "fund_period.live_period(self.base, market)" in src
    proto = (ROOT / fp.PROTOCOL).read_text(encoding="utf-8")
    assert "나란히 기록" in proto and "TRAILING_BETTER" in proto and "QSF_FUND_PERIOD=ANNUAL" in proto and "IC가 A -0.002, B -0.014" in proto
    assert config.MODEL_VERSION == "QSF-1.5.0"                                                         # the live formula and its inputs did not change


def test_the_pass_bar_keeps_a_chance_pass_rare_and_two_episodes_do_not_decide():
    """User decision 2026-11-22.  The difference series is 240 overlapping 20-session returns: with no effect the statistic
    passed the old bar (2.0) about three times as often as a normal test would.  The bar is tied to that fact here."""
    rng = np.random.default_rng(11)
    ts = []
    for _ in range(3000):
        noise = rng.standard_normal(260)
        ts.append(fp.validate.newey_west_t(list(np.convolve(noise, np.ones(20), "valid")[:240]), 20))
    ts = np.array(ts)
    assert np.mean(ts >= 2.0) > 0.055 and np.mean(ts >= fp.MIN_T) < 0.03                              # the old bar was loose, the new one is not
    two = [0.0] * 240
    for start in (20, 150):
        two[start:start + 30] = [0.01] * 30
    days = [{"annual": {"ret": 0.0, "names": 0}, "trailing": {"ret": x, "names": 1 if x else 0}, "diff": x, "ic_annual": None, "ic_trailing": None} for x in two]
    got = fp.summarize(days, 20)["difference"]
    assert got["days_with_difference"] == 60 and 2.0 < got["t"] < fp.MIN_T and fp.verdict(got) == "NOT_DISTINGUISHED"      # passed before (t 2.37)
    proto = (Path(__file__).resolve().parents[1] / "reports" / "QSF_FUND_PERIOD_PROTOCOL.md").read_text(encoding="utf-8")
    assert "수정 1 (2026-11-22)" in proto and "차이 평균 > 0, t ≥ 3.0, 두 점수가 다른 종목을 고른 날 120일 이상" in proto and "첫 줄이 쓰이기 전에" in proto and "차이 평균 > 0, t ≥ 2.0" not in proto
