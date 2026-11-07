"""Room left on the disk, and the one cache that grows without limit.

A full disk would stop every record at once, so the daily summary and the record screen warn before that.  Removing files needs the user's word:
``prune_scanbars`` only lists what it would remove unless ``apply`` is passed, and nothing calls it on a schedule.
"""
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

GB = 1024 ** 3
WARN_FREE = 5 * GB
BAD_FREE = 2 * GB
CACHE = Path("data") / "qsf" / "cache"
SCANBARS = re.compile(r"^scanbars_(\d{4}-\d{2}-\d{2})_[0-9a-f]+_[0-9a-f]+\.json$")
KEEP_SESSIONS = 5


def disk(base: Path, usage=shutil.disk_usage) -> Dict[str, Any]:
    u = usage(Path(base))
    level = "bad" if u.free < BAD_FREE else "warn" if u.free < WARN_FREE else "ok"
    return {"free_gb": round(u.free / GB, 1), "total_gb": round(u.total / GB, 1), "level": level}


def low_disk_text(base: Path, usage=shutil.disk_usage) -> Optional[str]:
    """The sentence to show when room is short, or nothing."""
    d = disk(base, usage)
    if d["level"] == "ok":
        return None
    return f"디스크 여유가 {d['free_gb']}GB입니다. " + ("곧 기록을 쓰지 못할 수 있습니다." if d["level"] == "bad" else "공간을 확보하세요.")


def scanbars_report(base: Path, keep: int = KEEP_SESSIONS) -> Dict[str, Any]:
    """Per-session scan price files.  An old session's files are read again only by a rescan of that session, which the scan does not do."""
    sessions: Dict[str, List[Path]] = {}
    root = Path(base) / CACHE
    if root.exists():
        for f in root.iterdir():
            m = SCANBARS.match(f.name)
            if m and f.is_file():
                sessions.setdefault(m.group(1), []).append(f)
    order = sorted(sessions)
    old = order[:-keep] if keep > 0 else order
    size = lambda names: sum(f.stat().st_size for s in names for f in sessions[s])      # noqa: E731
    return {"sessions": len(order), "files": sum(len(v) for v in sessions.values()), "total_mb": round(size(order) / 1024 ** 2, 1), "keep": keep,
            "kept": order[-keep:] if keep > 0 else [], "old_sessions": old, "old_files": sum(len(sessions[s]) for s in old), "old_mb": round(size(old) / 1024 ** 2, 1), "_paths": [f for s in old for f in sessions[s]]}


def prune_scanbars(base: Path, keep: int = KEEP_SESSIONS, apply: bool = False) -> Dict[str, Any]:
    """Lists by default.  With ``apply`` removes only files whose names match the scan cache pattern, older than the newest ``keep`` sessions."""
    if keep < 1:
        raise ValueError("KEEP_AT_LEAST_ONE")
    rep = scanbars_report(base, keep)
    paths = rep.pop("_paths")
    removed = 0
    if apply:
        for f in paths:
            f.unlink()
            removed += 1
    return {**rep, "applied": bool(apply), "removed": removed}
