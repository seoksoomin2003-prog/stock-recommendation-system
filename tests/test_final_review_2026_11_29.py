"""Final latency and stability review, 2026-11-29 (user decision: fix both lists).  No score, record content or provider
pacing is touched: a cut record line can be mended from the button, the daily job writes nothing on a nearly full disk, a
key file saved by a Windows editor still loads, a scan marker is not believed for ever, and what one screen request asks for
many times is built once."""
import json
import os
import threading
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from terminal import automation, model_scan, restore, storage, symbols
from terminal.qsf import ledger as ledger_mod
from terminal.qsf.ledger import Ledger
from utils import durable, reqmemo, runtime_config

ROOT = Path(__file__).resolve().parents[1]


def test_a_cut_last_line_is_mended_by_the_button_and_never_by_a_writer(tmp_path):
    store = tmp_path / "research_data" / "a"
    durable.append_chained(store, "2026-11.jsonl", [{"x": 1}, {"x": 2}])
    f = store / "2026-11.jsonl"
    f.write_bytes(f.read_bytes() + b'{"x": 3, "cha')                           # the disk ran out in the middle of a line
    with pytest.raises(durable.TornFile):
        durable.append_chained(store, "2026-11.jsonl", [{"x": 9}])              # a writer still refuses: it never repairs
    whole = tmp_path / "research_data" / "b"
    durable.append_chained(whole, "2026-11.jsonl", [{"x": 1}])
    g = whole / "2026-11.jsonl"
    g.write_bytes(g.read_bytes().rstrip(b"\n"))                                 # a whole record that only lacks its line break
    res = restore.repair_ledger(tmp_path, backups=[])
    assert res["status"] == "REPAIRED" and {(m["file"], m["what"]) for m in res["mended"]} == {("research_data/a/2026-11.jsonl", "CUT"), ("research_data/b/2026-11.jsonl", "CLOSED")}
    assert durable.verify_chained(store) == {"status": "OK", "lines": 2} and durable.verify_chained(whole) == {"status": "OK", "lines": 1}
    kept = list((store / restore.ASIDE).iterdir())
    assert len(kept) == 1 and kept[0].read_bytes() == b'{"x": 3, "cha'           # the fragment is kept, never deleted
    assert durable.append_chained(store, "2026-11.jsonl", [{"x": 9}]) == 1 and restore.repair_ledger(tmp_path, backups=[])["status"] == "NOTHING_TO_DO"
    bad = tmp_path / "x.jsonl"
    bad.write_bytes(b'not json\n{"cut')
    assert durable.mend_tail(bad, "S") == "UNREADABLE" and bad.read_bytes() == b'not json\n{"cut'      # an earlier unreadable line: nothing is changed
    assert durable.mend_tail(tmp_path / "missing.jsonl", "S") is None


def test_the_score_ledgers_own_index_is_mended_too(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "snapshot", lambda card: card)             # the shape of a card is not what this is about
    led = Ledger(tmp_path)
    led.append("2026-11-27", "US", [{"ticker": "A", "strategy": "SWING", "score": 60.0, "data_date": "2026-11-27"}])
    with open(led.index, "ab") as fh:
        fh.write(b'{"seq": 2, "sess')
    assert led.read_index()["status"] != "OK"
    res = restore.repair_ledger(tmp_path, backups=[])
    assert res["mended"] == [{"file": "data/qsf/ledger/index.jsonl", "what": "CUT"}] and led.read_index()["status"] == "OK" and res["integrity"] == "OK"
    assert led.append("2026-11-30", "US", [{"ticker": "A", "strategy": "SWING", "score": 61.0, "data_date": "2026-11-30"}])["recorded"] == 1


def test_the_daily_job_writes_nothing_on_a_nearly_full_disk_and_says_so_once_a_day(tmp_path, monkeypatch):
    Usage = namedtuple("Usage", "total used free")
    assert storage.too_full(tmp_path, lambda p: Usage(100, 99, storage.STOP_FREE - 1)) is not None
    assert storage.too_full(tmp_path, lambda p: Usage(100, 50, storage.STOP_FREE + 1)) is None
    monkeypatch.setattr(storage, "too_full", lambda base: 0.2)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path / "t"))
    (tmp_path / "t").mkdir()
    ran, told = [], []
    d = automation.Daily(tmp_path / "base", runner=lambda n, a: ran.append(n) or 0, telegram=lambda text: told.append(text) or {"status": "SENT"}, macos=lambda *a: {"status": "SENT"})
    first, second = d.run(), d.run()
    assert first["status"] == second["status"] == "DISK_FULL" and ran == [] and len(told) == 1 and "0.2GB" in told[0]
    assert not (tmp_path / "base" / "data" / "automation" / automation.RUNNING_FILE).exists()      # not even the marker was written


def test_a_key_file_saved_by_a_windows_editor_still_loads(tmp_path, monkeypatch):
    monkeypatch.delenv("QE_TEST_FIRST", raising=False)
    monkeypatch.delenv("QE_TEST_SECOND", raising=False)
    f = tmp_path / ".env"
    f.write_bytes("﻿QE_TEST_FIRST=one\n".encode("utf-8") + "# 한글 주석\n".encode("cp949") + b"QE_TEST_SECOND=two\n")
    got = runtime_config.load_local_env(f)
    assert got.get("QE_TEST_FIRST") == "one" and got.get("QE_TEST_SECOND") == "two"      # the byte-order mark is not part of the first key; another encoding does not stop the program
    monkeypatch.delenv("QE_TEST_FIRST", raising=False)
    monkeypatch.delenv("QE_TEST_SECOND", raising=False)
    assert 'os.environ.setdefault("PYTHONUTF8", "1")' in (ROOT / "app.py").read_text(encoding="utf-8") and "PYTHONUTF8" in (ROOT / "ops" / "win_launch.py").read_text(encoding="utf-8")


def test_a_scan_marker_is_not_believed_for_ever(tmp_path, monkeypatch):
    monkeypatch.setattr(model_scan, "_alive", lambda pid: True)                 # some program answers at that number
    f = tmp_path / model_scan.MARKER
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"pid": 1, "started_at": "2026-11-13T00:00:00+00:00"}), encoding="utf-8")
    m = model_scan._marker(tmp_path)
    wrote = f.stat().st_mtime
    assert model_scan._live(tmp_path, m, lambda: wrote + 600)                   # ten minutes on: running
    assert not model_scan._live(tmp_path, m, lambda: wrote + 16 * 86400)        # sixteen days on: the number belongs to something else
    assert model_scan.started_here(tmp_path) and not model_scan._live(tmp_path, None)
    monkeypatch.setattr(model_scan, "_alive", lambda pid: False)
    assert not model_scan._live(tmp_path, m, lambda: wrote + 600)


def test_one_request_builds_a_thing_once_and_nothing_outlives_the_request():
    n = []
    build = lambda: n.append(1) or {"v": len(n)}      # noqa: E731
    assert reqmemo.get("k", build) == {"v": 1} and reqmemo.get("k", build) == {"v": 2}       # outside a request nothing is kept
    with reqmemo.scope():
        assert reqmemo.get("k", build) is reqmemo.get("k", build) and len(n) == 3
        with reqmemo.scope():
            assert reqmemo.get("k", build)["v"] == 3                            # an inner scope shares the outer one
        seen = []
        th = threading.Thread(target=lambda: seen.append(reqmemo.get("k", build)["v"]))
        th.start(); th.join()
        assert seen == [4]                                                      # another thread is another request
    assert reqmemo.get("k", build) == {"v": 5}
    src = (ROOT / "terminal" / "server.py").read_text(encoding="utf-8")
    assert "with reqmemo.scope():" in src and src.index("with writes:") < src.index("with reqmemo.scope():")      # reads only: a write is never answered from memory


def test_the_newest_scan_is_read_once_a_request_and_each_caller_gets_its_own_rows(tmp_path):
    from terminal.qsf import views
    calls = []

    class Q(views.Views if hasattr(views, "Views") else object):
        pass

    owner = next(v for v in vars(views).values() if isinstance(v, type) and "_latest_built" in vars(v))
    q = owner.__new__(owner)
    q._latest_built = lambda market="US": calls.append(market) or {"status": "REAL", "rows": [{"ticker": "A", "score": 1.0}]}
    with reqmemo.scope():
        a, b = q.latest("US"), q.latest("US")
        a["rows"][0]["added"] = True
        a["rows"].append({"ticker": "Z"})
        assert calls == ["US"] and "added" not in b["rows"][0] and len(q.latest("US")["rows"]) == 1
        q.latest("KR")
    assert calls == ["US", "KR"]
    q.latest("US")
    assert calls == ["US", "KR", "US"]                                          # the next request reads the file again


def test_a_session_of_the_record_is_parsed_once_while_the_index_stays_as_it_is(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_mod, "snapshot", lambda card: card)
    led = Ledger(tmp_path)
    led.append("2026-11-27", "US", [{"ticker": "A", "strategy": "SWING", "score": 60.0, "data_date": "2026-11-27"}])
    loads = []
    real = led._load
    monkeypatch.setattr(led, "_load", lambda row: loads.append(row["file"]) or real(row))
    one = ledger_mod.session_snaps(led, "US", "2026-11-27")
    one[0]["score"] = -1                                                        # a caller's change never reaches the kept copy
    two = ledger_mod.session_snaps(led, "US", "2026-11-27")
    assert len(loads) == 1 and two[0]["score"] == 60.0 and one is not two
    led.append("2026-11-30", "US", [{"ticker": "A", "strategy": "SWING", "score": 61.0, "data_date": "2026-11-30"}])
    assert ledger_mod.session_snaps(led, "US", "2026-11-27")[0]["score"] == 60.0 and len(loads) == 2      # the index changed: read again
    for day in ("2026-11-30", "2026-11-27", "2026-11-30"):
        ledger_mod.session_snaps(led, "US", day)
    assert len(led.__dict__["_snaps_kept"]) <= ledger_mod.SNAPS_KEPT

    class Plain:                                                                # a stand-in without an index: nothing is kept, as before
        def _live_rows(self): return [{"market": "US", "session": "d", "file": "f"}]
        def _load(self, row): return [{"ticker": "A"}]
    p = Plain()
    assert ledger_mod.session_snaps(p, "US", "d") == [{"ticker": "A"}] and "_snaps_kept" not in p.__dict__


def test_a_report_is_kept_while_the_index_bars_are_the_same_though_their_file_was_written_again(tmp_path):
    from terminal.qsf import views
    owner = next(v for v in vars(views).values() if isinstance(v, type) and "_cache_mark" in vars(v))
    q = owner.__new__(owner)
    f = tmp_path / "bars.json"

    class Cache:
        def _path(self, key): return f
    q.cache = Cache()
    assert q._cache_mark("k") is None                                           # no file: unknown
    f.write_text(json.dumps({"data": {"^KS11": [{"date": "2026-11-26", "close": 1.0}, {"date": "2026-11-27", "close": 2.0}]}}), encoding="utf-8")
    first = q._cache_mark("k")
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 10 ** 9))      # written again half an hour later with the same bars
    assert q._cache_mark("k") == first
    f.write_text(json.dumps({"data": {"^KS11": [{"date": "2026-11-26", "close": 1.0}, {"date": "2026-11-27", "close": 2.5}]}}), encoding="utf-8")
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 2 * 10 ** 9))
    assert q._cache_mark("k") != first                                          # a bar changed: the report is computed again


def test_the_search_box_builds_its_list_once_per_scan(tmp_path):
    class Qsf:
        dir = tmp_path
    class T:
        qsf = Qsf()
    for m in ("US", "KR"):
        (tmp_path / f"latest_{m}.json").write_text("{}", encoding="utf-8")
    asked = []
    rows = lambda t, m: asked.append(m) or [{"ticker": m + "1", "name": "n"}]     # noqa: E731
    t = T()
    a, b = symbols.universe_of(t, rows), symbols.universe_of(t, rows)
    assert a is b and asked == ["US", "KR"]
    f = tmp_path / "latest_US.json"
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 10 ** 9))      # a new scan
    symbols.universe_of(t, rows)
    assert asked == ["US", "KR", "US", "KR"]
