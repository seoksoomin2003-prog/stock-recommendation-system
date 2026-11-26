"""Windows port (2026-11-27): the shared lock module, the scheduler definition and the entry guard.  The lock tests run on
whichever system runs the suite, so the Windows run checks the Windows lock and the Mac run the Mac's."""
import os
import subprocess
import sys
import xml.dom.minidom
from pathlib import Path

import pytest

from terminal import automation, win_tasks
from utils import fcntl_port

ROOT = Path(__file__).resolve().parents[1]
HOLD = """
import sys, time
sys.path.insert(0, sys.argv[1])
from utils import fcntl_port as fcntl
with open(sys.argv[2], "w") as fh:
    fcntl.flock(fh, fcntl.LOCK_EX)
    print("held", flush=True)
    time.sleep(float(sys.argv[3]))
"""


def test_a_lock_held_by_another_process_refuses_a_second_holder_and_frees_on_exit(tmp_path):
    lock = tmp_path / "run.lock"
    other = subprocess.Popen([sys.executable, "-c", HOLD, str(ROOT), str(lock), "30"], stdout=subprocess.PIPE, text=True)
    try:
        assert other.stdout.readline().strip() == "held"
        with open(lock, "a") as fh:
            with pytest.raises(OSError):
                fcntl_port.flock(fh, fcntl_port.LOCK_EX | fcntl_port.LOCK_NB)
        assert fcntl_port.pid_alive(other.pid)
    finally:
        other.kill()
        other.wait()
    assert not fcntl_port.pid_alive(other.pid)
    with open(lock, "a") as fh:                                   # the holder is gone: the lock is free
        fcntl_port.flock(fh, fcntl_port.LOCK_EX | fcntl_port.LOCK_NB)
        fcntl_port.flock(fh, fcntl_port.LOCK_UN)


def test_a_locked_record_file_can_still_be_read_and_appended_by_its_holder(tmp_path):
    f = tmp_path / "rows.jsonl"
    f.write_text("a\n", encoding="utf-8")
    with open(f, "a", encoding="utf-8") as fh:
        fcntl_port.flock(fh, fcntl_port.LOCK_EX)
        fh.write("b\n")
        fh.flush()
        assert f.read_text(encoding="utf-8") == "a\nb\n"          # the lock is a byte past the end, never the data
    assert fcntl_port.pid_alive(os.getpid()) and not fcntl_port.pid_alive(0)


def test_the_windows_task_runs_the_same_command_at_the_same_times_without_a_secret(tmp_path):
    doc = win_tasks.task_xml(tmp_path, tmp_path / "data" / "automation" / "launchd.log", ["automation", "run"], automation.SCHEDULE)
    dom = xml.dom.minidom.parseString(doc.replace('encoding="UTF-16"', ""))
    assert len(dom.getElementsByTagName("CalendarTrigger")) == len(automation.SCHEDULE) and len(dom.getElementsByTagName("LogonTrigger")) == 1
    args = dom.getElementsByTagName("Arguments")[0].firstChild.data
    assert '"automation" "run"' in args and "win_launch.py" in args and '"-X" "utf8"' in args
    assert dom.getElementsByTagName("DisallowStartIfOnBatteries")[0].firstChild.data == "false"
    assert "RestartOnFailure" not in doc and "TOKEN" not in doc.upper().replace("INTERACTIVETOKEN", "") and "KEY" not in doc.upper()
    server = win_tasks.task_xml(tmp_path, tmp_path / "l.log", ["terminal", "--port", "8765"], keep_alive=True)
    assert "RestartOnFailure" in server and "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in server and "CalendarTrigger" not in server


def test_no_module_imports_the_mac_only_lock_module_directly():
    for folder in ("terminal", "pipeline", "utils", "markets", "core"):
        for p in (ROOT / folder).rglob("*.py"):
            if p.name != "fcntl_port.py":
                assert "\nimport fcntl\n" not in p.read_text(encoding="utf-8"), p
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert '"-X", "utf8"' in app and "stay_awake" in app
    for name in ("1 처음 설치.bat", "2 자동 실행 등록.bat", "서버 다시 시작.bat", "지금 수집.bat", "자동 실행 해제.bat"):
        body = (ROOT / "ops" / "windows" / name).read_bytes()
        assert body.startswith(b"@echo off\r\nchcp 65001") and b"\r\n" in body and b"\n" not in body.replace(b"\r\n", b"")
