"""Windows: the daily job and the terminal server as Task Scheduler entries (2026-11-27, Windows port).

The Mac keeps both with launchd agents (``automation.install``, ``server_agent.install``).  Windows has no launchd; the same
two things are Task Scheduler entries of the signed-in user, made and removed with ``schtasks`` (part of Windows):

* ``QuantEngine Daily``: ``app.py automation run`` at each time of ``automation.SCHEDULE`` (the computer's clock, as on the
  Mac) and at sign-in.  A run that finds nothing to do ends at once, as on the Mac.
* ``QuantEngine Terminal``: ``app.py terminal --port 8765`` at sign-in, started again a minute after any exit.

Both run only while the user is signed in (no password is stored), also on battery, and start late when the time was missed.
They run ``pythonw.exe`` through ``ops/win_launch.py``: no console window, output to the same log files as on the Mac.
Nothing from ``.env`` is copied into a task.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple
from xml.sax.saxutils import escape

DAILY, SERVER = "QuantEngine Daily", "QuantEngine Terminal"
TIMEOUT_S = 20


def pythonw() -> str:
    """The windowless interpreter beside the running one (``.venv\\Scripts\\pythonw.exe``); the running one when there is none."""
    p = Path(sys.executable).with_name("pythonw.exe")
    return str(p if p.exists() else sys.executable)


def _schtasks(*args: str):
    try:
        return subprocess.run(["schtasks", *args], capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(["schtasks", *args], 124, b"", b"TIMEOUT")
    except OSError:
        return subprocess.CompletedProcess(["schtasks", *args], 127, b"", b"NO_SCHTASKS")


def _err(res) -> str:
    raw = (res.stderr or b"") or (res.stdout or b"")
    if isinstance(raw, str):
        return raw.strip()
    for enc in ("utf-8", "cp949", "mbcs"):
        try:
            return raw.decode(enc).strip()
        except (UnicodeDecodeError, LookupError):
            continue
    return "SCHTASKS_FAILED"


def task_xml(base: Path, log: Path, app_args: Sequence[str], times: Sequence[Tuple[int, int]] = (), keep_alive: bool = False) -> str:
    """The task definition.  ``times``: (hour, minute) daily starts; a sign-in start is always there.  ``keep_alive``: started
    again a minute after it stops, never ended for running long (the server)."""
    base = Path(base)
    triggers = ["<LogonTrigger><Enabled>true</Enabled></LogonTrigger>"]
    triggers += [f"<CalendarTrigger><StartBoundary>2026-01-01T{h:02d}:{m:02d}:00</StartBoundary><Enabled>true</Enabled>"
                 f"<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>" for h, m in times]
    args = " ".join(f'"{a}"' for a in ["-X", "utf8", str(base / "ops" / "win_launch.py"), str(log), *app_args])
    restart = "<RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>" if keep_alive else ""
    limit = "PT0S" if keep_alive else "PT12H"
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Quant terminal ({escape(" ".join(app_args))})</Description></RegistrationInfo>
  <Triggers>{"".join(triggers)}</Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowHardTerminate>true</AllowHardTerminate>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>{limit}</ExecutionTimeLimit>
    {restart}
  </Settings>
  <Actions Context="Author"><Exec>
    <Command>{escape(pythonw())}</Command>
    <Arguments>{escape(args)}</Arguments>
    <WorkingDirectory>{escape(str(base))}</WorkingDirectory>
  </Exec></Actions>
</Task>
"""


def _create(name: str, xml: str) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "task.xml"
        f.write_bytes(b"\xff\xfe" + xml.encode("utf-16-le"))
        res = _schtasks("/Create", "/TN", name, "/XML", str(f), "/F")
    return {"installed": res.returncode == 0, "task": name, "error": _err(res) if res.returncode else None}


def is_installed(name: str) -> bool:
    return _schtasks("/Query", "/TN", name).returncode == 0


def _remove(name: str) -> Dict[str, Any]:
    _schtasks("/End", "/TN", name)
    _schtasks("/Delete", "/TN", name, "/F")
    return {"installed": False}


# ------------------------------------------------------------------ the two tasks
def install_daily(base: Path, times: Sequence[Tuple[int, int]]) -> Dict[str, Any]:
    base = Path(base)
    log = base / "data" / "automation" / "launchd.log"                  # the same file name as on the Mac: the screens read it
    log.parent.mkdir(parents=True, exist_ok=True)
    return {**_create(DAILY, task_xml(base, log, ["automation", "run"], times)), "path": DAILY}


def uninstall_daily() -> Dict[str, Any]:
    return _remove(DAILY)


def install_server(base: Path, port: int) -> Dict[str, Any]:
    base = Path(base)
    log = base / "data" / "terminal" / "logs" / "launchd.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    res = _create(SERVER, task_xml(base, log, ["terminal", "--port", str(int(port))], keep_alive=True))
    if res["installed"]:
        _schtasks("/Run", "/TN", SERVER)                                   # the Mac's agent starts at load; so does this
    return {**res, "path": SERVER, "port": port}


def uninstall_server() -> Dict[str, Any]:
    return _remove(SERVER)


def server_status(base: Path, port: int) -> Dict[str, Any]:
    return {"installed": is_installed(SERVER), "port": port, "log": str(Path(base) / "data" / "terminal" / "logs" / "launchd.log")}
