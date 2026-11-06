"""A company whose SEC number changed keeps its annual figures; other companies are untouched and a failed fetch never saves a thin record."""
import pytest

from terminal import sources
from terminal.qsf import fundamentals


def _rows(*years, form="10-K", val=100.0):
    return [{"start": f"{y}-01-01", "end": f"{y}-12-31", "val": val, "filed": f"{y + 1}-02-20", "form": form} for y in years]


def _facts(concept, rows):
    return {"entityName": "X", "facts": {"us-gaap": {concept: {"label": "n", "units": {"USD": rows}}}}}


def test_older_filings_fill_a_number_with_no_annual_report():
    new = _facts("NetIncomeLoss", _rows(2026, form="10-Q"))
    old = _facts("NetIncomeLoss", _rows(2024, 2025))
    annual = fundamentals.extract_us(sources.merge_companyfacts(new, old))
    assert [r["end"][:4] for r in annual["net_income"]] == ["2024", "2025"]
    assert fundamentals.extract_us(new)["net_income"] == []


def test_a_newer_filing_of_the_same_period_is_kept_beside_the_older_one():
    new = _facts("NetIncomeLoss", [{"start": "2024-01-01", "end": "2024-12-31", "val": 7.0, "filed": "2026-02-20", "form": "10-K"}])
    old = _facts("NetIncomeLoss", [{"start": "2024-01-01", "end": "2024-12-31", "val": 5.0, "filed": "2025-02-20", "form": "10-K"}])
    rows = fundamentals.extract_us(sources.merge_companyfacts(new, old))["net_income"]
    assert [(r["filed"], r["val"]) for r in rows] == [("2025-02-20", 5.0), ("2026-02-20", 7.0)]


def test_merge_does_not_change_its_inputs():
    new, old = _facts("A", _rows(2025)), _facts("A", _rows(2024))
    sources.merge_companyfacts(new, old)
    assert len(new["facts"]["us-gaap"]["A"]["units"]["USD"]) == 1
    assert len(old["facts"]["us-gaap"]["A"]["units"]["USD"]) == 1


def test_a_concept_only_in_the_older_number_is_added():
    merged = sources.merge_companyfacts(_facts("A", _rows(2025)), _facts("B", _rows(2024)))
    assert set(merged["facts"]["us-gaap"]) == {"A", "B"}


def test_other_tickers_fetch_one_number_and_keep_their_cache_name():
    seen = []

    def fetch(cik):
        seen.append(cik)
        return _facts("A", _rows(2025))
    sources.facts_with_predecessors("CVX", "93410", fetch)
    assert seen == ["93410"]
    assert sources.facts_key("CVX", "93410") == "93410"


def test_changed_number_uses_a_new_cache_name_and_fetches_both():
    seen = []

    def fetch(cik):
        seen.append(cik)
        return _facts("NetIncomeLoss", _rows(2025))
    sources.facts_with_predecessors("XOM", "0002115436", fetch)
    assert seen == ["0002115436", "34088"]
    assert sources.facts_key("XOM", "0002115436") != "0002115436"


def _series(*ends):
    return [{"end": e, "val": 1.0, "filed": e} for e in ends]


def test_a_series_that_stopped_years_ago_is_empty_not_current():
    a = {"net_income": _series("2024-12-31", "2025-12-31"), "revenue": _series("2019-12-31", "2020-12-31"), "assets": _series("2024-12-31")}
    out = fundamentals.drop_stale_series(a)
    assert out["revenue"] == [] and len(out["net_income"]) == 2 and len(out["assets"]) == 1


def test_losing_one_debt_part_drops_both():
    a = {"net_income": _series("2025-12-31"), "debt_long": _series("2017-12-31"), "debt_short": _series("2025-12-31"), "liabilities": _series("2025-12-31")}
    out = fundamentals.drop_stale_series(a)
    assert out["debt_long"] == [] and out["debt_short"] == [] and len(out["liabilities"]) == 1
    m = fundamentals.metrics({**out, "equity": _series("2025-12-31")}, 10.0, "2026-06-01", shares=5.0)
    assert m["status"] != "UNAVAILABLE"


def test_a_fiscal_year_a_little_behind_stays():
    a = {"net_income": _series("2025-12-31"), "capex": _series("2024-12-31")}
    assert fundamentals.drop_stale_series(a)["capex"]


def test_only_changed_number_companies_are_filtered():
    from terminal.qsf.service import QSF
    stale = _facts("NetIncomeLoss", _rows(2025))
    stale["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": _rows(2015)}}

    class Src:
        @staticmethod
        def sec_companyfacts(cik):
            return stale
    svc = QSF.__new__(QSF)
    svc.src = Src
    assert svc._annual("CVX", "93410")["revenue"]
    assert svc._annual("XOM", "2115436")["revenue"] == []


def test_a_failed_older_fetch_raises_instead_of_saving_thin_figures():
    def fetch(cik):
        if cik == "34088":
            raise RuntimeError("down")
        return _facts("A", _rows(2026, form="10-Q"))
    with pytest.raises(RuntimeError):
        sources.facts_with_predecessors("XOM", "0002115436", fetch)
