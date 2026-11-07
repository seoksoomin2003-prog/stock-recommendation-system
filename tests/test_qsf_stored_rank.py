"""The stock screen and held signals read the scan's universe rank, so one stock shows one score.  The scan and the ledger stay as they were."""
import gzip
import json
from pathlib import Path

import pytest

from terminal.qsf import config, factors
from terminal.qsf.service import QSF, _rank_in, _six_month_return
from tests.test_qsf import NOW, SESSION, FakeSrc, FakeTerm, bars

TICKERS = [f"T{k}" for k in range(25)]
ROOT = Path(__file__).resolve().parents[1]


class Src(FakeSrc):
    """Every stock has its own six-month return, and it differs from what the benchmark formula would give."""

    def yahoo_history(self, symbols, period="2y"):
        got = super().yahoo_history(symbols, period)
        for s in symbols:
            if s.startswith("T") and s[1:].isdigit():
                got[s] = bars(drift=-0.002 + 0.0004 * int(s[1:]))
            elif s == "OUT":
                got[s] = bars(drift=0.0003)
            elif s == "NEW":
                got[s] = bars(n=100)
        return got


class HeldTerm(FakeTerm):
    def _book(self, market="US"):
        return [], {"status": "OK"}, {"positions": {"T20": {"avg": 10.0, "opened": "2026-10-01", "qty": 1.0, "style": "SWING"}}, "plans": {"T20": {"stop": 1.0, "target": 1000.0}}}


def service(tmp_path, term=FakeTerm):
    return QSF(tmp_path, src=Src(), now=lambda: NOW, terminal=term())


def scan_scores(res):
    return {(r["ticker"], r["strategy"]): r["score"] for r in res["rows"]}


def rank_file(q, market="US"):
    return q.dir / f"ranks_{market}.json"


def factor(card, fid="relative_strength"):
    return next(f for f in card["factors"] if f["factor"] == fid)


def test_scan_saves_the_returns_it_ranked(tmp_path):
    q = service(tmp_path)
    q.scan("US", tickers=TICKERS)
    d = json.loads(rank_file(q).read_text(encoding="utf-8"))
    assert d["market"] == "US" and d["session"] == SESSION and set(d["returns"]) == set(TICKERS)
    assert d["returns"]["T24"] > d["returns"]["T0"]


def test_a_dry_run_or_a_refused_scan_leaves_no_rank_file(tmp_path):
    q = service(tmp_path)
    q.scan("US", tickers=TICKERS, record=False)
    assert not rank_file(q).exists()

    class Late(Src):
        def yahoo_history(self, symbols, period="2y"):
            return {s: bars(end="2026-11-03") for s in symbols}
    q2 = QSF(tmp_path / "b", src=Late(), now=lambda: NOW, terminal=FakeTerm())
    assert q2.scan("US", tickers=TICKERS)["status"] == "DATA_NOT_READY"
    assert not rank_file(q2).exists()


def test_too_few_names_write_no_file_and_the_screen_says_no_scan(tmp_path):
    q = service(tmp_path)
    q.scan("US", tickers=TICKERS[:10])
    assert not rank_file(q).exists()
    assert q.evaluate("T3")["rank_basis"] == "NO_SCAN"


def test_every_member_shows_the_scan_score_on_the_screen(tmp_path):
    q = service(tmp_path)
    scanned = scan_scores(q.scan("US", tickers=TICKERS))
    for t in TICKERS:
        d = q.evaluate(t)
        assert d["rank_basis"] == "UNIVERSE"
        for s in config.STRATEGIES:
            assert d["cards"][s]["score"] == scanned[(t, s)]


def test_the_gap_is_real_before_a_scan_and_the_screen_says_so(tmp_path):
    q = service(tmp_path)
    before = q.evaluate("T20")
    assert before["rank_basis"] == "NO_SCAN"
    assert factor(before["cards"]["SWING"])["raw"].get("percentile") is None
    scanned = scan_scores(q.scan("US", tickers=TICKERS))
    assert before["cards"]["SWING"]["score"] != scanned[("T20", "SWING")]


def test_a_rank_of_another_session_is_not_used(tmp_path):
    q = service(tmp_path)
    q.scan("US", tickers=TICKERS)
    d = json.loads(rank_file(q).read_text(encoding="utf-8"))
    rank_file(q).write_text(json.dumps({**d, "session": "2026-11-03"}), encoding="utf-8")
    got = q.evaluate("T20")
    assert got["rank_basis"] == "NO_SCAN" and factor(got["cards"]["SWING"])["raw"].get("percentile") is None


def test_the_other_market_file_is_not_used(tmp_path):
    q = service(tmp_path)
    q.scan("US", tickers=TICKERS)
    d = json.loads(rank_file(q).read_text(encoding="utf-8"))
    assert q._read_ranks("KR", SESSION) is None
    rank_file(q).write_text(json.dumps({**d, "market": "KR"}), encoding="utf-8")
    assert q._read_ranks("US", SESSION) is None


@pytest.mark.parametrize("text", ["{not json", "[]", '{"market": "US", "session": "2026-11-04"}', '{"market": "US", "session": "2026-11-04", "returns": {"T1": "x"}}',
                                  '{"market": "US", "session": "2026-11-04", "returns": {"T1": 0.1}}', '{"market": "US", "session": "2026-11-04", "returns": [1, 2]}'])
def test_a_broken_file_counts_as_no_scan(tmp_path, text):
    q = service(tmp_path)
    q.dir.mkdir(parents=True, exist_ok=True)
    rank_file(q).write_text(text, encoding="utf-8")
    assert q.evaluate("T3")["rank_basis"] == "NO_SCAN"


def test_nan_in_the_file_counts_as_no_scan(tmp_path):
    q = service(tmp_path)
    q.dir.mkdir(parents=True, exist_ok=True)
    rets = {t: 0.1 for t in TICKERS}
    rets["T1"] = float("nan")
    rank_file(q).write_text(json.dumps({"market": "US", "session": SESSION, "returns": rets}), encoding="utf-8")
    assert q.evaluate("T3")["rank_basis"] == "NO_SCAN"


def test_a_stock_outside_the_scan_is_placed_in_the_same_distribution(tmp_path):
    q = service(tmp_path)
    q.scan("US", tickers=TICKERS)
    rets = json.loads(rank_file(q).read_text(encoding="utf-8"))["returns"]
    d = q.evaluate("OUT")
    assert d["rank_basis"] == "OUTSIDE_UNIVERSE"
    want = _rank_in(sorted(rets.values()), _six_month_return(bars(drift=0.0003)))
    assert 0 < want < 1 and factor(d["cards"]["SWING"])["normalized"] == pytest.approx(want)
    assert "OUT" not in json.loads(rank_file(q).read_text(encoding="utf-8"))["returns"]


def test_short_history_gets_the_same_score_as_the_scan_and_says_why(tmp_path):
    q = service(tmp_path)
    names = TICKERS + ["NEW"]
    scanned = scan_scores(q.scan("US", tickers=names))
    d = q.evaluate("NEW")
    assert d["rank_basis"] == "SHORT_HISTORY"
    assert d["cards"]["SWING"]["score"] == scanned[("NEW", "SWING")]


def test_the_rank_comes_from_the_scan_even_if_the_screen_gets_other_prices(tmp_path):
    q = service(tmp_path)
    scanned = scan_scores(q.scan("US", tickers=TICKERS))
    rets = json.loads(rank_file(q).read_text(encoding="utf-8"))["returns"]
    rets["T20"] = max(rets.values()) + 1
    rank_file(q).write_text(json.dumps({"market": "US", "session": SESSION, "returns": rets}), encoding="utf-8")
    c = q.evaluate("T20")["cards"]["SWING"]
    assert factor(c)["normalized"] == 1.0 and c["score"] != scanned[("T20", "SWING")]


def test_the_scan_does_not_read_the_stored_file(tmp_path):
    clean = scan_scores(service(tmp_path / "a").scan("US", tickers=TICKERS))
    q = service(tmp_path / "b")
    q.dir.mkdir(parents=True, exist_ok=True)
    rank_file(q).write_text(json.dumps({"market": "US", "session": SESSION, "returns": {t: 9.9 - k for k, t in enumerate(TICKERS)}}), encoding="utf-8")
    assert scan_scores(q.scan("US", tickers=TICKERS)) == clean


def test_a_second_scan_keeps_the_ledger_and_the_ledger_has_no_new_field(tmp_path):
    q = service(tmp_path)
    q.scan("US", tickers=TICKERS)
    again = q.scan("US", tickers=TICKERS)
    assert again["ledger"]["recorded"] == 0 and q.ledger.verify()["status"] == "OK"
    row = q.ledger.read_index()["rows"][0]
    with gzip.open(q.ledger.dir / row["file"], "rt", encoding="utf-8") as fh:
        rec = json.loads(fh.readline())
    assert "rank_basis" not in rec and rec["model_version"] == config.MODEL_VERSION


def test_scan_rows_have_no_new_field(tmp_path):
    res = service(tmp_path).scan("US", tickers=TICKERS)
    assert "rank_basis" not in res["rows"][0]


def test_held_signal_matches_the_scan_and_exit_does_not_depend_on_the_rank(tmp_path):
    q = service(tmp_path, HeldTerm)
    before = q.signal("T20", 5.0, 15.0)
    assert before["rank_basis"] == "NO_SCAN"
    scanned = scan_scores(q.scan("US", tickers=TICKERS))
    after = q.signal("T20", 5.0, 15.0)
    assert after["rank_basis"] == "UNIVERSE" and after["score"] == scanned[("T20", "SWING")] and after["score"] != before["score"]
    assert after["exit"]["action"] == before["exit"]["action"] and after["exit"]["conditions"] == before["exit"]["conditions"]


def test_the_factor_formula_itself_is_unchanged():
    t = {"rel_63": 0.05, "rel_126": 0.05, "date": SESSION}
    assert factors.relative_strength({"tech": t, "rs_rank": 0.8, "bench_name": "SPY"})["normalized"] == pytest.approx(0.8)
    assert factors.relative_strength({"tech": t, "rs_rank": None, "bench_name": "SPY"})["normalized"] == pytest.approx(0.2 / 0.35)


def test_six_month_return_needs_127_bars():
    assert _six_month_return(bars(n=126)) is None
    r = bars(n=127)
    assert _six_month_return(r) == pytest.approx(r[-1]["adj_close"] / r[0]["adj_close"] - 1)
    assert _six_month_return([{**x, "adj_close": None} for x in r]) is None


def test_screens_tell_the_basis_of_the_rank():
    qsf = (ROOT / "terminal/static/qsf.js").read_text(encoding="utf-8")
    assert "QSF_RANK_NOTE" in qsf and "d.rank_basis" in qsf
    for basis in ("NO_SCAN", "OUTSIDE_UNIVERSE", "SHORT_HISTORY"):
        assert basis in qsf
    assert "s.rank_basis" in (ROOT / "terminal/static/portfolio.js").read_text(encoding="utf-8")
