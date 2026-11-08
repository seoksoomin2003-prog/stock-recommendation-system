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
    new = pa.merge(old, bars("2026-09-30", "2026-11-06", "2026-11-09", close=11.0))
    assert [(b["date"], b["close"]) for b in new] == [("2026-11-05", 10.0), ("2026-11-06", 11.0), ("2026-11-09", 11.0)]   # 09-30 is before the start
    assert "volume" not in new[-1]
    assert pa.merge(old, []) == old


def test_older_days_are_kept_when_the_new_series_starts_later():
    out = pa.merge(pa._slim(bars("2026-10-01", "2026-10-02")), bars("2026-10-02", "2026-10-05", close=12.0))
    assert [(b["date"], b["close"]) for b in out] == [("2026-10-01", 10.0), ("2026-10-02", 12.0), ("2026-10-05", 12.0)]


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
