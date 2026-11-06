"""The recheck reads only what was on file each day, joins earlier company numbers, and never overwrites an earlier result.  No network."""
import pytest

from terminal.qsf import pit, research_score, validate, validate_corrected as vc


def _row(end, filed, val=1.0):
    return {"end": end, "val": val, "filed": filed}


def test_a_later_filing_never_decides_what_had_stopped():
    annual = {"net_income": [_row("2015-12-31", "2016-02-20"), _row("2020-12-31", "2021-02-20")], "revenue": [_row("2015-12-31", "2016-02-20")]}
    assert vc.as_of_annual(annual, "2016-06-01")["revenue"]
    assert vc.as_of_annual(annual, "2021-06-01")["revenue"] == []


def test_a_filing_after_the_day_is_invisible():
    annual = {"net_income": [_row("2015-12-31", "2016-02-20"), _row("2016-12-31", "2017-02-20")]}
    assert [r["end"] for r in vc.as_of_annual(annual, "2016-06-01")["net_income"]] == ["2015-12-31"]


def test_views_shape_matches_the_earlier_reading():
    rec = {"annual": {"net_income": [_row("2015-12-31", "2016-02-20", 5.0)], "revenue": [_row("2015-12-31", "2016-02-20", 50.0)]},
           "full": {"net_income": [{"start": "2015-01-01", "end": "2015-12-31", "val": 5.0, "filed": "2016-02-20"}], "revenue": [{"start": "2015-01-01", "end": "2015-12-31", "val": 50.0, "filed": "2016-02-20"}]}}
    out = vc.fund_views(rec, 10.0, pit.Splits([]), "2016-06-01", False)
    assert set(out) == {"A", "B"} and out["A"]["net_margin"] == 0.1 and out["B"]["net_margin"] == 0.1


def test_earlier_numbers_are_joined_and_the_same_number_is_not_fetched_twice():
    seen = []

    def fetch(c):
        seen.append(c)
        return {"facts": {"us-gaap": {"A" + c: {"units": {"USD": []}}}}}
    merged = vc.joined_facts("0002115436", ["34088", "2115436"], fetch)
    assert seen == ["0002115436", "34088"] and set(merged["facts"]["us-gaap"]) == {"A0002115436", "A34088"}


def test_an_earlier_number_with_no_file_adds_nothing():
    def fetch(c):
        if c == "1134538":
            raise RuntimeError("SEC HTTP_404")
        return {"facts": {"us-gaap": {"A": {"units": {"USD": []}}}}}
    assert set(vc.joined_facts("1467373", ["1134538"], fetch)["facts"]["us-gaap"]) == {"A"}


def test_the_current_number_with_no_file_still_raises():
    def fetch(c):
        raise RuntimeError("SEC HTTP_404")
    with pytest.raises(RuntimeError):
        vc.joined_facts("66479", [], fetch)


def test_a_failed_earlier_number_raises():
    def fetch(c):
        if c == "34088":
            raise RuntimeError("down")
        return {"facts": {}}
    with pytest.raises(RuntimeError):
        vc.joined_facts("2115436", ["34088"], fetch)


@pytest.mark.parametrize("key", ["OPEN", "OOS", "RESEARCH", "SWING"])
def test_each_recheck_runs_once_and_writes_only_its_own_file(tmp_path, key):
    target = tmp_path / vc.REPORTS[key]
    target.parent.mkdir(parents=True)
    assert vc._guard(tmp_path, key) == target
    target.write_text("{}")
    with pytest.raises(RuntimeError):
        vc._guard(tmp_path, key)
    assert "CORRECTED" in target.name


def test_earlier_reading_stays_the_default():
    import inspect
    assert inspect.signature(validate.score_dates).parameters["views"].default is validate.fund_views
    assert inspect.signature(research_score.build_features).parameters["view_of"].default is research_score.earlier_view
