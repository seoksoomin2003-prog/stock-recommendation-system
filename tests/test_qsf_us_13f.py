"""13F breadth test: only holdings count, a quarter is read as known on its deadline, filers must report both quarters, securities are
tied by price alone, the value is not used on the deadline day, one run.  Synthetic files only; no network and no real security number."""
import json
import zipfile
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from terminal.qsf import research_us_13f as m

SUB = ["ACCESSION_NUMBER", "FILING_DATE", "SUBMISSIONTYPE", "CIK", "PERIODOFREPORT"]
COVER = ["ACCESSION_NUMBER", "REPORTCALENDARORQUARTER", "ISAMENDMENT", "AMENDMENTNO", "AMENDMENTTYPE"]
INFO = ["ACCESSION_NUMBER", "INFOTABLE_SK", "NAMEOFISSUER", "TITLEOFCLASS", "CUSIP", "FIGI", "VALUE", "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL"]
MON = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
A, B, C = "AAAAAAAA1", "BBBBBBBB2", "CCCCCCCC3"


def sec(day):
    d = date.fromisoformat(day)
    return f"{d.day:02d}-{MON[d.month - 1]}-{d.year}"


def filing(acc, filed, cik, period, kind="13F-HR", amend="", rows=()):
    """rows: (security, value, shares[, type[, putcall]])"""
    return {"sub": [acc, sec(filed), kind, f"{cik:010d}", sec(period)], "cover": [acc, sec(period), "Y" if amend else "N", "", amend],
            "rows": [[acc, "1", "ISSUER", "COM", r[0], "", str(r[1]), str(r[2]), r[3] if len(r) > 3 else "SH", r[4] if len(r) > 4 else ""] for r in rows]}


def make_zip(path, filings, extra_info_lines=()):
    def tsv(head, rows):
        return "\n".join("\t".join(x) for x in [head] + rows) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("SUBMISSION.tsv", tsv(SUB, [f["sub"] for f in filings]))
        z.writestr("COVERPAGE.tsv", tsv(COVER, [f["cover"] for f in filings]))
        z.writestr("INFOTABLE.tsv", tsv(INFO, [r for f in filings for r in f["rows"]]) + "".join(extra_info_lines))
    return path


def weekdays(first, last):
    d, out = date.fromisoformat(first), []
    while d.isoformat() <= last:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_dates_and_kinds():
    assert m.iso("31-JUL-2026") == "2026-07-31" and m.iso("2026-07-31") == "2026-07-31"
    assert m.iso("31-XXX-2026") is None and m.iso("") is None and m.iso("30-FEB-2026") is None
    assert m.kind_of("13F-HR", "") == "O" and m.kind_of("13F-HR/A", "restatement") == "R" and m.kind_of("13F-HR/A", "NEW HOLDINGS") == "N"
    assert m.kind_of("13F-HR/A", "") == "X" and m.kind_of("13F-NT", "") is None


def test_only_holdings_are_read_and_old_values_are_thousands(tmp_path):
    z = make_zip(tmp_path / "a_form13f.zip", [
        filing("f1", "2022-11-01", 1, "2022-09-30", rows=[(A, 50, 1000), (A, 30, 1000, "SH", "PUT"), (B, 70, 1000, "PRN"), (B, 0, 10), (C, 5, 0), ("SHORT", 5, 5)]),
        filing("f2", "2023-02-01", 1, "2022-12-31", rows=[(A, 52000, 1000)]),
        filing("f3", "2022-11-01", 2, "2022-09-30", kind="13F-NT"),
        filing("f4", "2022-11-01", 3, "2022-08-31", rows=[(A, 50, 1000)]),
        filing("f5", "2013-05-01", 4, "2013-03-31", rows=[(A, 50, 1000)])], extra_info_lines=["f1\tbroken line\n"])
    codes = {}
    d = m.read_zip(z, codes)
    assert list(d["acc"]) == ["f1", "f2"] and list(d["kind"]) == ["O", "O"] and list(d["cik"]) == [1, 1]
    assert list(d["period"]) == ["2022-09-30", "2022-12-31"] and list(d["filed"]) == ["2022-11-01", "2023-02-01"]
    assert codes == {A: 0} and list(d["row_filing"]) == [0, 1]
    assert [round(float(x), 6) for x in d["row_ratio"]] == [50.0, 52.0]          # 50 thousand dollars / 1000 shares, then 52,000 dollars / 1000
    s = d["stats"]
    assert s["option_rows"] == 1 and s["principal_rows"] == 1 and s["zero_or_misnumbered_rows"] == 3 and s["rows_of_unused_filings"] == 2
    assert s["not_a_holdings_report"] == 1 and s["other_report_date"] == 2 and s["bad_width_INFOTABLE.TSV"] == 1


def window(filings):
    """The arrays `chosen` reads, from (acc, filed, kind, cik, period) tuples."""
    return {"acc": np.array([f[0] for f in filings]), "filed": np.array([f[1] for f in filings]), "kind": np.array([f[2] for f in filings]),
            "cik": np.array([f[3] for f in filings], dtype=np.int64), "period": np.array([f[4] for f in filings])}


def test_a_restatement_replaces_and_new_holdings_add():
    P, by = "2020-03-31", "2020-05-15"
    w = window([("a1", "2020-05-01", "O", 1, P), ("a2", "2020-05-05", "N", 1, P), ("a3", "2020-05-10", "R", 1, P), ("a4", "2020-05-12", "N", 1, P), ("a5", "2020-05-13", "X", 1, P),
                ("b1", "2020-05-01", "O", 2, P), ("b2", "2020-05-20", "R", 2, P),            # the restatement arrives after the cut-off
                ("c1", "2020-05-02", "N", 3, P),                                              # an addition with nothing to add to
                ("d1", "2020-05-01", "O", 4, "2019-12-31"),
                ("e1", "2020-05-15", "O", 5, P), ("e2", "2020-05-15", "R", 5, P)])            # same day: the later accession number
    assert m.chosen(w, P, by) == {2: 1, 3: 1, 5: 2, 10: 5}
    assert m.chosen(w, P, "2020-05-25")[6] == 2 and 5 not in m.chosen(w, P, "2020-05-25")


def test_the_deadline_moves_to_the_next_trading_day_and_the_value_starts_the_day_after():
    dates = weekdays("2014-10-01", "2015-06-30")
    dates.remove("2015-02-16")                                # a market holiday
    assert m.deadline("2014-12-31") == "2015-02-14" and m.cutoff("2014-12-31", dates) == "2015-02-17"
    assert m.cutoff("2015-03-31", dates) == "2015-05-15" and m.cutoff("2015-06-30", dates) is None
    assert m.period_ends("2014-07-01", "2013-06-30") == ["2013-06-30", "2013-09-30", "2013-12-31", "2014-03-31", "2014-06-30"]
    periods, cutoffs = ["2014-09-30", "2014-12-31", "2015-03-31"], ["2014-11-14", "2015-02-17", "2015-05-15"]
    assert m.quarter_on("2015-02-17", cutoffs, periods) is None            # the first quarter has no earlier one to compare with
    assert m.quarter_on("2015-02-18", cutoffs, periods) == 1 and m.quarter_on("2015-05-15", cutoffs, periods) == 1
    assert m.quarter_on("2015-05-18", cutoffs, periods) == 2 and m.quarter_on("2015-08-14", cutoffs, periods) == 2
    assert m.quarter_on("2015-08-17", cutoffs, periods) is None            # the next quarter's deadline has passed and nothing newer is known


def reduced(tmp_path, filings):
    make_zip(tmp_path / m.RAW / "x_form13f.zip", filings)
    assert m.reduce_all(tmp_path, log=lambda *_: None)["new"] == 1
    assert m.reduce_all(tmp_path, log=lambda *_: None)["new"] == 0             # a file already reduced is not read again
    return {c: n for n, c in enumerate(json.loads((tmp_path / m.CODES).read_text()))}


def test_holders_are_counted_among_filers_of_both_quarters_and_once_per_ticker(tmp_path):
    P0, P1 = "2020-03-31", "2020-06-30"
    fs = [filing("p1", "2020-05-01", 1, P0, rows=[(A, 10, 1)]), filing("n1", "2020-08-01", 1, P1, rows=[(A, 10, 1), (A, 5, 1), (B, 10, 1)]),     # two lines of A, and B is A's other number
          filing("p2", "2020-05-01", 2, P0, rows=[(C, 10, 1)]), filing("n2", "2020-08-01", 2, P1, rows=[(A, 10, 1)]),
          filing("p3", "2020-05-01", 3, P0, rows=[(A, 10, 1)]),                                                                               # reports the earlier quarter only
          filing("n4", "2020-08-01", 4, P1, rows=[(A, 10, 1)]),                                                                               # reports the later quarter only
          filing("p5", "2020-08-20", 5, P0, rows=[(A, 10, 1)]), filing("n5", "2020-08-01", 5, P1, rows=[(C, 10, 1)])]                         # the earlier quarter arrives after the cut-off
    codes = reduced(tmp_path, fs)
    sf = {"periods": np.array([P0, P1]), "cutoffs": np.array(["2020-05-15", "2020-08-14"])}
    b = m.count(tmp_path, sf, {codes[A]: 0, codes[B]: 0, codes[C]: 1}, 2, min_holders=1, log=lambda *_: None)
    assert int(b["common"][1]) == 2                                              # filers 1 and 2
    assert list(b["now"][1]) == [2, 0] and list(b["prev"][1]) == [1, 1] and int(b["several"][1]) == 1
    v = m.values(b, 1)
    assert v[0, 0] == pytest.approx(0.5) and v[0, 1] == pytest.approx(1.0) and v[0, 2] == pytest.approx(1.0)
    assert np.isnan(v[1]).all()                                                  # no holder now: empty, not zero
    late = m.count(tmp_path, {"periods": sf["periods"], "cutoffs": np.array(["2020-05-15", "2020-08-21"])}, {codes[A]: 0, codes[C]: 1}, 2, min_holders=1, log=lambda *_: None)
    assert int(late["common"][1]) == 3 and list(late["prev"][1]) == [2, 1]       # by a later cut-off filer 5's earlier quarter is known


def test_a_count_under_the_floor_is_empty():
    b = {"now": np.array([[0, 0], [60, 49]]), "prev": np.array([[0, 0], [50, 80]]), "common": np.array([0, 1000]), "min_holders": np.array(50)}
    v = m.values(b, 1)
    assert v[0, 0] == pytest.approx(0.01) and np.isnan(v[1]).all()


def test_the_implied_price_is_the_median_of_the_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "MIN_HOLDERS", 2)
    P = "2020-03-31"
    fs = [filing(f"h{k}", "2020-05-01", k, P, rows=[(A, v, 10)]) for k, v in ((1, 100), (2, 102), (3, 5000))] + [filing("s1", "2020-05-01", 9, P, rows=[(B, 10, 1)])]
    codes = reduced(tmp_path, fs)
    out = m.scan(tmp_path, weekdays("2020-01-01", "2020-06-30"), log=lambda *_: None)
    with np.load(tmp_path / m.SCAN) as z:
        last = len(z["periods"]) - 1
        assert str(z["periods"][last]) == P and str(z["cutoffs"][last]) == "2020-05-15"
        assert list(z[f"code_{last}"]) == [codes[A]] and list(z[f"holders_{last}"]) == [3] and float(z[f"price_{last}"][0]) == pytest.approx(10200.0)     # thousands before 2023; one wild filer does not move it; B has one holder
    q = out["quarters"][-1]
    assert q["filers"] == 4 and q["originals"] == 4 and q["securities_50_holders"] == 1


def scan_of(prices):
    """{security number: [price per quarter or None]} as the arrays `link` reads."""
    n = len(next(iter(prices.values())))
    out = {}
    for k in range(n):
        have = [(c, p[k]) for c, p in prices.items() if p[k] is not None]
        out[f"code_{k}"], out[f"price_{k}"] = np.array([c for c, _ in have], dtype=np.int32), np.array([p for _, p in have], dtype=float)
    return out


def test_a_security_is_tied_by_price_over_several_quarters():
    closes = [np.array([10.0, 10.03, 50.0, np.nan]), np.array([12.0, 12.05, 55.0, 7.0]), np.array([9.0, 9.04, 60.0, 8.0]), np.array([11.0, 11.05, 65.0, 9.0]), np.array([13.0, 13.02, 70.0, 10.0])]
    sf = scan_of({1: [10.0, 12.0, 9.0, 11.0, 13.0],             # ticker 0 exactly; ticker 1 is within the tolerance too, but further
                  2: [50.0, 55.0, 60.0, None, None],            # three quarters only
                  3: [None, 7.0, 8.0, 9.0, 10.0],               # four quarters of ticker 3
                  4: [50.0, 55.0, 60.0, 65.0, 99.0],            # four of five: under nine tenths
                  5: [10.03, 12.05, 9.04, 11.05, 13.02]})
    links, how = m.link(sf, closes, 0.005)
    assert links == {1: 0, 3: 3, 5: 1} and how["tickers_tied"] == 3 and how["tickers_with_several_securities"] == 0
    assert m.link(sf, closes, 0.0001)[0] == {1: 0, 3: 3, 5: 1}


def test_the_quoted_close_puts_later_splits_back():
    px = SimpleNamespace(dates=["2020-06-29", "2020-06-30", "2020-07-01"], symbols=["AAA", "BBB", "CCC"], data={"close": np.array([[1.0, 5.0, np.nan], [25.0, 5.0, np.nan], [26.0, 6.0, 3.0]])})
    splits = {"AAA": [["2020-08-31", 4.0], ["2019-01-02", 2.0]]}
    assert list(m.quoted_close(px, splits, "2020-06-30"))[:2] == [100.0, 5.0] and np.isnan(m.quoted_close(px, splits, "2020-06-30")[2])
    assert m.quoted_close(px, {}, "2020-06-28").tolist() != m.quoted_close(px, {}, "2020-06-28").tolist()            # before the history: all empty


def test_fill_needs_the_average_and_every_year():
    def f(shares):
        n = len(shares)
        t = np.full((n, 40, 3), np.nan, dtype=np.float32)
        for k, s in enumerate(shares):
            t[k, :int(round(s * 40)), 0] = 1.0
        return {"tensor": t, "quarter": np.ones(n, dtype=np.int32), "sample": np.full(n, 40), "rows": np.arange(n)}
    dates = ["2020-01-02", "2020-06-01", "2021-01-04", "2021-06-01"]
    assert m.fill(f([1.0, 1.0, 0.9, 0.9]), dates)["passes"]
    assert not m.fill(f([1.0, 1.0, 0.7, 0.8]), dates)["passes"]                  # one year under 80%
    assert not m.fill(f([0.9, 0.9, 0.8, 0.9]), dates)["passes"]                  # the average under 90%
    empty = f([1.0, 1.0, 1.0, 1.0])
    empty["sample"][3], empty["tensor"][3] = 0, np.nan                             # a day with no sample stock has no ratio: 0 of 0 is not 0%
    r = m.fill(empty, dates)
    assert r["passes"] and r["days"] == 3 and r["days_without_a_sample"] == 1 and r["by_year"]["2021"] == 1.0
    r = m.fill(f([1.0, 0.9, 1.0, 0.8]), dates)
    assert r["overall"] == pytest.approx(0.925) and r["by_year"] == {"2020": pytest.approx(0.95), "2021": pytest.approx(0.9)} and r["passes"]


@pytest.mark.parametrize("verdict,independent,b1,b2,want", [
    ("NO_EVIDENCE", True, True, True, "NO_EVIDENCE"), ("WEAK_POSITIVE_EVIDENCE", False, True, True, "A_NOT_INDEPENDENT"),
    ("WEAK_POSITIVE_EVIDENCE", True, True, False, "A_C_AND_B1"), ("WEAK_POSITIVE_EVIDENCE", True, False, True, "A_C_AND_B2"), ("WEAK_POSITIVE_EVIDENCE", True, False, False, "A_C_ONLY")])
def test_the_reading_is_fixed(verdict, independent, b1, b2, want):
    assert m.reading({"verdict": verdict}, independent, {"b1_top_beats_market": b1, "b2_avoiding_bottom_helps": b2}) == want


def test_money_conditions_need_both_periods_and_the_residual_needs_both_numbers():
    def period(top, spy, rest, everything):
        return {"periods": 5, "top": {"annual_net": top}, "spy": {"annual": spy}, "no_bottom": {"annual_net": rest}, "all_equal": {"annual_net": everything}}
    assert m.money_conditions({"a": period(0.2, 0.1, 0.12, 0.1), "b": period(0.2, 0.1, 0.12, 0.1)}) == {"b1_top_beats_market": True, "b2_avoiding_bottom_helps": True}
    assert m.money_conditions({"a": period(0.2, 0.1, 0.12, 0.1), "b": period(0.05, 0.1, 0.09, 0.1)}) == {"b1_top_beats_market": False, "b2_avoiding_bottom_helps": False}
    assert not m.money_conditions({"a": period(0.2, 0.1, 0.12, 0.1), "b": {"periods": 0}})["b1_top_beats_market"]
    assert m.condition_c({"ic": 0.02, "t": 2.24}) and not m.condition_c({"ic": 0.03, "t": 2.2}) and not m.condition_c({"ic": 0.019, "t": 5}) and not m.condition_c({"ic": None, "t": None})


def test_the_fixed_numbers_are_the_protocol_s():
    text = open(m.PROTOCOL, encoding="utf-8").read()
    assert (m.MIN_HOLDERS, m.TOLERANCE, m.TOLERANCE_FALLBACK, m.MIN_MATCH_QUARTERS, m.MIN_MATCH_SHARE, m.NW_LAG, m.DEADLINE_DAYS) == (50, 0.005, 0.02, 4, 0.9, 13, 45)
    assert (m.FILL_MIN, m.FILL_MIN_YEAR, m.HORIZONS, m.UNIT_CHANGE) == (0.90, 0.80, {"SWING_20": 20, "QUARTER_63": 63}, "2023-01-03")
    for words in ("50곳 이상", "0.5% 이내", "4개 분기 이상", "90% 이상", "시차는 13", "45일", "2023-01-03", "2013-11~2019-12", "한 번만 2%"):
        assert words in text


def test_too_little_data_ends_the_test_and_a_second_run_is_refused(tmp_path):
    (tmp_path / m.PREPARED).parent.mkdir(parents=True)
    (tmp_path / m.PREPARED).write_text(json.dumps({"status": "DATA_INSUFFICIENT", "fill": {"overall": 0.5, "passes": False}}), encoding="utf-8")
    out = m.run_once(tmp_path)
    assert out["status"] == "DATA_INSUFFICIENT" and json.loads((tmp_path / m.REPORT).read_text(encoding="utf-8"))["fill"]["overall"] == 0.5
    with pytest.raises(RuntimeError):
        m.run_once(tmp_path)
    with pytest.raises(RuntimeError):
        m.prepare(tmp_path)


def planted(tmp_path, monkeypatch, strength, seed=5):
    """A price history in which the stocks with the higher value of a quarter drift up for that quarter, by `strength`."""
    from terminal.qsf import validate
    rng = np.random.default_rng(seed)
    dates = weekdays("2018-01-01", "2021-12-31")
    n_sym, block = 80, 65
    symbols = [f"S{j:02d}" for j in range(n_sym)] + ["SPY"]
    rows = list(range(260, len(dates) - 1, 5))
    signal = np.zeros((len(dates), n_sym))
    for start in range(0, len(dates), block):
        signal[start:start + block] = rng.normal(size=n_sym)
    ret = rng.normal(0, 0.01, size=(len(dates), n_sym)) + strength * np.roll(signal, 1, axis=0)
    close = 50 * np.exp(np.cumsum(ret, axis=0))
    spy = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, size=len(dates))))[:, None]
    close = np.hstack([close, spy])
    path = tmp_path / "px.npz"
    np.savez(path, dates=np.array(dates), symbols=np.array(symbols), open=close, high=close, low=close, close=close, adj_close=close, volume=np.full(close.shape, 1e6))
    px = validate.Prices(path)
    tensor = np.full((len(rows), len(symbols), 3), np.nan, dtype=np.float32)
    quarter, age = np.zeros(len(rows), dtype=np.int32), np.zeros(len(rows), dtype=np.int32)
    for n, i in enumerate(rows):
        tensor[n, :n_sym, :] = signal[i][:, None]
        quarter[n], age[n] = i // block, i % block
    (tmp_path / m.FEATURES).parent.mkdir(parents=True)
    np.savez(tmp_path / m.FEATURES, rows=np.array(rows), tensor=tensor, quarter=quarter, age=age, sample=np.full(len(rows), n_sym))
    (tmp_path / m.PREPARED).parent.mkdir(parents=True)
    (tmp_path / m.PREPARED).write_text(json.dumps({"status": "PREPARED_OK", "tolerance_used": 0.005, "fill": {"overall": 1.0, "passes": True}}), encoding="utf-8")
    size = np.tile(np.r_[rng.random(n_sym), np.nan].astype(np.float32), (len(rows), 1))
    monkeypatch.setattr(m, "_load", lambda base: (tmp_path, px, rows, None, None, None, {s: "X" for s in symbols}, {}))
    monkeypatch.setattr(m, "_controls", lambda *a: {"size": size})
    return px, rows


def test_the_whole_run_finds_a_planted_effect_and_refuses_a_second_time(tmp_path, monkeypatch):
    planted(tmp_path, monkeypatch, 0.002)
    out = m.run_once(tmp_path, log=lambda *_: None)
    s = out["scores"]["BREADTH"]["SWING_20"]
    assert out["status"] == "TESTED" and s["verdict"] == "WEAK_POSITIVE_EVIDENCE" and s["lag"] == 13 and s["ic"] > 0.1
    assert s["t"] != s["t_usual_lag"] and s["quarters"]["n"] >= 8 and s["quarters"]["t_simple"] > 2
    assert out["partial"]["SWING_20"]["c_independent"] and out["conditions"] == {"b1_top_beats_market": True, "b2_avoiding_bottom_helps": True}
    assert out["readings"] == {"SWING_20": "A_C_AND_B1", "QUARTER_63": "A_C_AND_B1"}
    assert set(out["scores"]) == {"BREADTH", "BREADTH_RESIDUAL", "BREADTH_REL", "BREADTH_LEVEL", "BREADTH_FRESH", "BREADTH_OLDER"} and set(s) >= {"early", "late", "top_excess", "spread_net"}
    assert out["money_20d"]["2013_2019"]["periods"] > 0 and out["money_20d"]["2020_on"]["periods"] > 0 and "LONG_252" in out["scores"]["BREADTH"]
    assert json.loads((tmp_path / m.REPORT).read_text(encoding="utf-8"))["readings"] == out["readings"]
    with pytest.raises(RuntimeError):
        m.run_once(tmp_path)


def test_the_whole_run_finds_nothing_when_nothing_is_planted(tmp_path, monkeypatch):
    planted(tmp_path, monkeypatch, 0.0)
    out = m.run_once(tmp_path, log=lambda *_: None)
    assert out["readings"] == {"SWING_20": "NO_EVIDENCE", "QUARTER_63": "NO_EVIDENCE"}
    assert abs(out["scores"]["BREADTH"]["SWING_20"]["ic"]) < 0.03
