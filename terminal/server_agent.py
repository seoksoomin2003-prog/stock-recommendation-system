"""Keep the terminal server running: a macOS launchd agent that starts it at login and restarts it when it stops.

``app.py terminal-agent install`` writes ``~/Library/LaunchAgents/com.quantengine.terminal.plist`` and loads it;
``uninstall`` stops the server and removes the file.  The server is the same ``app.py terminal --port 8765`` a person would
start by hand (it listens on this Mac only).  launchd restarts it after any exit, at most every ``THROTTLE_S`` seconds, so a
crash or a broken start never spins.

Like the daily automation agent, a login shell supplies the user's environment and nothing from ``.env`` is copied into
the plist.  The shell, not launchd, opens the start-up log, so the log can be rotated at each start and a repeated failure
cannot fill the disk.  Request errors go to the server's own rotating log (``server.setup_error_log``).
"""
import os
import plistlib
import shlex
import sys
from pathlib import Path
from typing import Any, Dict

from terminal.automation import _launchctl

LABEL = "com.quantengine.terminal"
PORT = 8765
THROTTLE_S = 30
LOG_MAX_BYTES = 1_000_000


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def log_path(base: Path) -> Path:
    return Path(base) / "data" / "terminal" / "logs" / "launchd.log"


def plist_bytes(base: Path, port: int = PORT) -> bytes:
    log = shlex.quote(str(log_path(base)))
    cmd = (f"cd {shlex.quote(str(base))} && "
           f"if [ -f {log} ] && [ $(stat -f%z {log}) -gt {LOG_MAX_BYTES} ]; then mv -f {log} {log}.1; fi; "
           f"exec {shlex.quote(sys.executable)} app.py terminal --port {int(port)} >> {log} 2>&1 < /dev/null")
    return plistlib.dumps({
        "Label": LABEL, "ProgramArguments": ["/bin/zsh", "-lc", cmd],
        "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": THROTTLE_S})


def install(base: Path, port: int = PORT) -> Dict[str, Any]:
    log_path(base).parent.mkdir(parents=True, exist_ok=True)
    p = plist_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", domain, str(p))                     # a reinstall replaces the old definition
    p.write_bytes(plist_bytes(base, port))
    res = _launchctl("bootstrap", domain, str(p))
    return {"installed": res.returncode == 0, "path": str(p), "port": port, "error": res.stderr.strip() if res.returncode else None}


def uninstall() -> Dict[str, Any]:
    p = plist_path()
    _launchctl("bootout", f"gui/{os.getuid()}", str(p))       # also stops the server it started
    p.unlink(missing_ok=True)
    return {"installed": False}


def status(base: Path) -> Dict[str, Any]:
    res = _launchctl("print", f"gui/{os.getuid()}/{LABEL}")
    loaded = plist_path().exists() and res.returncode == 0
    info = {}
    for line in res.stdout.splitlines() if loaded else []:
        key, _, value = line.strip().partition(" = ")
        if key in ("state", "pid", "runs", "last exit code"):
            info[key.replace(" ", "_")] = value
    return {"installed": loaded, "port": PORT, **info, "log": str(log_path(base))}
