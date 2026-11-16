"""Price archive: a recorded stock keeps its prices after it leaves the scan; nothing is filled in or shortened."""
import gzip
import json

from terminal.qsf import price_archive as pa
from terminal.qsf.ledger import Ledger


def bars(*days, close=10.0):
    return [{"date": d, "open": close, "close": close, "adj_close": close, "volume": 1} for d in days]


def record(base, market, tickers, session="2026-11-06"):
    cards = [{"ticker": t, "strategy": "SWING", "benchmark": "SPY", "entry_session": "2026-11-09", "domains": {}, "factors": [], "levels": {}} for t in tickers]
    Ledger(base).append(session, market, cards)


def test_merge_never_shortens_and_drops_days_before_the_start():
    old = bars("2026-11-05", "2026-11-06")
    assert pa.merge(old, bars("2026-11-05")) == old                                   # shorter answer: kept as stored
    new = pa.merge(old, bars("2026-09-30", "2026-11-06", "2026-11-09"))
    assert [b["date"] for b in new] == ["2026-11-05", "2026-11-06", "2026-11-09"]      # 09-30 is before the start
    assert "volume" not in new[-1]
    assert pa.merge(old, []) == old


def test_older_days_are_kept_when_the_new_series_starts_later():
    out = pa.merge(pa._slim(bars("2026-10-01", "2026-10-02")), bars("2026-10-02", "2026-10-05"))
    assert [(b["date"], b["close"]) for b in out] == [("2026-10-01", 10.0), ("2026-10-02", 10.0), ("2026-10-05", 10.0)]


def test_update_takes_the_scan_fetches_the_rest_and_keeps_what_yahoo_no_longer_serves(tmp_path):
    record(tmp_path, "KR", ["005930", "111110", "222220"])
    scan = {"005930": bars("2026-11-05", "2026-11-06")}
    asked = []

    def fetch(syms):
        asked.extend(syms)
        return {"111110.KQ": bars("2026-11-05", "2026-11-06")}
    out = pa.update(tmp_path, "KR", scan.get, fetch, lambda t: [f"{t}.KS", f"{t}.KQ"])
    assert out["recorded"] == 3 and (out["source"], out["fetched"], out["none"]) == (1, 1, 1)
    assert set(asked) == {"111110.KS", "111110.KQ", "222220.KS", "222220.KQ"}
    arch = pa.read(tmp_path, "KR")
    assert arch["111110"]["symbol"] == "111110.KQ" and arch["111110"]["via"] == "YAHOO" and "222220" not in arch

    # the stock is delisted: Yahoo answers nothing, the network even fails; the stored days stay, nothing is invented
    def broken(syms):
        raise OSError("down")
    out = pa.update(tmp_path, "KR", {"005930": bars("2026-11-05", "2026-11-06", "2026-11-09")}.get, broken, lambda t: [])
    assert (out["source"], out["kept"], out["none"]) == (1, 1, 1)
    arch = pa.read(tmp_path, "KR")
    assert [b["date"] for b in arch["111110"]["bars"]] == ["2026-11-05", "2026-11-06"]
    st = pa.status(tmp_path, "KR")
    assert st["via"] == {"SCAN": 1, "YAHOO": 1, "NONE": 1} and st["stopped"] == ["111110"] and st["newest"] == "2026-11-09"


def test_loader_prefers_whichever_reaches_further_and_never_mixes(tmp_path):
    record(tmp_path, "US", ["OKTA", "AAPL"])
    pa.update(tmp_path, "US", {"AAPL": bars("2026-11-05")}.get, lambda s: {"OKTA": bars("2026-11-05", "2026-11-06")}, lambda t: [t])
    load = pa.loader(tmp_path, "US", {"AAPL": bars("2026-11-05", "2026-11-06", close=20.0)}.get)
    assert load("AAPL")[-1]["close"] == 20.0 and len(load("AAPL")) == 2                # the scan, which is newer
    assert [b["date"] for b in load("OKTA")] == ["2026-11-05", "2026-11-06"]           # left the scan: the archive
    assert load("ZZZ") == []
    with gzip.open(pa.path_of(tmp_path, "US"), "rt", encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["start"] == pa.START and set(doc["tickers"]) == {"OKTA", "AAPL"}


def test_service_loader_reads_the_archive(tmp_path):
    from terminal.qsf.service import QSF
    record(tmp_path, "KR", ["111110"])
    pa.update(tmp_path, "KR", lambda t: [], lambda s: {"111110.KQ": bars("2026-11-06")}, lambda t: ["111110.KQ"])
    svc = QSF.__new__(QSF)
    svc.base, svc.dir = tmp_path, tmp_path / "data" / "qsf"
    assert svc._loader("KR")("111110")[0]["date"] == "2026-11-06"


# ---------------------------------------------------------------- a stock that stops trading inside the horizon (user decision 2026-11-08)
from terminal.qsf import ledger as lg   # noqa: E402

CAL = ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]


def px(days, closes):
    return [{"date": d, "open": c, "close": c, "adj_close": c} for d, c in zip(days, closes)]


def test_a_stock_that_stopped_trading_exits_at_its_last_trade_against_the_whole_horizon():
    bench = px(CAL, [100.0 + i for i in range(len(CAL))])
    path = px(CAL[:3], [10.0, 12.0, 15.0])                   # taken over: last trade 11-11, the market keeps going
    o = lg.outcome(path, bench, "2026-11-06", 5, 0.0, "2026-11-09", calendar=CAL)
    assert o["stopped"] and o["exit_date"] == "2026-11-11" and o["gross"] == 0.5
    assert o["relative_net"] == 0.5 - (104.0 / 100.0 - 1)      # benchmark to the horizon's last session, 11-13
    assert lg.outcome(path, bench, "2026-11-06", 5, 0.0, "2026-11-09") is None          # no calendar: the old answer
    assert lg.outcome(path, bench, "2026-11-06", 20, 0.0, "2026-11-09", calendar=CAL) is None   # horizon not over yet


def test_a_short_lag_or_a_halt_that_resumes_is_not_a_stop():
    bench = px(CAL, [100.0] * len(CAL))
    lag = px(CAL[:6], [10.0] * 6)                            # four sessions behind the market: may only be late data
    assert lg.outcome(lag, bench, "2026-11-06", 8, 0.0, "2026-11-09", calendar=CAL) is None
    halted = px(CAL[:2] + CAL[8:], [10.0, 9.0, 11.0, 12.0])    # suspended, then traded again: counted by its own bars as before
    o = lg.outcome(halted, bench, "2026-11-06", 3, 0.0, "2026-11-09", calendar=CAL)
    assert "stopped" not in o and o["exit_date"] == "2026-11-19"
    assert lg.outcome(halted, bench, "2026-11-06", 5, 0.0, "2026-11-09", calendar=CAL) is None


def test_top_three_and_ledger_count_a_stopped_stock_instead_of_dropping_it(monkeypatch):
    from terminal.qsf import top_picks as tp
    monkeypatch.setitem(tp.MIN_ROWS, "US", 4)
    rows = []
    for i, t in enumerate("ABCDE"):
        rows += [{"ticker": t, "name": t, "strategy": s, "score": 60 + i, "action": "WATCH", "price": 10.0, "actionability": "ACTIONABLE",
                  "data_date": "2026-11-06"} for s in ("SWING", "LONG_TERM")]
    latest = {"status": "REAL", "session": "2026-11-06", "model_version": "V", "rows": rows}
    snaps = [{"ticker": t, "strategy": s, "benchmark": "SPY", "entry_session": "2026-11-09"} for t in "ABCDE" for s in ("SWING", "LONG_TERM")]
    from datetime import datetime, timezone
    doc = tp.build(latest, snaps, "US", datetime(2026, 11, 8, 3, tzinfo=timezone.utc))
    prices = {"SPY": px(CAL, [100.0] * 10), "E": px(CAL[:2], [10.0, 5.0])}
    for t in "ABCD":
        prices[t] = px(CAL, [10.0] * 10)
    load = lambda t: prices.get(t, [])                       # noqa: E731
    h5 = tp.report([doc], "US", load, load, cost=0.0)["strategies"]["SWING"]["days"][0]
    assert h5["horizons"]["5"]["universe_n"] == 5 and h5["top"][0]["horizons"]["5"]["stopped"] and h5["top"][0]["horizons"]["5"]["net"] == -0.5
    snap = {"market": "US", "strategy": "SWING", "ticker": "E", "score": 80.0, "data_date": "2026-11-06", "entry_session": "2026-11-09", "model_version": "V"}
    out = lg.validate([snap], "US", "SWING", load, prices["SPY"], cost=0.0)
    assert sum(b["n"] for b in out["horizons"]["5"]["buckets"].values()) == 1 and out["horizons"]["5"]["matured_sessions"] == 1
