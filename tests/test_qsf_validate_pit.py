"""Point-in-time rerun: frozen list, membership by snapshot, sector parsing, price merge.  No network."""
import re
from pathlib import Path

import numpy as np

from terminal.qsf import validate, validate_pit as vp

ROOT = Path(__file__).resolve().parent.parent


def test_recovered_list_matches_the_committed_protocol():
    text = (ROOT / "reports" / "QSF_PIT_VALIDATION_PROTOCOL.md").read_text(encoding="utf-8")
    block = re.search(r"```\n(.*?)```", text, re.S).group(1).split()
    assert tuple(block) == vp.RECOVERED and len(vp.RECOVERED) == 95 == len(set(vp.RECOVERED))


def test_history_parses_any_order_and_dash_form():
    keys, snaps = vp.load_history([["date", "tickers"], ["2020-02-01", "BRK.B,AAL"], ["2020-01-01", '"AAL,GME"']])
    assert keys == ["2020-01-01", "2020-02-01"] and snaps[0] == {"AAL", "GME"} and snaps[1] == {"BRK-B", "AAL"}


def test_recovered_name_is_only_scored_while_listed():
    keys, snaps = vp.load_history([["2020-01-01", "AAL,GME"], ["2020-06-01", "AAL"]])
    m = vp.members_fn(lambda d: ["MMM"], keys, snaps, recovered=["AAL", "GME", "M"])
    assert m("2020-03-01") == ["MMM", "AAL", "GME"]
    assert m("2020-06-01") == ["MMM", "AAL"]             # removed names leave on the snapshot that drops them
    assert m("2019-12-31") == []


def test_nothing_is_scored_after_the_last_snapshot():
    keys, snaps = vp.load_history([["2020-01-01", "AAL"], ["2020-06-01", "AAL"]])
    m = vp.members_fn(lambda d: ["MMM"], keys, snaps, recovered=["AAL"])
    assert m("2020-06-01") == ["MMM", "AAL"]
    assert m("2020-06-02") == []


def test_sector_from_wikitext_row_and_old_name():
    row = "| {{NyseSymbol|AAL}} || [[American Airlines Group]] || [http://x reports] || Industrials || Airlines || Fort Worth || 2015-03-23 || 0000006201"
    assert vp.row_ticker(row) == "AAL" and vp.sector_of_row(row) == "Industrials"
    old = "\n| {{NasdaqSymbol|FTR}}\n| [[Frontier]]\n| [[Telecommunications Services]]\n| Integrated"
    assert vp.row_ticker(old) == "FTR" and vp.sector_of_row(old) == "Communication Services"
    assert vp.sector_of_row("| {{NYSE|X}} || Unknown thing") is None


def _npz(path, dates, symbols, value):
    n = (len(dates), len(symbols))
    np.savez(path, dates=np.array(dates), symbols=np.array(symbols), **{f: np.full(n, value) for f in validate.FIELDS})


def test_merge_keeps_the_axis_and_leaves_gaps_empty(tmp_path):
    a, b, out = tmp_path / "a.npz", tmp_path / "b.npz", tmp_path / "out.npz"
    _npz(a, ["2020-01-02", "2020-01-03", "2020-01-06"], ["SPY", "MMM"], 1.0)
    _npz(b, ["2020-01-03", "2020-01-07"], ["AAL", "MMM"], 2.0)
    res = vp.merge_prices(a, b, out)
    assert res["added"] == ["AAL"]
    z = np.load(out)
    assert [str(s) for s in z["symbols"]] == ["SPY", "MMM", "AAL"] and len(z["dates"]) == 3
    c = z["close"]
    assert np.isnan(c[0, 2]) and c[1, 2] == 2.0 and np.isnan(c[2, 2])     # a missing day is never filled
    assert (c[:, 1] == 1.0).all()                                          # an existing column is untouched


def test_coverage_counts_recovered_share():
    keys, snaps = vp.load_history([["2020-01-01", "A,B,C,D"]])
    recs = [{"i": 0, "t": "A"}, {"i": 0, "t": "B", "recovered": True}]
    cov = vp.coverage(recs, ["2020-01-02"], keys, snaps)["2020"]
    assert cov["evaluations"] == 2 and cov["recovered"] == 1 and cov["share_of_index"] == 0.5
