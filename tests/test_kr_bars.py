"""Korean bars rebuilt from KRX daily snapshots (QSF-1.1.8)."""
import gzip
import json
from datetime import date

import pytest

from terminal.qsf import kr_bars

DAYS = ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"]


def row(code, o, h, lo, c, rate, vol):
    return [code, "이름", "", str(o), str(h), str(lo), str(c), f"{rate:.2f}", str(vol), "0", "0", "0"]


def write(base, by_day):
    for day, rows in by_day.items():
        for board in kr_bars.BOARDS:
            p = base / kr_bars.KRX / board / f"{day}.json.gz"
            p.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(p, "wt", encoding="utf-8") as fh:
                json.dump(rows if board == "KOSPI" else [], fh)


def ybar(day, c, adj=None, vol=100.0):
    return {"date": day, "open": c, "high": c, "low": c, "close": c, "adj_close": adj if adj is not None else c, "volume": vol}


@pytest.fixture
def split_case(tmp_path):
    # a 1:5 split on 10-28: raw 10,100 -> 2,040 is a +1% day from the base price 2,020
    write(tmp_path, {
        "2026-10-26": [row("000010", 10000, 10000, 10000, 10000, 0.0, 50)],
        "2026-10-27": [row("000010", 10000, 10200, 9900, 10100, 1.0, 60)],
        "2026-10-28": [row("000010", 2030, 2050, 2020, 2040, 0.99, 300)],
        "2026-10-29": [row("000010", 0, 0, 0, 2060, 0.98, 0)],            # a halted-looking day: no trade listed
    })
    return tmp_path


def test_rate_chain_adjusts_a_split_without_another_source(split_case):
    pan = kr_bars.panel(split_case, date(2026, 11, 9))
    yahoo = [ybar("2026-10-26", 2000), ybar("2026-10-27", 2000), ybar("2026-10-29", 2060)]       # a stale and a missing day
    bars, info = kr_bars.rebuild("000010", yahoo, pan)
    assert info["source"] == "KRX" and info["tail_days"] == 0 and [b["date"] for b in bars] == DAYS
    assert [round(b["close"], 1) for b in bars] == [pytest.approx(2000.0, abs=1), pytest.approx(2020.0, abs=1), 2040.0, 2060.0]
    assert bars[1]["volume"] == pytest.approx(300, rel=0.01)                  # 60 old shares are 300 new ones
    assert bars[1]["high"] == pytest.approx(2040, rel=0.01) and bars[1]["low"] == pytest.approx(1980, rel=0.01)
    assert bars[3]["open"] == bars[3]["high"] == bars[3]["low"] == 2060.0 and bars[3]["volume"] == 0


def test_dividend_ratio_from_yahoo_is_kept(split_case):
    pan = kr_bars.panel(split_case, date(2026, 11, 9))
    yahoo = [ybar("2026-10-26", 2000, adj=1900), ybar("2026-10-28", 2040, adj=2040)]
    bars, _ = kr_bars.rebuild("000010", yahoo, pan)
    assert bars[0]["adj_close"] / bars[0]["close"] == pytest.approx(0.95) and bars[1]["adj_close"] / bars[1]["close"] == pytest.approx(0.95)
    assert bars[2]["adj_close"] == pytest.approx(bars[2]["close"])


def test_days_krx_has_not_published_come_from_yahoo_on_todays_basis(split_case):
    pan = kr_bars.panel(split_case, date(2026, 11, 9))
    yahoo = [ybar("2026-10-29", 2060), {**ybar("2026-10-30", 2100), "high": 2110.0, "low": 2050.0}]
    bars, info = kr_bars.rebuild("000010", yahoo, pan)
    assert info["source"] == "KRX+YAHOO" and info["tail_days"] == 1 and bars[-1]["date"] == "2026-10-30"
    assert bars[-1]["close"] == pytest.approx(2100) and bars[-1]["high"] == pytest.approx(2110) and bars[-2]["close"] == pytest.approx(2060)


def test_a_split_inside_the_tail_puts_history_on_the_new_basis(split_case):
    pan = kr_bars.panel(split_case, date(2026, 11, 9))
    yahoo = [ybar("2026-10-29", 1030), ybar("2026-10-30", 1050)]        # Yahoo already halved everything for a 2:1 split on 10-30
    bars, _ = kr_bars.rebuild("000010", yahoo, pan)
    assert bars[-1]["close"] == pytest.approx(1050) and bars[-2]["close"] == pytest.approx(1030) and bars[0]["close"] == pytest.approx(1000, abs=1)


def test_unknown_code_and_no_snapshots_keep_yahoo(split_case, tmp_path_factory):
    pan = kr_bars.panel(split_case, date(2026, 11, 9))
    yahoo = [ybar("2026-10-29", 5000)]
    assert kr_bars.rebuild("999999", yahoo, pan) == (yahoo, {"source": "YAHOO", "reason": "KRX 일별 자료에 없는 종목"})
    empty = tmp_path_factory.mktemp("empty")
    assert kr_bars.panel(empty, date(2026, 11, 9)) is None and kr_bars.rebuild("000010", yahoo, None)[1]["source"] == "YAHOO"


def test_history_before_the_listing_is_dropped(tmp_path):
    write(tmp_path, {"2026-10-28": [row("000020", 2000, 2000, 1800, 1900, -5.0, 10)], "2026-10-29": [row("000020", 1900, 2000, 1900, 1950, 2.63, 10)]})
    pan = kr_bars.panel(tmp_path, date(2026, 11, 9))
    yahoo = [ybar("2026-10-26", 700), ybar("2026-10-27", 710), ybar("2026-10-28", 1900), ybar("2026-10-29", 1950)]
    bars, info = kr_bars.rebuild("000020", yahoo, pan)
    assert [b["date"] for b in bars] == ["2026-10-28", "2026-10-29"] and info["dropped_yahoo_days"] == 2


def test_panel_cache_is_rebuilt_when_a_day_arrives(split_case):
    first = kr_bars.panel(split_case, date(2026, 11, 9))
    assert (split_case / kr_bars.CACHE).exists() and first["dates"] == DAYS
    write(split_case, {"2026-10-30": [row("000010", 2060, 2080, 2050, 2070, 0.49, 100)]})
    again = kr_bars.panel(split_case, date(2026, 11, 9))
    assert again["dates"][-1] == "2026-10-30" and isinstance(again["dates"][0], str)
    (split_case / kr_bars.KRX / "KOSDAQ" / "2026-10-30.json.gz").unlink()                    # half a day is not a day
    assert kr_bars.panel(split_case, date(2026, 11, 9))["dates"][-1] == "2026-10-29"


def test_summary_counts_sources():
    got = kr_bars.summary({"A": {"source": "KRX", "krx_last": "2026-10-29", "dropped_yahoo_days": 1}, "B": {"source": "YAHOO"}})
    assert got == {"stocks": 2, "by_source": {"KRX": 1, "YAHOO": 1}, "krx_last": "2026-10-29", "dropped_yahoo_days": 1}
