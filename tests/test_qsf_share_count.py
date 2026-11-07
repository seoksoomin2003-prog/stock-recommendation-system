"""Share counts behind market value: all classes in the US, KRX listed shares in Korea.  No network."""
import gzip
import json

import pytest

from terminal.qsf import fundamentals as f, krx_history as kh


def annual(val):
    return {"shares_avg": [{"end": "2025-12-31", "val": val}]}


def test_a_multi_class_company_uses_the_total_when_sec_agrees():
    info = {"sharesOutstanding": 5.0e9, "marketCap": 3.5e12}
    assert f.us_total_shares(info, 300.0, annual(12.0e9)) == pytest.approx(3.5e12 / 300)


def test_a_single_class_company_keeps_yahoos_count():
    info = {"sharesOutstanding": 5.0e9, "marketCap": 1.5e12}
    assert f.us_total_shares(info, 300.0, annual(5.0e9)) == 5.0e9


def test_a_stale_market_value_alone_does_not_trigger_it():
    info = {"sharesOutstanding": 1.0e8, "marketCap": 4.9e10}       # ROK: Yahoo and SEC agree, price fell after the value was stored
    assert f.us_total_shares(info, 370.0, annual(1.1e8)) == 1.0e8


def test_without_sec_figures_yahoos_own_price_is_needed():
    info = {"sharesOutstanding": 1.0e9, "marketCap": 1.5e12}
    assert f.us_total_shares(info, 1000.0, {}) == 1.0e9
    assert f.us_total_shares({**info, "currentPrice": 1000.0}, 900.0, {}) == pytest.approx(1.5e9)


def test_yahoos_own_price_is_preferred_for_the_total():
    info = {"sharesOutstanding": 5.0e9, "marketCap": 3.5e12, "currentPrice": 350.0}
    assert f.us_total_shares(info, 300.0, annual(12.0e9)) == pytest.approx(1.0e10)


def test_missing_values_change_nothing():
    assert f.us_total_shares({}, 10.0) is None
    assert f.us_total_shares({"sharesOutstanding": 7.0}, 10.0) == 7.0
    assert f.us_total_shares({"sharesOutstanding": 7.0, "marketCap": 100.0}, None) == 7.0


def _day(root, day, kospi, kosdaq):
    for board, rows in (("KOSPI", kospi), ("KOSDAQ", kosdaq)):
        p = kh.path_of(root, board, day)
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8") as fh:
            json.dump(rows, fh)


def row(code, shares):
    return [code] + [None] * 10 + [shares]


def test_listed_shares_come_from_the_newest_full_day(tmp_path):
    _day(tmp_path, "2026-11-05", [row("000010", "1,000")], [row("000020", "2000")])
    _day(tmp_path, "2026-11-06", [row("000010", "1,500")], [])              # not published in full
    assert kh.listed_shares(tmp_path, "2026-11-06") == {"000010": 1000.0, "000020": 2000.0}


def test_a_later_day_is_never_read_and_an_old_snapshot_is_not_used(tmp_path):
    _day(tmp_path, "2026-11-10", [row("000010", "9")], [row("000020", "9")])
    assert kh.listed_shares(tmp_path, "2026-11-09") == {}
    assert kh.listed_shares(tmp_path, "2026-11-25") == {}
    assert kh.listed_shares(tmp_path, "2026-11-11") == {"000010": 9.0, "000020": 9.0}
