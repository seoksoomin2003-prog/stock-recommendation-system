"""Independent test: frozen hypothesis, older names under aliases, the one-run guard.  No network."""
from pathlib import Path

import pytest

from terminal.qsf import validate_oos as vs, validate_open as vo, validate_pit as vp

ROOT = Path(__file__).resolve().parent.parent


def test_one_frozen_hypothesis_on_live_style_scores():
    assert vs.HYPOTHESIS == ("LONG_TERM", "A", 252)
    assert (vs.STRICT_FIRST, vs.STRICT_LAST) == ("2011-03-01", "2012-12-31")
    assert vs.STRICT_FIRST in (ROOT / "reports" / "QSF_OOS_TEST_PROTOCOL.md").read_text(encoding="utf-8")


def test_old_universe_is_verified_and_separate():
    old = vs.load_old(ROOT)
    assert all(v["cik"].isdigit() and v["sec_name"] and v["ticker"] for v in old.values())
    assert not {v["ticker"] for v in old.values()} & set(vo.load_universe(ROOT))
    assert not {v["ticker"] for v in old.values()} & set(vp.RECOVERED)


def test_alias_keeps_an_old_company_apart_from_the_current_ticker_holder():
    keys, snaps = vp.load_history([["2012-01-03", "DOW,MMM"], ["2013-01-02", "MMM"]])
    old = {"DOW~OLD": {"ticker": "DOW"}, "SHLD": {"ticker": "SHLD"}}
    m = vs.old_members(lambda d: ["MMM"], keys, snaps, old)
    assert m("2012-06-01") == ["MMM", "DOW~OLD"]
    assert m("2013-06-01") == ["MMM"]


def test_scoring_has_no_returns_in_its_coverage():
    keys, snaps = vp.load_history([["2012-01-03", "A,B,C,D"]])
    cov = vs.coverage([{"i": 0, "t": "A", "LONG_TERM|A": 60.0}, {"i": 0, "t": "B"}], ["2012-02-01"], keys, snaps)
    assert cov == {"2012-02-01": {"members": 4, "scored": 2, "usable": 1}}


def test_window_filter():
    recs = [{"i": 0}, {"i": 1}, {"i": 2}]
    assert vs.in_window(recs, ["2011-03-04", "2012-12-03", "2013-01-02"], "2011-03-01", "2012-12-31") == recs[:2]


def test_second_run_is_refused(tmp_path):
    report = tmp_path / vs.REPORT
    report.parent.mkdir(parents=True)
    report.write_text("{}")
    with pytest.raises(RuntimeError):
        vs.test_once(tmp_path)
