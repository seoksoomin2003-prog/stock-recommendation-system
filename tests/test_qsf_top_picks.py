"""Top three tracking: frozen once before the open, counted only when frozen in time, a missing price is never zero."""
import gzip
import json
from datetime import datetime, timezone

import pytest

from terminal.qsf import top_picks as tp
from terminal.qsf.ledger import Ledger

DAYS = ["2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16"]
SUNDAY = datetime(2026, 11, 8, 3, tzinfo=timezone.utc)


def row(t, score, strategy="SWING", **kw):
    return {"ticker": t, "name": t + " Inc", "strategy": strategy, "score": score, "action": "WATCH", "price": 10.0, "actionability": "ACTIONABLE",
            "data_date": "2026-11-06", **kw}


def latest(rows):
    return {"status": "REAL", "session": "2026-11-06", "model_version": "QSF-1.1.7", "rows": rows}


def snaps(tickers, bench="SPY"):
    return [{"ticker": t, "strategy": s, "benchmark": bench, "entry_session": "2026-11-09"} for t in tickers for s in ("SWING", "LONG_TERM")]


@pytest.fixture
def small(monkeypatch):
    monkeypatch.setitem(tp.MIN_ROWS, "US", 4)
    monkeypatch.setitem(tp.MIN_ROWS, "KR", 4)


def universe():
    out = []
    for i, t in enumerate(["A", "B", "C", "D", "E"]):
        out += [row(t, 60 + i), row(t, 50 + i, "LONG_TERM")]
    return out


def test_build_takes_the_three_highest_scores_and_skips_unusable_rows(small):
    rows = universe() + [row("Z", 99, actionability="INSUFFICIENT_DATA"), row("Y", 98, data_date="2026-11-05"), row("X", None)]
    rows.append(row("F", 64))                                   # ties E: the code decides
    doc = tp.build(latest(rows), snaps("ABCDEFXYZ"), "US", SUNDAY)
    sw = doc["strategies"]["SWING"]
    assert [p["ticker"] for p in sw["top"]] == ["E", "F", "D"] and [p["rank"] for p in sw["top"]] == [1, 2, 3]
    assert sw["top"][0]["benchmark"] == "SPY" and len(sw["scores"]) == 6
    assert doc["entry_session"] == "2026-11-09" and doc["before_open"] and doc["model_version"] == "QSF-1.1.7"
    late = tp.build(latest(rows), snaps("ABCDEF"), "US", datetime(2026, 11, 9, 14, 31, tzinfo=timezone.utc))   # 09:31 New York
    assert not late["before_open"]
    kr = tp.build(latest(rows), snaps("ABCDEF", "^KQ11"), "KR", datetime(2026, 11, 9, 0, 1, tzinfo=timezone.utc))  # 09:01 Seoul
    assert not kr["before_open"] and kr["strategies"]["SWING"]["top"][0]["benchmark"] == "^KQ11"
    with pytest.raises(ValueError, match="TOO_FEW_STOCKS"):
        tp.build(latest(universe()[:4]), snaps("AB"), "US", SUNDAY)
    with pytest.raises(ValueError, match="NO_LEDGER_SESSION"):
        tp.build(latest(universe()), [], "US", SUNDAY)


def test_written_once_chained_and_a_changed_file_is_refused(tmp_path, small):
    doc = tp.build(latest(universe()), snaps("ABCDE"), "US", SUNDAY)
    assert tp.write(tmp_path, doc) is True
    other = tp.build(latest([{**r, "score": 1.0} for r in universe()]), snaps("ABCDE"), "US", SUNDAY)
    assert tp.write(tmp_path, other) is False                   # the first freeze of a session stands
    got = tp.read(tmp_path, "US")
    assert got["status"] == "OK" and got["docs"][0]["strategies"]["SWING"]["top"][0]["ticker"] == "E"
    p = tmp_path / tp.FOLDER / "2026-11-06_US.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump({**doc, "before_open": True, "strategies": other["strategies"]}, fh)
    assert tp.read(tmp_path)["status"] == "BROKEN"


def test_freeze_reads_the_published_scan_and_the_ledger(tmp_path, small):
    assert tp.freeze(tmp_path, "US", lambda: SUNDAY)["status"] == "WAITING"
    (tmp_path / "data" / "qsf").mkdir(parents=True)
    (tmp_path / "data" / "qsf" / "latest_US.json").write_text(json.dumps(latest(universe())), encoding="utf-8")
    assert tp.freeze(tmp_path, "US", lambda: SUNDAY) == {"status": "WAITING", "reason": "NO_LEDGER_SESSION", "session": "2026-11-06"}
    cards = [{"ticker": t, "strategy": s, "benchmark": "SPY", "entry_session": "2026-11-09", "domains": {}, "factors": [], "levels": {}}
             for t in "ABCDE" for s in ("SWING", "LONG_TERM")]
    Ledger(tmp_path).append("2026-11-06", "US", cards)
    out = tp.freeze(tmp_path, "US", lambda: SUNDAY)
    assert out == {"status": "OK", "session": "2026-11-06", "written": True, "before_open": True}
    assert tp.freeze(tmp_path, "US", lambda: SUNDAY)["written"] is False
    assert tp.freeze(tmp_path, "US", lambda: SUNDAY, first="2026-11-09")["reason"] == "BEFORE_FIRST"


def bars(path):
    return [{"date": d, "open": o, "close": c, "adj_close": c} for d, o, c in path]


def test_report_measures_from_the_entry_open_against_the_benchmark_and_the_whole_scan(small):
    doc = tp.build(latest(universe()), snaps("ABCDE"), "US", SUNDAY)
    flat = [(d, 100.0, 100.0) for d in DAYS]
    up = [(DAYS[0], 100.0, 100.0)] + [(d, 100.0 + i, 101.0 + i) for i, d in enumerate(DAYS[1:])]
    prices = {"SPY": flat, "E": up, "D": up, "C": flat, "B": flat, "A": [(d, 100.0, 90.0) for d in DAYS[:3]]}
    load = lambda t: bars(prices.get(t, []))                     # noqa: E731
    out = tp.report([doc], "US", load, load, cost=0.0)
    day = out["strategies"]["SWING"]["days"][0]
    e = day["top"][0]
    assert e["ticker"] == "E" and e["sessions_held"] == 6
    assert e["so_far"]["net"] == pytest.approx(106 / 100 - 1) and e["so_far"]["relative_net"] == pytest.approx(0.06)
    assert e["horizons"]["1"]["net"] == pytest.approx(0.01) and e["horizons"]["10"] is None and e["horizons"]["20"] is None
    h5 = day["horizons"]["5"]
    assert h5["universe_n"] == 4                                 # A stops trading before day five: left out, not counted as zero
    assert h5["top_mean_net"] == pytest.approx((0.05 + 0.05 + 0.0) / 3)
    assert h5["top_minus_universe"] == pytest.approx(h5["top_mean_net"] - (0.05 + 0.05) / 4)
    assert h5["rank_corr"] is None                               # fewer than ten stocks: no correlation
    s = out["strategies"]["SWING"]["summary"]["QSF-1.1.7"]["horizons"]["5"]
    assert s["picks"] == 3 and s["beat_benchmark"] == pytest.approx(2 / 3) and s["verdict"].startswith("판단 보류")


def test_a_late_freeze_is_shown_but_never_counted(small):
    late = tp.build(latest(universe()), snaps("ABCDE"), "US", datetime(2026, 11, 9, 15, tzinfo=timezone.utc))
    load = lambda t: bars([(d, 100.0, 101.0) for d in DAYS])     # noqa: E731
    out = tp.report([late], "US", load, load, cost=0.0)
    assert out["strategies"]["SWING"]["days"][0]["before_open"] is False and out["strategies"]["SWING"]["summary"] == {}


def test_verdict_needs_twelve_independent_samples_and_a_positive_spaced_correlation():
    def day(i, corr):
        return {"model_version": "V", "before_open": True, "entry_session": f"2026-{i:04d}", "top": [],
                "horizons": {str(h): {"universe_n": 100, "top_minus_universe": None, "rank_corr": corr} for h in tp.HORIZONS["SWING"]}}
    few = tp.summarize([day(i, 0.1) for i in range(59)], "SWING")["V"]["horizons"]["5"]
    assert few["verdict"] == "판단 보류 (독립 표본 11.8/12)"
    good = tp.summarize([day(i, 0.1 + 0.01 * (i % 3)) for i in range(60)], "SWING")["V"]["horizons"]["5"]
    assert good["verdict"] == "점수 순위에 증거 있음" and good["spaced_rank_corr_t"] > 2
    bad = tp.summarize([day(i, (-1) ** (i // 5) * 0.1) for i in range(60)], "SWING")["V"]["horizons"]["5"]
    assert bad["verdict"] == "증거 없음"


def test_route_and_service_without_records(tmp_path):
    from terminal.qsf.service import QSF
    from terminal.server import routes
    svc = QSF.__new__(QSF)
    svc.base = tmp_path
    assert svc.top3("US")["status"] == "NO_RECORD"

    class T:
        class qsf:
            @staticmethod
            def top3(market):
                return {"market": market}
    fn = routes(T())[("GET", "/api/qsf/top3")]
    assert fn({"market": "KR"}, {}) == {"market": "KR"} and fn({}, {}) == {"market": "US"}
    with pytest.raises(ValueError):
        fn({"market": "JP"}, {})
