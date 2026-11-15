"""The first batch of the 2026-11-15 stability review (reports/STABILITY_REVIEW_2026_11_15.md): a long-lived server recomputes
the regime, a run waits for the network and tries a quick failure once more, a file cut short is survived, write-once stores
take one writer at a time, and a full disk does not throw fetched data away.  No network."""
import gzip
import json
import logging
import urllib.request
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from markets.kr import acquisition, security_master
from terminal import automation, server, storage
from terminal.cache import FileCache
from terminal.qsf import kr_bars, kr_forward as kf, ledger, price_audit, top_picks
from terminal.qsf import service as qsf_service
from tests import kr_fakes as F
from tests.test_qsf import NOW, SESSION, card, service
from tests.test_server_stability import live  # noqa: F401  (fixture)
from tests.test_terminal_1 import _loopback_only  # noqa: F401  (autouse: these tests may reach 127.0.0.1 only)
from tests.test_terminal_4 import clean_env, make  # noqa: F401  (clean_env is an autouse fixture)


# ---------------------------------------------------------------------- A1: the regime memo
def test_a_long_lived_process_recomputes_the_regime_and_a_scan_keeps_one(tmp_path):
    clock = {"now": NOW}
    svc = qsf_service.QSF(tmp_path, src=service(tmp_path).src, now=lambda: clock["now"], terminal=service(tmp_path).terminal)
    made = []
    svc._regime_us = lambda: made.append(clock["now"]) or {"n": len(made)}
    assert svc.regime("US") == {"n": 1} and svc.regime("US") == {"n": 1}
    clock["now"] = NOW + timedelta(seconds=qsf_service.REGIME_MEMO_SECONDS - 1)
    assert svc.regime("US") == {"n": 1}
    clock["now"] = NOW + timedelta(seconds=qsf_service.REGIME_MEMO_SECONDS)
    assert svc.regime("US") == {"n": 2}                              # the server no longer keeps its first regime for good
    seen = []

    @qsf_service._one_regime
    def scan(self):
        seen.append(self.regime("US"))
        clock["now"] += timedelta(hours=3)                           # a scan slowed by a sleeping Mac
        seen.append(self.regime("US"))
        return "done"
    assert scan(svc) == "done" and seen == [{"n": 3}, {"n": 3}] and svc._regime_hold is False      # fresh at the start, one to the end
    assert svc.regime("US") == {"n": 4}                              # and it expires again once the scan is over
    svc._regime["KR"] = {"set": "by hand"}                           # a value placed without a time is kept
    assert svc.regime("KR") == {"set": "by hand"}


# ---------------------------------------------------------------------- B1, B4, B8: the daily run
def test_the_korean_record_step_has_room(tmp_path):
    assert automation.STEP_TIMEOUTS["KR_FORWARD"] == 90 * 60 and automation.STEP_TIMEOUT == 45 * 60


def test_a_run_waits_for_the_network_but_not_for_ever(tmp_path):
    d, _, _ = make(tmp_path)
    answers, naps = iter([False, False, True]), []
    d.online, d.sleep = lambda: next(answers), naps.append
    assert d._wait_for_network() is True and naps == [automation.NETWORK_POLL_S] * 2
    naps.clear()
    d.online = lambda: False
    assert d._wait_for_network() is False and sum(naps) == automation.NETWORK_WAIT_S
    assert automation.Daily(tmp_path, runner=lambda n, a: 0).online() is True          # a stand-in runner never looks anything up


def test_a_quick_failure_gets_one_more_try_and_a_slow_one_or_missing_data_does_not(tmp_path, monkeypatch):
    monkeypatch.setenv("QPP_CAPITAL", "1000")
    d, calls, sent = make(tmp_path, rc={"TRACK": 1, "QSF": 3})
    res = d.run()
    assert calls.count("TRACK") == 2 and res["steps"]["TRACK"]["retried"] is True and res["steps"]["TRACK"]["status"] == automation.FAILED
    assert calls.count("QSF") == 1 and "retried" not in res["steps"]["QSF"]            # "data not ready": the provider will not have it a minute later
    assert calls.index("TRACK", calls.index("US_CHALLENGER")) > calls.index("US_CHALLENGER")     # the second try comes after the whole chain
    ticks = iter(range(0, 10 ** 7, 400))                                               # every step takes 400 seconds awake
    d2, calls2, _ = make(tmp_path / "slow", rc={"TRACK": 1})
    d2.clocks = (lambda: 0.0, lambda: float(next(ticks)))
    assert d2.run()["steps"]["TRACK"]["seconds"] == 400 and calls2.count("TRACK") == 1


def test_a_run_that_dies_outside_its_steps_says_so_once_a_day(tmp_path):
    d, _, sent = make(tmp_path)
    d._run = lambda resend: (_ for _ in ()).throw(OSError("disk full"))
    with pytest.raises(OSError):
        d.run()
    assert len(sent) == 1 and "단계 밖에서 멈췄습니다" in sent[0] and "OSError" in sent[0] and "disk full" not in sent[0]
    with pytest.raises(OSError):
        d.run()
    assert len(sent) == 1 and d.state()["last_attempt"]["status"] == "ERROR"
    d.telegram = lambda text: (_ for _ in ()).throw(RuntimeError("no network"))
    d._run = lambda resend: (_ for _ in ()).throw(KeyError("other"))
    with pytest.raises(KeyError):                                                       # a failed notice never hides the failure itself
        d.run()


# ---------------------------------------------------------------------- B3: the Korean security master
def test_a_failed_download_falls_back_to_a_recent_snapshot_and_says_it_is_old(tmp_path):
    def boom(m):
        raise RuntimeError("KIND download failed")
    first = security_master.load_master(tmp_path, fetch=F.fake_kind(5, 4), now=F.NOW)
    later = security_master.load_master(tmp_path, fetch=boom, now=F.NOW + pd.Timedelta(hours=30))
    assert later["meta"]["status"] == "STALE" and later["meta"]["stale_hours"] == 30.0 and later["meta"]["error"] == "RuntimeError"
    assert list(later["master"]["canonical_ticker"]) == list(first["master"]["canonical_ticker"])
    with pytest.raises(RuntimeError):                                                   # a week-old list is not used in its place
        security_master.load_master(tmp_path, fetch=boom, now=F.NOW + pd.Timedelta(hours=security_master.MAX_STALE_HOURS + 1))
    with pytest.raises(RuntimeError):                                                   # and with no snapshot nothing is made up
        security_master.load_master(tmp_path / "empty", fetch=boom, now=F.NOW)


def test_a_table_that_shrank_is_read_as_a_broken_download(tmp_path):
    security_master.load_master(tmp_path, fetch=F.fake_kind(50, 40), now=F.NOW)
    small = security_master.load_master(tmp_path, fetch=F.fake_kind(5, 4), now=F.NOW + pd.Timedelta(hours=30))
    assert small["meta"]["status"] == "STALE" and small["meta"]["error"] == "ValueError" and small["meta"]["rows"] == 90
    fresh = security_master.load_master(tmp_path, fetch=F.fake_kind(50, 41), now=F.NOW + pd.Timedelta(hours=31))
    assert fresh["meta"]["status"] == "REAL" and fresh["meta"]["rows"] == 91


# ---------------------------------------------------------------------- C1: files written whole, cut files survived
def test_a_cut_korean_bar_file_is_survived_by_its_readers(tmp_path):
    folder = tmp_path / "data" / "qsf"
    folder.mkdir(parents=True)
    whole = gzip.compress(json.dumps({"005930": [{"date": "2026-11-13", "close": 1.0}]}).encode())
    (folder / "bars_KR.json.gz").write_bytes(whole[:len(whole) // 2])                   # a run killed in the middle of the write
    with pytest.raises(EOFError):
        with gzip.open(folder / "bars_KR.json.gz", "rt", encoding="utf-8") as fh:
            json.load(fh)
    assert price_audit.audit_kr(tmp_path)["status"] == "UNAVAILABLE"
    assert service(tmp_path)._loader("KR")("005930") == []


def test_the_scan_swaps_the_korean_bar_file_in_and_the_bar_cache_too(tmp_path):
    src = (qsf_service.__file__ and open(qsf_service.__file__, encoding="utf-8").read())
    assert 'os.replace(tmp, self.dir / "bars_KR.json.gz")' in src and 'gzip.open(self.dir / "bars_KR.json.gz", "wt"' not in src

    class Provider:
        events = []

        def __init__(self):
            self.calls = 0

        def fetch(self, securities, start, end):
            self.calls += 1
            return pd.DataFrame({"ticker": ["005930"], "date": pd.to_datetime(["2026-11-12"]), "close": [1.0], "quality_flags": [""], "quality_status": ["OK"]})
    secs = pd.DataFrame({"yahoo_symbol": ["005930.KS"]})
    prov, cache = Provider(), tmp_path / "cache"
    now = pd.Timestamp("2026-11-13T00:30:00Z")
    first = acquisition.bars(prov, secs, "2026-09-01", "2026-11-13", now, cache, "history")
    assert not first["cache_hit"] and [f.name for f in cache.iterdir()] == [f.name for f in cache.glob("history_*.csv.gz")]      # no temp file left
    assert acquisition.bars(prov, secs, "2026-09-01", "2026-11-13", now, cache, "history")["cache_hit"] and prov.calls == 1
    path = next(cache.iterdir())
    path.write_bytes(path.read_bytes()[:20])                                            # cut short
    again = acquisition.bars(prov, secs, "2026-09-01", "2026-11-13", now, cache, "history")
    assert not again["cache_hit"] and again["stale_cache_found"] and prov.calls == 2 and len(again["bars"]) == 1


# ---------------------------------------------------------------------- C2: the KRX panel
def test_the_panel_is_built_under_a_lock_with_its_own_temp_file_and_a_waiter_reads_the_result(tmp_path, monkeypatch):
    from tests.test_kr_bars import DAYS, row, write
    write(tmp_path, {d: [row("005930", 10, 11, 9, 10, 0.0, 100)] for d in DAYS})
    first = kr_bars.panel(tmp_path, today=pd.Timestamp(DAYS[-1]).date())
    folder = (tmp_path / kr_bars.CACHE).parent
    assert first["dates"] == DAYS and sorted(f.name for f in folder.glob("krx_panel*")) == ["krx_panel.npz", "krx_panel.npz.lock"]
    monkeypatch.setattr(kr_bars, "build_panel", lambda *a: pytest.fail("built again though the stored panel covers the days"))
    again = kr_bars.panel(tmp_path, today=pd.Timestamp(DAYS[-1]).date())
    assert again["dates"] == DAYS and np.array_equal(again["data"], first["data"], equal_nan=True)
    (tmp_path / kr_bars.CACHE).write_bytes(b"cut")                                       # a stored panel that cannot be read is rebuilt, not fatal
    assert kr_bars._kept(tmp_path / kr_bars.CACHE, DAYS) is None


# ---------------------------------------------------------------------- C3, C4: the write-once stores
def store(tmp_path, days=("2026-11-10", "2026-11-11")):
    for n, day in enumerate(days):
        assert kf.write_record(tmp_path, day, NOW + timedelta(days=n), False, store=kf.FOLDER, scorer=lambda b, d: {"session": d, "rows": [{"t": 1}]})
    return tmp_path / kf.FOLDER


def test_a_cut_last_index_line_keeps_the_rows_before_it_readable_and_stops_new_records(tmp_path):
    folder = store(tmp_path)
    assert (folder / "write.lock").exists() and kf.verify(tmp_path)["status"] == "OK" and "torn_index" not in kf.verify(tmp_path)
    with open(folder / "index.jsonl", "a", encoding="utf-8") as fh:
        fh.write('{"session": "2026-11-12", "recorded_at": "2026-11')                    # the disk filled up here
    assert [r["session"] for r in kf.read_index(tmp_path)] == ["2026-11-10", "2026-11-11"] and kf.index_torn(tmp_path)
    check = kf.verify(tmp_path)
    assert check["status"] == "BROKEN" and check["torn_index"] is True and check["bad"] == [] and check["sessions"] == 2
    before = (folder / "index.jsonl").read_bytes()
    with pytest.raises(RuntimeError, match="INDEX_TORN"):
        kf.write_record(tmp_path, "2026-11-12", NOW, False, store=kf.FOLDER, scorer=lambda b, d: {"session": d, "rows": []})
    assert (folder / "index.jsonl").read_bytes() == before and not (folder / "2026-11-12.json.gz").exists()      # nothing welded onto the cut line


def test_a_bad_line_in_the_middle_of_an_index_is_not_hidden(tmp_path):
    folder = store(tmp_path)
    lines = (folder / "index.jsonl").read_text(encoding="utf-8").splitlines()
    (folder / "index.jsonl").write_text(lines[0][:30] + "\n" + lines[1] + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        kf.read_index(tmp_path)


def test_a_day_is_written_once_however_often_it_is_asked(tmp_path):
    folder = store(tmp_path, days=("2026-11-10",))
    assert kf.write_record(tmp_path, "2026-11-10", NOW, False, store=kf.FOLDER, scorer=lambda b, d: pytest.fail("scored a day already written")) is False
    assert len(kf.read_index(tmp_path)) == 1 and kf.verify(tmp_path)["status"] == "OK"
    assert "fcntl.flock(lock, fcntl.LOCK_EX)" in open(kf.__file__, encoding="utf-8").read().split("def write_record")[1].split("\ndef ")[0]


def test_the_score_ledger_and_the_top_three_read_past_a_cut_line_and_refuse_to_append(tmp_path):
    lg = ledger.Ledger(tmp_path)
    lg.append(SESSION, "US", [card()])
    with open(lg.index, "a", encoding="utf-8") as fh:
        fh.write('{"seq": 2, "session": "2026-11-0')
    idx = lg.read_index()
    assert idx["status"] == "BROKEN" and len(idx["rows"]) == 1 and len(lg.snapshots(market="US")) == 1          # what was recorded is still read
    with pytest.raises(RuntimeError):
        lg.append("2026-11-05", "US", [card()])
    folder = tmp_path / top_picks.FOLDER
    folder.mkdir(parents=True)
    (folder / "index.jsonl").write_text('{"session": "2026-11-0', encoding="utf-8")
    assert top_picks._index(folder) == ([], "BROKEN")
    with pytest.raises(RuntimeError):
        top_picks.write(tmp_path, {"session": "2026-11-09", "market": "US"})


# ---------------------------------------------------------------------- C5: a full disk
def test_a_cache_that_cannot_write_still_returns_what_was_fetched(tmp_path, monkeypatch):
    cache = FileCache(tmp_path / "c", clock=lambda: 1000.0)
    monkeypatch.setattr(cache, "write", lambda key, data: (_ for _ in ()).throw(OSError(28, "No space left on device")))
    got = cache.cached("k", 60, lambda: {"v": 1})
    assert got["status"] == "REAL" and got["data"] == {"v": 1} and got["error"] == "NOT_STORED" and got["age_s"] == 0.0
    assert cache.read("k") is None


# ---------------------------------------------------------------------- D3: the Korean bar cache
def test_old_korean_bar_windows_are_listed_then_removed_and_nothing_else_is(tmp_path):
    root = tmp_path / storage.KR_CACHE
    root.mkdir(parents=True)
    names = [f"{tag}_2026-09-0{n}_2026-11-0{n}_{'ab12cd34ef56'}.csv.gz" for n in range(1, 6) for tag in ("universe", "history")]
    for name in names + ["notes.txt", "universe_2026-09-01_2026-11-01_short.csv.gz"]:
        (root / name).write_bytes(b"x" * 10)
    rep = storage.prune_kr_bars(tmp_path)
    assert rep["windows"] == 5 and rep["old_windows"] == ["2026-11-01", "2026-11-02"] and rep["old_files"] == 4 and rep["removed"] == 0 and len(list(root.iterdir())) == 12
    done = storage.prune_cache(tmp_path, apply=True)
    assert done["kr_bars"]["removed"] == 4 and done["applied"] is True
    left = sorted(f.name for f in root.iterdir())
    assert len(left) == 8 and "notes.txt" in left and "universe_2026-09-01_2026-11-01_short.csv.gz" in left and not any("_2026-11-02_" in f for f in left)
    with pytest.raises(ValueError):
        storage.prune_kr_bars(tmp_path, keep=0)


def test_only_old_temp_files_of_a_killed_write_are_removed(tmp_path):
    qsf, kr = tmp_path / "data" / "qsf", tmp_path / storage.KR_CACHE
    qsf.mkdir(parents=True)
    kr.mkdir(parents=True)
    names = [qsf / "bars_KR.json.gz.4242.tmp", qsf / "krx_panel.npz.4242.tmp.npz", kr / "history_2026-09-01_2026-11-13_ab12cd34ef56.csv.gz.77.tmp"]
    keep = [qsf / "bars_KR.json.gz", qsf / "krx_panel.npz", qsf / "krx_panel.npz.lock", qsf / "latest_KR.json.tmp", kr / "history_2026-09-01_2026-11-13_ab12cd34ef56.csv.gz"]
    for f in names + keep:
        f.write_bytes(b"x" * 5)
    late = lambda: names[0].stat().st_mtime + storage.TEMP_AGE_S + 5      # noqa: E731
    assert storage.prune_temps(tmp_path)["files"] == 0                                    # minutes old: a writer may still be at work
    assert storage.prune_temps(tmp_path, clock=late) == {"files": 3, "mb": 0.0, "applied": False, "removed": 0}
    assert storage.prune_temps(tmp_path, apply=True, clock=late)["removed"] == 3
    assert all(f.exists() for f in keep) and not any(f.exists() for f in names)
    assert storage.prune_cache(tmp_path)["temps"] == {"files": 0, "mb": 0.0, "applied": False, "removed": 0}


# ---------------------------------------------------------------------- E1, E2: the server's error log
def test_a_client_that_left_is_not_an_error_and_an_unreadable_stored_file_is(live, tmp_path):  # noqa: F811
    httpd, t = live
    path = server.setup_error_log(tmp_path)
    try:
        def gone(market="US"):
            raise BrokenPipeError(32, "Broken pipe")

        def unreadable(market="US"):
            return json.loads('{"cut": ')

        def bad_input(market="US"):
            raise ValueError("INVALID_TICKER")
        base = f"http://127.0.0.1:{httpd.server_port}"
        t.overview = gone
        with pytest.raises(Exception):                                                   # the handler answers nothing: the client "left"
            urllib.request.urlopen(base + "/api/overview", timeout=5)
        t.overview = unreadable
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/overview", timeout=10)
        assert e.value.code == 500 and json.loads(e.value.read())["type"] == "JSONDecodeError"
        t.overview = bad_input
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/api/overview", timeout=10)
        assert e.value.code == 400 and json.loads(e.value.read()) == {"error": "INVALID_TICKER"}
        for h in server.log.handlers:
            h.flush()
        text = path.read_text(encoding="utf-8")
        assert "BrokenPipeError" not in text and text.count("api error on GET /api/overview") == 1 and "JSONDecodeError" in text
        with urllib.request.urlopen(base + "/api/health", timeout=10) as r:
            tally = json.loads(r.read())["server_errors"]
        assert tally["count"] == 1 and tally["last"]["type"] == "JSONDecodeError"
    finally:
        for h in list(server.log.handlers):
            if getattr(h, "baseFilename", "") == str(path):
                server.log.removeHandler(h)
                h.close()
    assert server.GONE == (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) and logging.getLogger(server.log.name) is server.log
