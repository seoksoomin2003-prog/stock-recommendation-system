"""Open-archive rerun: rebuilding old Yahoo files, delisting values, membership.  No network."""
import csv
import io
import json
import tarfile
from pathlib import Path

import numpy as np
import pytest

from terminal.qsf import open_prices as op, validate, validate_open as vo, validate_pit

ROOT = Path(__file__).resolve().parent.parent


def row(c, a=None, o=None, v=100):
    a = c if a is None else a
    return {"open": str(o or c), "high": str(c), "low": str(c), "close": str(c), "volume": str(v), "adj_close": str(a)}


def test_universe_is_frozen_and_separate_from_earlier_groups():
    u = vo.load_universe(ROOT)
    assert len(u) >= 100 and all(v["cik"].isdigit() and v["sec_name"] for v in u.values())
    assert not set(u) & set(validate_pit.RECOVERED)
    assert {"KORS", "CTL", "LB"} <= set(vo.SAME_COMPANY)


def test_split_is_found_and_ohlc_is_put_on_todays_basis():
    # 2-for-1 on the 3rd: raw close halves, the adjusted close does not move.
    s = op.build_series([{"2020-01-02": row(100, 50), "2020-01-03": row(52, 52)}])
    assert s["splits"] == [("2020-01-03", 2.0)]
    assert s["rows"][0]["close"] == 50 and s["rows"][1]["close"] == 52


def test_dividend_is_not_a_split_and_total_return_keeps_it():
    s = op.build_series([{"2020-01-02": row(100, 99), "2020-01-03": row(100, 100)}])
    assert s["splits"] == []
    r = s["rows"]
    assert r[1]["adj_close"] / r[0]["adj_close"] == pytest.approx(100 / 99) and r[0]["close"] == 100


def test_returns_chain_across_files_with_different_adjustment_bases():
    # Each file is adjusted only to its own day; the second file rebases the 3rd after a dividend on the 6th.
    f1 = {"2020-01-02": row(100, 100), "2020-01-03": row(110, 110)}
    f2 = {"2020-01-03": row(110, 108), "2020-01-06": row(110, 110)}
    r = op.build_series([f1, f2])["rows"]
    assert [x["date"] for x in r] == ["2020-01-02", "2020-01-03", "2020-01-06"]
    assert r[2]["adj_close"] / r[1]["adj_close"] == pytest.approx(110 / 108)
    assert r[1]["adj_close"] / r[0]["adj_close"] == pytest.approx(1.1)
    assert r[1]["close"] == 110


def test_a_missing_file_uses_raw_close_or_stops_on_a_big_jump():
    ok = op.build_series([{"2020-01-02": row(100), "2020-01-03": row(101)}, {"2020-01-07": row(102), "2020-01-08": row(103)}])
    assert ok["gaps"] == 1 and ok["rows"][2]["adj_close"] / ok["rows"][1]["adj_close"] == pytest.approx(102 / 101)
    bad = op.build_series([{"2020-01-02": row(100), "2020-01-03": row(101)}, {"2020-01-07": row(30), "2020-01-08": row(31)}])
    assert bad["stopped"] == "2020-01-07" and len(bad["rows"]) == 2


def test_missing_values_stay_missing():
    assert op.build_series([{"2020-01-02": row("")}])["rows"] == []


def test_archives_are_read_without_unpacking(tmp_path):
    body = io.BytesIO()
    with tarfile.open(fileobj=body, mode="w:gz") as t:
        text = "symbol,date,open,high,low,close,volume,adj_close\nAAA,2015-03-20,1,1,1,1,5,1\nZZZ,2015-03-20,1,1,1,1,5,1\n".encode()
        info = tarfile.TarInfo("prices.csv")
        info.size = len(text)
        t.addfile(info, io.BytesIO(text))
    outer = tmp_path / "repo.tar.gz"
    with tarfile.open(outer, "w:gz") as t:
        info = tarfile.TarInfo("repo/2015/20150320.tar.gz")
        info.size = len(body.getvalue())
        t.addfile(info, io.BytesIO(body.getvalue()))
    files = op.read_archives(outer, ["AAA"])
    assert list(files[0]) == ["AAA"] and sorted(p.name for p in tmp_path.iterdir()) == ["repo.tar.gz"]


def _px(tmp_path, closes, dates):
    syms = list(closes)
    arr = np.array([closes[s] for s in syms], dtype=float).T
    np.savez(tmp_path / "p.npz", dates=np.array(dates), symbols=np.array(syms), **{f: arr for f in validate.FIELDS})
    return vo.OpenPrices(tmp_path / "p.npz", ["OPN"])


DATES = ["2017-03-27", "2017-03-28", "2017-03-29", "2017-03-30", "2017-03-31", "2017-04-03"]


def test_exit_before_the_archive_ends_is_valued_at_last_close(tmp_path):
    px = _px(tmp_path, {"OPN": [10, 10, 12, np.nan, np.nan, np.nan], "SPY": [1, 1, 1, 1, 1, 1]}, DATES)
    assert px.forward(0, 4)[0] == pytest.approx(0.2)


def test_nothing_past_the_archive_end_even_if_it_had_a_price(tmp_path):
    px = _px(tmp_path, {"OPN": [10, 10, 10, 10, 10, 11], "SPY": [1, 1, 1, 1, 1, 2]}, DATES)
    f = px.forward(0, 5)
    assert np.isnan(f[0]) and f[1] == pytest.approx(1.0)


def test_early_panel_drops_every_name_past_the_archive_end(tmp_path):
    px = _px(tmp_path, {"OPN": [10] * 6, "SPY": [1, 1, 1, 1, 1, 2]}, DATES)
    px.early_only = True
    assert np.isnan(px.forward(0, 5)).all() and px.forward(0, 4)[1] == pytest.approx(0.0)


def test_no_entry_price_means_no_return(tmp_path):
    px = _px(tmp_path, {"OPN": [10, np.nan, 12, 12, 12, 12], "SPY": [1, 1, 1, 1, 1, 1]}, DATES)
    assert np.isnan(px.forward(0, 3)[0])


def test_members_stop_at_archive_end_and_keep_one_ticker_per_company():
    keys, snaps = validate_pit.load_history([["2017-01-03", "OPN,KORS,CPRI,LB"], ["2017-04-03", "OPN"]])
    m = vo.open_members(lambda d: ["MMM"], keys, snaps, ["OPN", "KORS", "LB"])
    assert m("2017-02-01") == ["MMM", "OPN", "LB"]      # KORS waits while CPRI is listed; LB stays since BBWI is not
    assert m("2017-04-03") == ["MMM"]


def test_merge_never_fills_a_gap(tmp_path):
    n = (2, 1)
    np.savez(tmp_path / "a.npz", dates=np.array(["2017-01-03", "2017-01-04"]), symbols=np.array(["SPY"]), **{f: np.ones(n) for f in validate.FIELDS})
    s = {"OPN": {"rows": [{"date": "2017-01-04", "open": 2.0, "high": 2.0, "low": 2.0, "close": 2.0, "adj_close": 2.0, "volume": None}]}}
    vo.merge_open(tmp_path / "a.npz", s, tmp_path / "o.npz")
    z = np.load(tmp_path / "o.npz")
    assert np.isnan(z["close"][0, 1]) and z["close"][1, 1] == 2.0 and np.isnan(z["volume"][1, 1])
