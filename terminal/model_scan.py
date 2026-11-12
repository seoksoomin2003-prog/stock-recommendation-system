"""The Korean model scan started from the screen.  It is the documented command, ``python app.py --market KR scan``, and nothing else.

The scan (experimental model KR-EXP-0.1) was built as a hand-run command; since 2026-11-12 the daily job also runs it as its
last step before the backup (user decision).  The button starts that same command detached from the server, one at a time and
never beside the daily job's own run, and the screen reads how it ended from the run folder the scan itself writes.  No argument
comes from the request.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

MARKER = Path("data") / "kr" / "model_scan.json"       # the scan in progress or the last one started: pid and start time
LOG = Path("data") / "kr" / "model_scan.log"
RUNS = Path("runs") / "KR"
CAFFEINATE = "/usr/bin/caffeinate"
COMMAND = ("--market", "KR", "scan")


def _marker(base: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads((Path(base) / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _alive(pid: Any) -> bool:
    """Whether the started process still runs.  A child of this server that has ended stays in the process table until it is
    collected, and would answer a signal as if alive, so it is collected here first."""
    try:
        pid = int(pid)
    except (ValueError, TypeError):
        return False
    try:
        if os.waitpid(pid, os.WNOHANG)[0] == pid:
            return False                    # this server's own child, ended
    except ChildProcessError:
        pass                                # not a child of this process: the server was restarted since the scan began
    except OSError:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def run_since(base: Path, started_at: str) -> Optional[Dict[str, Any]]:
    """The newest scan run that began at or after ``started_at`` and wrote its result; None when there is none."""
    root = Path(base) / RUNS
    for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True) if root.exists() else []:
        try:
            v = json.loads((d / "validation_result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if v.get("mode") == "kr_market_scan" and str(v.get("executed_at") or "") >= started_at:
            return {"run_id": v.get("run_id"), "executed_at": v.get("executed_at"), "recommendation_status": v.get("recommendation_status"),
                    "latest_session": v.get("latest_session"), "scope": v.get("validation_scope"), "capital": v.get("capital_krw")}
    return None


def started_here(base: Path) -> bool:
    """A scan started from the screen is still running."""
    m = _marker(base)
    return bool(m and _alive(m.get("pid")))


def _daily_job(base: Path) -> Optional[Dict[str, Any]]:
    """The daily job, when it is at its Korean model scan step right now."""
    from terminal import automation
    r = automation.running(Path(base))
    return r if r and r.get("step") == "SCAN_KR" else None


def status(base: Path) -> Dict[str, Any]:
    """RUNNING while the started process lives, or while the daily job runs the same scan.  Afterwards DONE with the run it
    wrote, or FAILED when it wrote none."""
    job = _daily_job(base)
    if job:
        return {"status": "RUNNING", "started_at": job.get("started_at"), "by": "DAILY_JOB"}
    m = _marker(base)
    if not m:
        return {"status": "IDLE"}
    if _alive(m.get("pid")):
        return {"status": "RUNNING", "started_at": m.get("started_at")}
    run = run_since(Path(base), str(m.get("started_at") or ""))
    if run:
        return {"status": "DONE", "started_at": m.get("started_at"), "run": run}
    return {"status": "FAILED", "started_at": m.get("started_at"), "log": str(LOG)}


def start(base: Path, popen: Callable = subprocess.Popen, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> Dict[str, Any]:
    """Start the scan unless one started here is still running.  Held awake against idle sleep while it runs."""
    base = Path(base)
    job = _daily_job(base)
    if job:
        return {"status": "ALREADY_RUNNING", "started_at": job.get("started_at"), "by": "DAILY_JOB"}
    m = _marker(base)
    if m and _alive(m.get("pid")):
        return {"status": "ALREADY_RUNNING", "started_at": m.get("started_at")}
    folder = (base / MARKER).parent
    folder.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(base / "app.py"), *COMMAND]
    if Path(CAFFEINATE).exists():
        cmd = [CAFFEINATE, "-i", *cmd]
    at = now().isoformat()
    with open(base / LOG, "w", encoding="utf-8") as fh:
        proc = popen(cmd, cwd=base, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    tmp = (base / MARKER).with_suffix(".tmp")
    tmp.write_text(json.dumps({"pid": proc.pid, "started_at": at}), encoding="utf-8")
    tmp.replace(base / MARKER)
    return {"status": "STARTED", "started_at": at}
