"""Files that must survive a power cut: written beside their target, pushed to the disk, then renamed over it.

A rename alone is atomic but not durable.  After a forced power-off the name can point at a file whose bytes never left the
memory cache: an empty or cut file under the final name, which a write-once store then trusts for good.  On macOS ``os.fsync``
only hands the bytes to the drive; ``F_FULLFSYNC`` asks the drive to put them on the medium.  It costs a few milliseconds, so it
is for records, verdicts and state, not for caches that can be fetched again.
"""
from utils import fcntl_port as fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Union

PathLike = Union[str, Path]


def sync(path: PathLike) -> None:
    """The finished file's bytes are on the disk when this returns."""
    fd = os.open(path, os.O_RDWR if fcntl.WINDOWS else os.O_RDONLY)      # Windows flushes only a handle opened for writing
    try:
        try:
            fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
        except (AttributeError, OSError):       # not macOS, or a volume that does not take it
            os.fsync(fd)
    finally:
        os.close(fd)


def replace(tmp: PathLike, target: PathLike) -> None:
    """``tmp`` becomes ``target``; a reader sees the old file or the whole new one, also after a power cut."""
    sync(tmp)
    fcntl.replace(tmp, target)


def write_text(target: PathLike, text: str) -> None:
    """The text under ``target``, whole or not at all.  An existing file is replaced only by a complete one."""
    target = Path(target)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    replace(tmp, target)


# ------------------------------------------------------------------------------------------------- line records
class TornFile(RuntimeError):
    """A line record ends in a cut line.  Appending after it would weld two lines into one for good, so nothing is appended
    until a person has looked (the cut line is never repaired by the program)."""


def _lines(path: Path) -> List[str]:
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        raise TornFile(f"LINES_TORN: {path.parent.name}/{path.name} ends in a cut line; it must be repaired before any new record")
    return [x for x in text.splitlines() if x.strip()]


def mend_tail(path: PathLike, stamp: str, aside: str = "damaged") -> Optional[str]:
    """What a person's repair button does to a line record that ends without a line break (a write cut short: the disk ran
    out, the power went).  Never called by a writer: a writer refuses such a file (``TornFile``).

    "CLOSED": the last line is a whole record that only lacked its line break; the break is added.
    "CUT": the last line is a fragment; it is moved to ``<folder>/<aside>/<name>.tail.<stamp>`` and the file ends at the line before.
    "UNREADABLE": an earlier line cannot be read either; nothing is changed.   None: the file ends whole, nothing to do."""
    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data or data.endswith(b"\n"):
        return None
    cut = data.rfind(b"\n") + 1
    head, tail = data[:cut], data[cut:]
    try:
        for line in head.decode("utf-8").splitlines():
            if line.strip():
                json.loads(line)
    except (UnicodeDecodeError, ValueError):
        return "UNREADABLE"
    try:
        whole = isinstance(json.loads(tail.decode("utf-8")), dict)
    except (UnicodeDecodeError, ValueError):
        whole = False
    tmp = path.with_name(path.name + ".mend")
    if whole:
        tmp.write_bytes(data + b"\n")
    else:
        folder = path.parent / aside
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{path.name}.tail.{stamp}").write_bytes(tail)
        tmp.write_bytes(head)
    replace(tmp, path)
    return "CLOSED" if whole else "CUT"


def _link(prev: str, row: Dict[str, Any]) -> str:
    body = json.dumps({k: v for k, v in row.items() if k != "chain"}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256((prev + hashlib.sha256(body.encode("utf-8")).hexdigest()).encode()).hexdigest()


def append_chained(folder: PathLike, name: str, rows: Iterable[Dict[str, Any]], skip: Optional[Callable[[], bool]] = None) -> int:
    """Append ``rows`` to ``folder/name`` (a ``*.jsonl`` file of a store whose files sort by time) the way the forward records
    are written: one writer at a time, never after a cut line, every line chained to the one before it (``chain``: the hash of
    the previous line's chain and this line), and on the disk before this returns.  ``skip`` is asked under the lock: True
    means another writer has already written it.  Returns the number of lines written."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / "write.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        files = sorted(folder.glob("*.jsonl"))
        if files and name < files[-1].name:
            raise ValueError(f"{folder.name}/{name} is older than the store's newest file {files[-1].name}: lines are appended in order only")
        prev = ""
        for p in files:                               # every file must end whole, not only the one written to
            lines = _lines(p)
            if lines:
                try:
                    prev = json.loads(lines[-1]).get("chain") or ""
                except ValueError as exc:
                    raise TornFile(f"LINES_TORN: {folder.name}/{p.name} ends in a line that cannot be read") from exc
        if skip is not None and skip():
            return 0
        out = []
        for row in rows:
            prev = _link(prev, row)
            out.append(json.dumps({**row, "chain": prev}, ensure_ascii=False, sort_keys=True) + "\n")
        if not out:
            return 0
        with open(folder / name, "a", encoding="utf-8") as fh:
            fh.write("".join(out))
            fh.flush()
            os.fsync(fh.fileno())
        sync(folder / name)
        return len(out)


def verify_chained(folder: PathLike) -> Dict[str, Any]:
    """{"status": OK | TORN | BROKEN | EMPTY, "lines": n}: whether every line of the store is whole and follows the one before."""
    folder, prev, n = Path(folder), "", 0
    try:
        for p in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
            for line in _lines(p):
                row = json.loads(line)
                prev = _link(prev, row)
                n += 1
                if row.get("chain") != prev:
                    return {"status": "BROKEN", "lines": n, "file": p.name}
    except (TornFile, ValueError):
        return {"status": "TORN", "lines": n}
    return {"status": "OK" if n else "EMPTY", "lines": n}
