"""The Korean model scan started from the screen: the documented command, one at a time, and its ending read from the run folder."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from terminal import model_scan as ms

AT = datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc)


class FakeProc:
    def __init__(self, pid):
        self.pid = pid


def starter(calls, pid):
    def popen(cmd, **kw):
        calls.append((cmd, kw))
        return FakeProc(pid)
    return popen


def write_run(base, name, executed_at, mode="kr_market_scan", scope="full"):
    d = base / ms.RUNS / name
    d.mkdir(parents=True)
    (d / "validation_result.json").write_text(json.dumps({"run_id": name, "mode": mode, "executed_at": executed_at, "recommendation_status": "REAL RECOMMENDATION",
                                                           "latest_session": "2026-11-11", "validation_scope": scope, "capital_krw": 10_000_000}), encoding="utf-8")


def test_the_button_runs_the_documented_command_detached_and_nothing_from_the_request(tmp_path):
    calls = []
    got = ms.start(tmp_path, popen=starter(calls, os.getpid()), now=lambda: AT)
    cmd, kw = calls[0]
    tail = cmd[-5:] if Path(ms.CAFFEINATE).exists() else cmd
    assert got == {"status": "STARTED", "started_at": AT.isoformat()} and tail == [sys.executable, str(tmp_path / "app.py"), "--market", "KR", "scan"]
    assert kw["cwd"] == tmp_path and kw["start_new_session"] is True and (tmp_path / ms.LOG).exists()
    assert json.loads((tmp_path / ms.MARKER).read_text()) == {"pid": os.getpid(), "started_at": AT.isoformat()}
    assert ms.status(tmp_path) == {"status": "RUNNING", "started_at": AT.isoformat()}
    again = ms.start(tmp_path, popen=starter(calls, 1), now=lambda: AT)                 # the first one is alive (this test's own pid)
    assert again["status"] == "ALREADY_RUNNING" and len(calls) == 1


def test_an_ended_scan_reads_as_done_with_the_run_it_wrote_or_as_failed_when_it_wrote_none(tmp_path):
    assert ms.status(tmp_path) == {"status": "IDLE"}
    dead = 2 ** 22 + 12345                                                              # no such process
    ms.start(tmp_path, popen=starter([], dead), now=lambda: AT)
    write_run(tmp_path, "20261111T090000Z_kr_market_scan_old", "2026-11-11T09:00:00+00:00")           # a run from before this start is not its result
    write_run(tmp_path, "20261112T030100Z_kr_direct_evaluation_x", "2026-11-12T03:01:00+00:00", mode="kr_direct_evaluation")
    failed = ms.status(tmp_path)
    assert failed == {"status": "FAILED", "started_at": AT.isoformat(), "log": str(ms.LOG)}
    write_run(tmp_path, "20261112T030005Z_kr_market_scan_new", "2026-11-12T03:00:05+00:00")
    done = ms.status(tmp_path)
    assert done["status"] == "DONE" and done["run"]["run_id"].endswith("_new") and done["run"]["latest_session"] == "2026-11-11" and done["run"]["scope"] == "full"
    calls = []
    assert ms.start(tmp_path, popen=starter(calls, dead), now=lambda: AT)["status"] == "STARTED" and len(calls) == 1      # an ended scan does not block the next


def test_the_screen_route_refuses_without_saved_capital_and_never_starts_a_us_scan(tmp_path, monkeypatch):
    from terminal.services import Terminal
    from tests.test_terminal_1 import AFTER, fake_src
    started = []
    monkeypatch.setattr(ms, "start", lambda base: started.append(base) or {"status": "STARTED", "started_at": "x"})
    monkeypatch.delenv("QPP_CAPITAL_KRW", raising=False)
    t = Terminal(tmp_path, src=fake_src(), now=lambda: AFTER)
    assert t.model_scan_start({"market": "KR"}) == {"status": "NO_CAPITAL"} and started == []
    with pytest.raises(ValueError, match="한국 스캔만"):
        t.model_scan_start({"market": "US"})
    monkeypatch.setenv("QPP_CAPITAL_KRW", "10000000")
    monkeypatch.setenv("QPP_CAPITAL", "5000")
    assert t.model_scan_start({"market": "KR"})["status"] == "STARTED" and started == [tmp_path]
    assert t.model_scan_start({})["status"] == "STARTED"


def test_the_button_is_wired_into_the_server_and_the_model_tab_for_korea_only():
    root = Path(__file__).resolve().parents[1]
    server = (root / "terminal" / "server.py").read_text(encoding="utf-8")
    assert '("GET", "/api/model/scan")' in server and '("POST", "/api/model/scan")' in server
    js = (root / "terminal" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'id="capRun"' in js and 'mk === "KR" ? \'<button id="capRun"' in js and "먼저 금액을 저장하세요" in js and "40분쯤 걸릴 수 있습니다" in js
    assert "python app.py --market KR scan</code>으로 실행하세요" not in js


def test_a_real_child_that_ends_at_once_is_not_left_reading_as_running(tmp_path):
    """No app.py in the folder: the started interpreter ends immediately.  An uncollected child would still answer a signal."""
    import time
    got = ms.start(tmp_path)
    assert got["status"] == "STARTED"
    deadline = time.time() + 20
    while ms.status(tmp_path)["status"] == "RUNNING" and time.time() < deadline:
        time.sleep(0.2)
    assert ms.status(tmp_path)["status"] == "FAILED" and ms.start(tmp_path)["status"] == "STARTED"
    while ms.status(tmp_path)["status"] == "RUNNING" and time.time() < deadline:
        time.sleep(0.2)
