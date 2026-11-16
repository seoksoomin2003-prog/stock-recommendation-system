"""Files that must survive a power cut: written beside their target, pushed to the disk, then renamed over it.

A rename alone is atomic but not durable.  After a forced power-off the name can point at a file whose bytes never left the
memory cache: an empty or cut file under the final name, which a write-once store then trusts for good.  On macOS ``os.fsync``
only hands the bytes to the drive; ``F_FULLFSYNC`` asks the drive to put them on the medium.  It costs a few milliseconds, so it
is for records, verdicts and state, not for caches that can be fetched again.
"""
import fcntl
import os
from pathlib import Path
from typing import Union

PathLike = Union[str, Path]


def sync(path: PathLike) -> None:
    """The finished file's bytes are on the disk when this returns."""
    fd = os.open(path, os.O_RDONLY)
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
    os.replace(tmp, target)


def write_text(target: PathLike, text: str) -> None:
    """The text under ``target``, whole or not at all.  An existing file is replaced only by a complete one."""
    target = Path(target)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    replace(tmp, target)
