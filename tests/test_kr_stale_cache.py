"""A Korean download taken before the provider finished the day must not be reused, and a scan of a handful of stocks is not a day.

2026-11-11: a run at 02:27 KST stored universe bars in which 28% of the stocks had the session.  The store is keyed by calendar day,
so the 07:32 run read the same file, built a universe of two stocks and recorded them as the Korean session."""
from datetime import datetime, timezone

import pandas as pd

from markets.kr import acquisition
from terminal.qsf import service as svc
from terminal.qsf.service import QSF

NOW = datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc)        # 09:00 KST: the bars of 2026-11-10 are complete
DAY, BEFORE = "2026-11-10", "2026-11-09"
TICKERS = [f"{k:06d}" for k in range(10)]
SECS = pd.DataFrame({"yahoo_symbol": [t + ".KS" for t in TICKERS]})
WINDOW = ("2026-09-12", "2026-11-12")


class Prov:
    def __init__(self, frames):
        self.frames, self.calls, self.events = list(frames), 0, []

    def fetch(self, securities, start, end):
        self.calls += 1
        return self.frames.pop(0)


def frame(last_of):
    rows = [{"ticker": t, "date": d, "close": 100.0, "quality_flags": "", "quality_status": "REAL"} for t, last in last_of.items() for d in pd.bdate_range("2026-11-02", last)]
    return pd.DataFrame(rows, columns=["ticker", "date", "close", "quality_flags", "quality_status"])


EARLY = {t: DAY if k < 3 else BEFORE for k, t in enumerate(TICKERS)}        # three of ten stocks have the day
FULL = {t: DAY for t in TICKERS}


def get(prov, tmp_path, **kw):
    return acquisition.bars(prov, SECS, *WINDOW, NOW, tmp_path, "universe", **kw)


def test_a_download_taken_too_early_is_replaced_once_the_session_is_asked_for(tmp_path):
    prov = Prov([frame(EARLY), frame(FULL)])
    assert not get(prov, tmp_path, fresh_at=BEFORE)["cache_hit"]
    assert get(prov, tmp_path, fresh_at=BEFORE)["cache_hit"] and prov.calls == 1         # while the index is a day behind the file is good
    again = get(prov, tmp_path, fresh_at=DAY)
    assert not again["cache_hit"] and again["stale_cache_found"] and prov.calls == 2
    assert set(again["bars"].groupby("ticker")["date"].max().dt.strftime("%Y-%m-%d")) == {DAY}
    kept = get(prov, tmp_path, fresh_at=DAY)
    assert kept["cache_hit"] and prov.calls == 2 and len(kept["bars"]) == len(again["bars"])


def test_a_few_halted_stocks_do_not_make_a_file_stale(tmp_path):
    prov = Prov([frame({**FULL, TICKERS[0]: BEFORE})])
    get(prov, tmp_path, fresh_at=DAY)
    assert get(prov, tmp_path, fresh_at=DAY)["cache_hit"] and prov.calls == 1


def test_without_a_session_the_stored_file_is_reused_as_before(tmp_path):
    prov = Prov([frame(EARLY)])
    get(prov, tmp_path)
    assert get(prov, tmp_path)["cache_hit"] and prov.calls == 1


def test_an_empty_reply_keeps_the_stored_file_and_returns_no_bars(tmp_path):
    prov = Prov([frame(EARLY), frame({})])
    first = get(prov, tmp_path, fresh_at=BEFORE)
    res = get(prov, tmp_path, fresh_at=DAY)
    assert res["bars"].empty and res["file"] is None and res["stale_cache_found"]
    assert get(prov, tmp_path, fresh_at=BEFORE)["cache_hit"] and len(first["bars"]) == 63       # the earlier file is still there


def kr_scan(tmp_path, n, **kw):
    q = QSF(tmp_path, now=lambda: NOW)
    codes = [f"{k:06d}" for k in range(n)]
    pre = {c: {"bars": [{"date": DAY, "close": 1.0}], "bench": []} for c in codes}
    q._kr_scan_input = lambda tickers, progress, side_files: (list(tickers or codes), pre)
    q.regime = lambda market: {"session": DAY}
    q._last_weekday_done = lambda: DAY
    q.context = lambda t, market, prefetched=None: {"error": "NOT_SCORED_IN_THIS_TEST"}
    q._write_ranks = lambda market, day, pre: None
    return q, q.scan("KR", **kw)


def test_a_whole_market_scan_of_two_stocks_is_not_recorded(tmp_path):
    q, res = kr_scan(tmp_path, 2)
    assert res["status"] == "DATA_NOT_READY" and res["reason"] == "UNIVERSE_TOO_SMALL" and res["tickers"] == 2 and res["at_session"] == 2
    assert not q.ledger.read_index()["rows"] and not (q.dir / "latest_KR.json").exists()


def test_the_size_rule_is_for_the_whole_market_scan_only(tmp_path):
    assert kr_scan(tmp_path / "a", svc.KR_MIN_UNIVERSE - 1)[1]["reason"] == "UNIVERSE_TOO_SMALL"
    assert kr_scan(tmp_path / "b", svc.KR_MIN_UNIVERSE)[1]["status"] != "DATA_NOT_READY"
    assert kr_scan(tmp_path / "c", 2, tickers=["000000", "000001"])[1]["status"] != "DATA_NOT_READY"       # a list the caller chose
    assert kr_scan(tmp_path / "d", 2, record=False)[1]["status"] != "DATA_NOT_READY"                       # a dry run records nothing
