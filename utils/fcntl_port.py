"""File locks and the few process calls that differ between macOS/Linux and Windows (2026-11-27, Windows port).

Modules import this in place of the standard ``fcntl`` (``from utils import fcntl_port as fcntl``), so every lock site reads as
before.  On macOS and Linux each name is the standard library's own: nothing about the Mac program changes.  On Windows, which
has no ``fcntl``, ``flock`` is built on ``msvcrt.locking``:

* The lock is one byte far past the end of the file (``_FAR``).  A Windows byte lock is mandatory, so locking real bytes would
  stop another process from reading them; a byte nobody reads or writes only says "held".
* A blocking lock waits as long as it takes (``msvcrt`` alone gives up after ten seconds).
* ``LOCK_NB`` raises ``BlockingIOError`` (an ``OSError``) when another holder has it, as ``fcntl.flock`` does.
* Closing the file releases the lock, as on the Mac.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any, Dict, List

WINDOWS = os.name == "nt"

if not WINDOWS:
    import fcntl as _fcntl

    LOCK_EX, LOCK_NB, LOCK_UN, LOCK_SH = _fcntl.LOCK_EX, _fcntl.LOCK_NB, _fcntl.LOCK_UN, _fcntl.LOCK_SH
    flock = _fcntl.flock
    fcntl = _fcntl.fcntl
    if hasattr(_fcntl, "F_FULLFSYNC"):
        F_FULLFSYNC = _fcntl.F_FULLFSYNC
else:
    import msvcrt

    LOCK_SH, LOCK_EX, LOCK_NB, LOCK_UN = 1, 2, 4, 8
    _FAR = 0x7FFFFFF0
    _WAIT_S = 0.05

    def _fd(f: Any) -> int:
        return f if isinstance(f, int) else f.fileno()

    def _at_far(fd: int, mode: int) -> None:
        pos = os.lseek(fd, 0, os.SEEK_CUR)
        try:
            os.lseek(fd, _FAR, os.SEEK_SET)
            msvcrt.locking(fd, mode, 1)
        finally:
            os.lseek(fd, pos, os.SEEK_SET)

    def flock(f: Any, op: int) -> None:
        fd = _fd(f)
        if op & LOCK_UN:
            try:
                _at_far(fd, msvcrt.LK_UNLCK)
            except OSError:
                pass                                   # not held by this handle: unlocking is not an error on the Mac either
            return
        while True:
            try:
                _at_far(fd, msvcrt.LK_NBLCK)
                return
            except OSError as exc:
                if op & LOCK_NB:
                    raise BlockingIOError(11, "lock held by another process") from exc
                time.sleep(_WAIT_S)

    def fcntl(fd: int, cmd: int, arg: int = 0) -> int:
        raise OSError("fcntl is not available on Windows")


def uid() -> int:
    """A number that tells this user's files in a shared temp folder apart.  Windows has no user number; its temp folder is
    already the user's own."""
    return os.getuid() if hasattr(os, "getuid") else 0


def pid_alive(pid: int) -> bool:
    """Whether a process with this number exists.  ``os.kill(pid, 0)`` is the Mac's way; on Windows the same call would SEND
    the process a Ctrl+C, so the process is asked for by handle instead."""
    if pid <= 0:
        return False
    if not WINDOWS:
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except OSError:
            return False
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, int(pid))                 # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259      # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def detached() -> Dict[str, Any]:
    """Popen arguments that let a started process outlive the one that started it."""
    if WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def stay_awake(on: bool = True) -> bool:
    """Windows: keep the computer from idle sleep while this process works (the Mac wraps the command in ``caffeinate -i``
    instead).  Returns whether anything was asked."""
    if not WINDOWS:
        return False
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 if on else 0))      # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    return True


def awake_prefix(caffeinate: str = "/usr/bin/caffeinate") -> List[str]:
    """What to put before a command so the Mac stays awake while it runs; nothing where there is no ``caffeinate``."""
    return [caffeinate, "-i"] if not WINDOWS and os.path.exists(caffeinate) else []


def replace(src: Any, dst: Any, tries: int = 40) -> None:
    """``os.replace``.  On Windows a file another process has open for reading cannot be replaced at that instant
    (PermissionError); the reader is done within milliseconds, so the rename is tried again for up to two seconds."""
    for n in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not WINDOWS or n == tries - 1:
                raise
            time.sleep(0.05)


if WINDOWS:
    # Every other ``os.replace`` / ``Path.replace`` in the program (caches, scan files) gets the same short retry on Windows:
    # the server reads these files while the daily job rewrites them.  The Mac never reaches this line.
    _os_replace = os.replace

    def _replace_retry(src: Any, dst: Any, *a: Any, **k: Any) -> None:
        for n in range(40):
            try:
                return _os_replace(src, dst, *a, **k)
            except PermissionError:
                if n == 39:
                    raise
                time.sleep(0.05)

    def replace(src: Any, dst: Any, tries: int = 40) -> None:      # noqa: F811
        _replace_retry(src, dst)

    os.replace = _replace_retry
