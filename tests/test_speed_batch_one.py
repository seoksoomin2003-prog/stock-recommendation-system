"""First batch of the 2026-11-16 speed and stability review (reports/SPEED_STABILITY_REVIEW_2026_11_16.md).
Each test pins one finding.  None of the fixes changes a score or a stored record: where a reading was made cheaper, the test
compares it with the reading it replaces."""
import gzip
import inspect
import json
import os
import subprocess
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from terminal import automation, cache as cache_mod, news, sources
from terminal.qsf import history, kr_bars, ledger, research_kr as kr
from terminal.qsf import service as qsf_service
from terminal.qsf.views import ScreenViews
from tests.test_kr_bars import row, write
from tests.test_qsf import NOW, FakeSrc, FakeTerm, card

DAYS = ["2026-10-%02d" % k for k in range(1, 7)]


def filled(tmp_path):
    """Six sessions.  T0 is in all of them, T1 leaves after the second, T2 has only a long-term record, GONE was never recorded."""
    lg = ledger.Ledger(tmp_path)
    for n, day in enumerate(DAYS):
        cards = []
        for t, st in (("T0", "SWING"), ("T0", "LONG_TERM"), ("T1", "SWING"), ("T2", "LONG_TERM")):
            if t == "T1" and n >= 2:
                continue
            c = card(ticker=t, strategy=st)
            c["data_date"], c["score"] = day, float(40 + n + len(t))
            for j, f in enumerate(c["factors"]):
                if f.get("contribution") is not None:
                    f["contribution"] = float(n + j) / 10
            cards.append(c)
        lg.append(day, "US", cards)
    lg.append(DAYS[0], "KR", [card(ticker="T0", market="KR")])           # another market's record of the same name is never read
    return lg


def walk(lg, market, ticker, strategy, before):
    """The reading ``previous`` replaced: every earlier shard parsed whole, newest first."""
    for r in reversed(lg._live_rows()):
        if r["market"] == market and r["session"] < before:
            hit = next((s for s in lg._load(r) if s["ticker"] == ticker and s["strategy"] == strategy), None)
            if hit:
                return hit
    return None


# ---------------------------------------------------------------------- B3 / C2: the previous snapshot, without parsing shards again
def test_the_previous_snapshot_gives_the_same_stability_reading_as_the_full_walk(tmp_path):
    lg = filled(tmp_path)
    cur = card(ticker="T0")
    cur["score"] = 55.0
    for t, st, before in (("T0", "SWING", "2026-10-06"), ("T0", "LONG_TERM", "2026-10-04"), ("T1", "SWING", "2026-10-06"),
                          ("T1", "SWING", "2026-10-02"), ("T2", "LONG_TERM", "2026-10-06"), ("T2", "SWING", "2026-10-06"),
                          ("T0", "SWING", "2026-10-01"), ("GONE", "SWING", "2026-10-06")):
        old, new = walk(lg, "US", t, st, before), ledger.Ledger(tmp_path).previous("US", t, st, before)
        assert (old is None) == (new is None), (t, st, before)
        assert ledger.stability(old, cur) == ledger.stability(new, cur), (t, st, before)
    assert ledger.stability(walk(lg, "US", "T1", "SWING", "2026-10-06"), cur)["previous_date"] == "2026-10-02"     # found two shards back


def test_a_scan_parses_the_previous_shard_once_and_a_stock_never_recorded_costs_no_shard(tmp_path, monkeypatch):
    filled(tmp_path)
    lg = ledger.Ledger(tmp_path)
    lg.previous("US", "T0", "SWING", "2026-10-07")                        # side files written, the newest shard kept
    loads = []
    plain = ledger.Ledger._load
    monkeypatch.setattr(ledger.Ledger, "_load", lambda self, r: (loads.append(r["file"]), plain(self, r))[1])
    for _ in range(50):
        assert lg.previous("US", "T0", "LONG_TERM", "2026-10-07")["score"] is not None
        assert lg.previous("US", "GONE", "SWING", "2026-10-07") is None
    assert loads == []
    fresh = ledger.Ledger(tmp_path)                                       # another process: the side files are on disk
    assert fresh.previous("US", "GONE", "SWING", "2026-10-07") is None and loads == []
    assert fresh.previous("US", "T1", "SWING", "2026-10-07")["data_date"] == "2026-10-02" and len(loads) == 1
    lg.append("2026-10-07", "US", [card(ticker="NEW")])                   # the index changed: the new shard is seen
    assert lg.previous("US", "NEW", "SWING", "2026-10-08")["score"] is not None


def test_a_side_file_is_kept_only_for_a_shard_that_has_the_recorded_hash(tmp_path):
    lg = filled(tmp_path)
    r = [x for x in lg._live_rows() if x["market"] == "US"][0]
    rows = lg.side(r)
    assert set(rows) == {"T0", "T1", "T2"} and list(rows["T0"]) == ["SWING", "LONG_TERM"] and len(list(lg.side_dir.iterdir())) == 1
    assert rows["T0"]["SWING"]["data_date"] == "2026-10-01" and set(rows["T0"]["SWING"]) == set(ledger.SIDE_FIELDS) | {"domains"}
    again = ledger.Ledger(tmp_path).side(r)
    assert again == rows
    r2 = [x for x in lg._live_rows() if x["market"] == "US"][1]
    with gzip.open(lg.dir / r2["file"], "wt", encoding="utf-8") as fh:    # the shard was rewritten after it was recorded
        fh.write(json.dumps({"ticker": "FAKE", "strategy": "SWING", "score": 99.0}) + "\n")
    assert set(lg.side(r2)) == {"FAKE"} and len(list(lg.side_dir.iterdir())) == 1          # read, never stored
    assert lg.verified()["status"] == "BROKEN"


def test_history_from_side_files_is_the_history_from_whole_shards(tmp_path, monkeypatch):
    lg = filled(tmp_path)

    def reference(market, ticker):                                        # the loop this replaced
        found = {}
        for r in lg._live_rows():
            if r["market"] != market:
                continue
            for s in lg._load(r):
                if s.get("ticker") == ticker:
                    found.setdefault(s["strategy"], {}).setdefault(r["session"], history._row(r["session"], s))
        out = {}
        for strategy, by_session in found.items():
            rows = [by_session[k] for k in sorted(by_session)]
            for prev, cur in zip(rows, rows[1:]):
                cur["model_changed"] = cur["model_version"] != prev["model_version"]
            if rows:
                rows[0]["model_changed"] = False
            out[strategy] = rows
        return out
    for t in ("T0", "T1", "T2", "GONE"):
        got = history.history(lg, "US", t)
        assert json.dumps(got["strategies"]) == json.dumps(reference("US", t)) and got["status"] == ("NO_RECORD" if t == "GONE" else "REAL")
    monkeypatch.setattr(ledger.Ledger, "_load", lambda self, r: pytest.fail("a shard was parsed though its side file exists"))
    monkeypatch.setattr(ledger.Ledger, "verify", lambda self: pytest.fail("every shard hashed again though no file changed"))
    assert len(history.history(lg, "US", "T0")["strategies"]["SWING"]) == 6


def test_the_cached_check_hashes_again_when_a_file_changes(tmp_path):
    lg = filled(tmp_path)
    assert lg.verified()["status"] == "OK" and lg.verified() is lg.verified()
    r = lg._live_rows()[0]
    p = lg.dir / r["file"]
    raw = p.read_bytes()
    p.write_bytes(raw[:-3])                                               # cut short
    assert lg.verified()["status"] == "BROKEN" and lg.verified()["bad_files"] == [r["file"]]
    p.write_bytes(raw)
    assert lg.verified()["status"] == "OK"


# ---------------------------------------------------------------------- A1: only a whole-universe scan replaces shared files
def test_a_scan_of_named_stocks_leaves_the_published_ranking_alone(tmp_path):
    import app
    svc = qsf_service.QSF(tmp_path, src=FakeSrc(), now=lambda: NOW, terminal=FakeTerm())
    res = svc.scan("US", tickers=["AAA", "BBB"], publish=False)           # what the command line does for named stocks
    assert res["status"] == "REAL" and res["scored"] == 4 and res["ledger"]["recorded"] == 4      # scored and recorded, as before
    assert not (svc.dir / "latest_US.json").exists() and not (svc.dir / "ranks_US.json").exists()
    assert svc.scan("US")["status"] == "REAL" and (svc.dir / "latest_US.json").exists()             # the whole universe publishes
    assert "publish=not args.tickers" in inspect.getsource(app._qsf_scan)
    src = inspect.getsource(qsf_service.QSF._kr_scan_input)
    assert "if side_files and not tickers:" in src and "if len(above) >= 50 and side_files and not tickers:" in src     # bar store and breadth


# ---------------------------------------------------------------------- D1: the Korean panel is continued, not rebuilt
def krx_days(base, days, extra=None):
    write(base, {d: [row("000010", 100 + n, 101 + n, 99 + n, 100 + n, 1.0, 10 + n)] + ([row("000020", 5, 5, 5, 5, 0.0, 1)] if n == 0 else [])
                 + (extra or {}).get(d, []) for n, d in enumerate(days)})


def window_from(first):
    """The day on which the panel's window starts at ``first``."""
    return date.fromisoformat(first) + timedelta(days=kr_bars.WINDOW_DAYS)


def same(a, b):
    assert a["dates"] == b["dates"] and a["codes"] == b["codes"] and np.array_equal(a["data"], b["data"], equal_nan=True)


def test_a_window_that_only_moved_forward_reads_the_stored_panel(tmp_path, monkeypatch):
    days = ["2024-09-0%d" % k for k in range(2, 7)]
    krx_days(tmp_path, days)
    first = kr_bars.panel(tmp_path, window_from(days[0]))                 # all five days
    assert first["dates"] == days and set(first["codes"]) == {"000010", "000020"}
    fresh = kr_bars._view(kr_bars.build_panel(tmp_path / kr_bars.KRX, days[2:]))
    monkeypatch.setattr(kr_bars, "build_panel", lambda *a: pytest.fail("built again though the stored panel holds these days"))
    later = kr_bars.panel(tmp_path, window_from(days[2]))                 # two days later the window starts two days later
    same(later, fresh)
    assert later["dates"] == days[2:] and list(later["codes"]) == ["000010"]       # the stock seen only on a day now outside is gone


def test_a_new_day_is_added_by_reading_that_day_only(tmp_path, monkeypatch):
    days = ["2024-09-0%d" % k for k in range(2, 7)]
    krx_days(tmp_path, days[:4])
    kr_bars.panel(tmp_path, window_from(days[0]))
    krx_days(tmp_path, days, extra={days[4]: [row("000030", 7, 7, 7, 7, 0.0, 3)]})
    read, plain = [], kr_bars.build_panel
    monkeypatch.setattr(kr_bars, "build_panel", lambda root, ds: (read.append(list(ds)), plain(root, ds))[1])
    grown = kr_bars.panel(tmp_path, window_from(days[1]))                 # the window moved a day, and the last day is new
    assert read == [[days[4]]]
    same(grown, kr_bars._view(plain(tmp_path / kr_bars.KRX, days[1:])))
    assert kr_bars._kept(tmp_path / kr_bars.CACHE, days[1:]) is not None  # stored: the next reading builds nothing
    with np.load(tmp_path / kr_bars.CACHE) as z:                          # a panel of the layout before this change is built anew
        np.savez_compressed(tmp_path / kr_bars.CACHE, dates=z["dates"], codes=z["codes"], data=z["data"])
    read.clear()
    same(kr_bars.panel(tmp_path, window_from(days[1])), grown)
    assert read == [days[1:]]


# ---------------------------------------------------------------------- B6: the same price arrays are built once per process
def test_price_arrays_for_the_same_days_are_built_once_and_handed_out_as_copies(tmp_path, monkeypatch):
    built = []
    monkeypatch.setattr(kr, "_LAST_BUILD", {})

    def fake(root, log, days):
        built.append(list(days))
        return {"dates": np.array(days), "symbols": np.array(["A"]), "close": np.arange(len(days), dtype=np.float32).reshape(-1, 1)}
    monkeypatch.setattr(kr, "_build_prices", fake)
    for b in ("KOSPI", "KOSDAQ"):
        (tmp_path / b).mkdir()
        (tmp_path / b / "2026-11-02.json.gz").write_bytes(b"x")
    said = []
    a = kr.build_prices(tmp_path, log=said.append, days=["2026-11-03", "2026-11-02"])
    a["close"][0, 0] = 99.0                                               # a caller changing its copy
    b = kr.build_prices(tmp_path, log=said.append, days=["2026-11-02", "2026-11-03"])
    assert built == [["2026-11-02", "2026-11-03"]] and b["close"][0, 0] == 0.0 and said == ["days 2 stocks 1"]
    (tmp_path / "KOSPI" / "2026-11-03.json.gz").write_bytes(b"new day")   # a day file appeared: built again
    kr.build_prices(tmp_path, log=lambda m: None, days=["2026-11-02", "2026-11-03"])
    kr.build_prices(tmp_path, log=lambda m: None, days=["2026-11-02"])
    assert len(built) == 3


# ---------------------------------------------------------------------- B4: one connection for the news run
def test_the_news_run_uses_one_connection_and_stores_no_cookie(tmp_path, monkeypatch):
    (tmp_path / "data" / "qsf").mkdir(parents=True)
    (tmp_path / "data" / "qsf" / "latest_US.json").write_text(json.dumps({"rows": [{"ticker": t} for t in ("A", "B", "C")]}), encoding="utf-8")

    class Reply:
        status_code, content = 200, b"<rss><channel></channel></rss>"

        def raise_for_status(self):
            pass

    class Client:
        made, calls, closed = 0, [], False

        def __init__(self):
            Client.made += 1

        def get(self, url, **kw):
            Client.calls.append(url)
            return Reply()

        def close(self):
            Client.closed = True
    monkeypatch.setattr(news, "_one_connection", Client)
    waits = []
    out = news.record(tmp_path, "US", sleep=waits.append)
    assert out["ok"] == 3 and Client.made == 1 and len(Client.calls) == 3 and Client.closed and waits == [news.PAUSE_S] * 2
    monkeypatch.undo()
    s = news._one_connection()
    assert s.cookies.get_policy().allowed_domains() == () and news.record.__defaults__[0] is news.requests
    s.close()


# ---------------------------------------------------------------------- B8 / D3: limits
def test_the_us_score_step_has_the_long_limit_and_a_silent_launchctl_is_given_up(monkeypatch):
    assert automation.STEP_TIMEOUTS["QSF"] == 90 * 60
    seen = []

    def run(cmd, **kw):
        seen.append((cmd[1], kw.get("timeout")))
        if cmd[1] == "print":
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(automation.subprocess, "run", run)
    assert automation._launchctl("print", "gui/1/x").returncode == 124 and automation._launchctl("bootout", "gui/1", "p").returncode == 0
    assert seen == [("print", automation.LAUNCHCTL_PRINT_TIMEOUT_S), ("bootout", None)]
    monkeypatch.setattr(automation, "plist_path", lambda: Path(__file__))
    assert os.name == "nt" or automation.is_installed() is False      # Windows asks Task Scheduler instead (tests/test_windows_port.py)


# ---------------------------------------------------------------------- D4 / D5: one computation, one fetch
def together(n, call):
    out, gate = [], threading.Barrier(n)

    def work():
        gate.wait()
        out.append(call())
    threads = [threading.Thread(target=work) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    return out


def test_two_requests_for_one_key_fetch_once_and_a_failed_fetch_does_not_block_the_next(tmp_path):
    c, fetched = cache_mod.FileCache(tmp_path), []

    def slow():
        fetched.append(1)
        time.sleep(0.2)
        return {"v": len(fetched)}
    got = together(4, lambda: c.cached("k", 60, slow))
    assert len(fetched) == 1 and [g["status"] for g in got] == ["REAL"] * 4 and {g["data"]["v"] for g in got} == {1}

    def down():
        fetched.append(1)
        raise RuntimeError("x")
    fetched.clear()
    got = together(3, lambda: c.cached("other", 60, down))
    assert len(fetched) == 3 and {g["status"] for g in got} == {"UNAVAILABLE"}      # each still tries, as before
    assert c.cached("k", 60, lambda: c.cached("k", 60, lambda: {"v": 0}))["data"] == {"v": 1}      # a fetch may read its own key
    assert len(c._key_locks) == 0                                         # a lock lives only while a request uses it


def test_a_report_asked_for_twice_at_once_is_computed_once():
    class V(ScreenViews):
        pass
    v, runs = V(), []

    def compute():
        runs.append(1)
        time.sleep(0.2)
        return {"n": len(runs)}
    got = together(4, lambda: v._memo("report", ("stamp",), compute))
    assert runs == [1] and got == [{"n": 1}] * 4
    assert v._memo("report", ("later",), compute) == {"n": 2}             # a new stamp computes again
    assert v._memo("outer", ("s",), lambda: v._memo("inner", ("s",), lambda: {"ok": True})) == {"ok": True}


# ---------------------------------------------------------------------- D7: lists a long-lived process reads again
def test_the_korean_stock_list_is_read_again_after_a_newer_snapshot_and_a_given_list_never_is(tmp_path, monkeypatch):
    from markets.kr import security_master
    folder = tmp_path / "data" / "kr" / "security_master"
    folder.mkdir(parents=True)
    (folder / "LATEST.json").write_text("{}", encoding="utf-8")
    loads = []

    def load(data_dir, now=None):
        loads.append(1)
        return {"master": pd.DataFrame({"canonical_ticker": ["000010"] + (["000020"] if len(loads) > 1 else []), "company_name": ["x"] * min(len(loads), 2)})}
    monkeypatch.setattr(security_master, "load_master", load)
    svc = qsf_service.QSF(tmp_path, src=FakeSrc(), now=lambda: NOW, terminal=FakeTerm())
    assert svc._kr_identity("000010") and svc._kr_identity("000020") is None and svc._kr_identity("000010") and len(loads) == 1
    os.utime(folder / "LATEST.json", ns=(1, 1))                           # the morning scan stored a newer list
    assert svc._kr_identity("000020") and len(loads) == 2 and svc._kr_identity("000020") and len(loads) == 2
    given = qsf_service.QSF(tmp_path, src=FakeSrc(), now=lambda: NOW, terminal=FakeTerm(), kr_master=pd.DataFrame({"canonical_ticker": ["000099"]}))
    os.utime(folder / "LATEST.json", ns=(2, 2))
    assert given._kr_identity("000099") and given._kr_identity("000010") is None and len(loads) == 2
    for day in ("a", "b", "c", "d", "e"):
        monkeypatch.setattr("terminal.qsf.krx_history.listed_shares", lambda root, as_of: {"x": 1.0})
        assert svc._krx_shares(day) == {"x": 1.0}
    assert list(svc._krx_share_cache) == ["c", "d", "e"]


def test_the_sec_ticker_table_is_read_again_a_day_later_and_a_table_put_there_is_left(monkeypatch):
    import core.universe_provider as up

    class Table:
        made = 0

        def __init__(self):
            Table.made += 1
            self.n = Table.made

        def load(self):
            if Table.fail:
                raise RuntimeError("down")
            return self

        def cik(self, t):
            return self.n
    Table.fail = False
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(up, "SecTickerMap", Table)
    monkeypatch.setattr(sources, "_ticker_map", [])
    monkeypatch.setattr(sources, "_ticker_map_at", [])
    monkeypatch.setattr(sources.time, "time", lambda: clock["t"])
    assert sources.sec_cik("AAA") == "0000000001" and sources.sec_cik("AAA") == "0000000001"
    clock["t"] += sources.TICKER_MAP_SECONDS + 1
    assert sources.sec_cik("AAA") == "0000000002"                         # a day later: read again
    clock["t"] += sources.TICKER_MAP_SECONDS + 1
    Table.fail = True
    assert sources.sec_cik("AAA") == "0000000002"                         # the reload failed: the table in hand answers
    made = Table.made
    assert sources.sec_cik("AAA") == "0000000002" and Table.made == made  # and is not retried on every call
    clock["t"] += sources.TICKER_MAP_RETRY_SECONDS + 1
    Table.fail = False
    assert sources.sec_cik("AAA") == f"{made + 1:010d}"
    monkeypatch.setattr(sources, "_ticker_map", [Table()])
    monkeypatch.setattr(sources, "_ticker_map_at", [])
    put = Table.made
    clock["t"] += 10 * sources.TICKER_MAP_SECONDS
    assert sources.sec_cik("AAA") == f"{put:010d}" and Table.made == put  # a table a caller put there is never replaced


# ---------------------------------------------------------------------- D2 / D6: text pins for what a unit test cannot reach
def test_the_peers_view_builds_one_map_and_the_page_drops_cards_of_an_earlier_scan():
    src = inspect.getsource(ScreenViews._peers)
    assert 'self.heatmap(market, "SWING")' in src and "config.STRATEGIES}" not in src
    assert "load.tail(t, self.HEAT_TAIL)" in inspect.getsource(ScreenViews._heatmap) and ScreenViews.HEAT_TAIL > 2 * max(ScreenViews.HEAT_SPANS.values())
    js = (Path(__file__).resolve().parents[1] / "terminal" / "static" / "qsf.js").read_text(encoding="utf-8")
    assert "qsfState.scanMark[mk] !== scanMark" in js and "delete qsfState.evals[k]" in js
