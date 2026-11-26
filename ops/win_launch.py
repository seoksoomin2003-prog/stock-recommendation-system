"""Windows: run ``app.py`` with its arguments without a console window, output appended to a log file.

The Task Scheduler entries made by ``app.py automation install`` and ``app.py terminal-agent install`` start
``pythonw.exe -X utf8 ops\\win_launch.py <log file> <app.py arguments...>``.  ``pythonw`` has no console and no output stream,
so this opens the log (moved aside once past 1 MB, as the Mac's start-up script does) and hands it to the program.
"""
import os
import runpy
import sys
from pathlib import Path

LOG_MAX_BYTES = 1_000_000


def main() -> None:
    base = Path(__file__).resolve().parents[1]
    log, args = Path(sys.argv[1]), sys.argv[2:]
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        if log.exists() and log.stat().st_size > LOG_MAX_BYTES:
            os.replace(log, log.with_name(log.name + ".1"))
    except OSError:
        pass
    out = open(log, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = out
    os.chdir(base)
    sys.path.insert(0, str(base))
    sys.argv = [str(base / "app.py"), *args]
    runpy.run_path(str(base / "app.py"), run_name="__main__")


if __name__ == "__main__":
    main()
