"""Room left on the disk, the one cache that grows without limit, and cache entries left behind by older versions.

A full disk would stop every record at once, so the daily summary and the record screen warn before that.  ``prune_cache`` only lists
what it would remove unless ``apply`` is passed.  The daily job applies it once per session (the user's decision of 2026-11-09);
it removes cache files only, matched by name, never records or backups.
"""
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

GB = 1024 ** 3
WARN_FREE = 5 * GB
BAD_FREE = 2 * GB
CACHE = Path("data") / "qsf" / "cache"
SCANBARS = re.compile(r"^scanbars_(\d{4}-\d{2}-\d{2})_[0-9a-f]+_[0-9a-f]+\.json$")
KEEP_SESSIONS = 5
KR_CACHE = Path("data") / "kr" / "cache"
KR_BARS = re.compile(r"^(?:universe|history|evaluate)_\d{4}-\d{2}-\d{2}_(\d{4}-\d{2}-\d{2})_[0-9a-f]{12}\.csv\.gz$")
# what an atomic write leaves when the process is killed between writing and swapping: (folder, name pattern)
TEMPS = ((Path("data") / "qsf", re.compile(r"^(?:bars_KR\.json\.gz\.\d+\.tmp|krx_panel\.npz\.\d+\.tmp\.npz)$")), (KR_CACHE, re.compile(r"^.+\.csv\.gz\.\d+\.tmp$")))
TEMP_AGE_S = 86400
KEEP_KR_WINDOWS = 3                 # window ends kept: today's, and two earlier ones in case a day is looked at again
# cache entries no program code reads any more: (file pattern, why).  QSF-1.1.9 moved the extracted annual series to the keys
# annual3 and krfund3; the annual2 and krfund2 files are deliberately not listed here yet, so a return to 1.1.8 needs no download.
# QSF-1.2.1 moved the US series on to annual4; the annual3 files are not listed either, for the same reason.
SUPERSEDED = ((re.compile(r"^annual_\d{10}_[0-9a-z_]+\.json$"), "QSF-1.1.3부터 annual2로 바뀐 예전 연간 재무"),)


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


def superseded_report(base: Path) -> Dict[str, Any]:
    """Cache files of a key format the code no longer reads (``SUPERSEDED``); listing only."""
    root = Path(base) / CACHE
    groups = []
    for pattern, why in SUPERSEDED:
        files = sorted(f for f in root.iterdir() if f.is_file() and pattern.match(f.name)) if root.exists() else []
        groups.append({"what": why, "files": len(files), "mb": round(sum(f.stat().st_size for f in files) / 1024 ** 2, 1), "_paths": files})
    return {"groups": groups, "files": sum(g["files"] for g in groups), "mb": round(sum(g["mb"] for g in groups), 1)}


def kr_bars_report(base: Path, keep: int = KEEP_KR_WINDOWS) -> Dict[str, Any]:
    """The Korean model scan's bar files (``markets/kr/acquisition.py``).  A file's name carries the end of its window, the day after
    the session it was fetched for; a later day never reads it, and no run artifact points at it (runs keep their own snapshots)."""
    ends: Dict[str, List[Path]] = {}
    root = Path(base) / KR_CACHE
    if root.exists():
        for f in root.iterdir():
            m = KR_BARS.match(f.name)
            if m and f.is_file():
                ends.setdefault(m.group(1), []).append(f)
    order = sorted(ends)
    old = order[:-keep] if keep > 0 else order
    size = lambda names: sum(f.stat().st_size for e in names for f in ends[e])      # noqa: E731
    return {"windows": len(order), "files": sum(len(v) for v in ends.values()), "total_mb": round(size(order) / 1024 ** 2, 1), "keep": keep,
            "old_windows": old, "old_files": sum(len(ends[e]) for e in old), "old_mb": round(size(old) / 1024 ** 2, 1), "_paths": [f for e in old for f in ends[e]]}


def prune_kr_bars(base: Path, keep: int = KEEP_KR_WINDOWS, apply: bool = False) -> Dict[str, Any]:
    """Lists by default.  With ``apply`` removes only files whose names match the Korean bar cache pattern, older than the newest ``keep`` windows."""
    if keep < 1:
        raise ValueError("KEEP_AT_LEAST_ONE")
    rep = kr_bars_report(base, keep)
    paths = rep.pop("_paths")
    removed = 0
    if apply:
        for f in paths:
            f.unlink()
            removed += 1
    return {**rep, "applied": bool(apply), "removed": removed}


def prune_temps(base: Path, apply: bool = False, clock=time.time) -> Dict[str, Any]:
    """Temp files a killed write left behind (``TEMPS``).  A live writer's file is minutes old at most, so only ones older than
    ``TEMP_AGE_S`` are listed; ``apply`` removes them."""
    old = [f for folder, pattern in TEMPS for f in ((Path(base) / folder).iterdir() if (Path(base) / folder).exists() else [])
           if f.is_file() and pattern.match(f.name) and clock() - f.stat().st_mtime > TEMP_AGE_S]
    mb = round(sum(f.stat().st_size for f in old) / 1024 ** 2, 1)
    removed = 0
    if apply:
        for f in old:
            f.unlink()
            removed += 1
    return {"files": len(old), "mb": mb, "applied": bool(apply), "removed": removed}


def prune_cache(base: Path, keep: int = KEEP_SESSIONS, apply: bool = False) -> Dict[str, Any]:
    """Old scan sessions, old Korean bar windows, leftover temp files and superseded entries.  Lists by default; ``apply`` removes
    exactly the listed files."""
    scan = prune_scanbars(base, keep, apply)
    kr = prune_kr_bars(base, apply=apply)
    temps = prune_temps(base, apply=apply)
    old = superseded_report(base)
    removed = 0
    for g in old["groups"]:
        for f in g.pop("_paths"):
            if apply:
                f.unlink()
                removed += 1
    return {"scanbars": scan, "kr_bars": kr, "temps": temps, "superseded": {**old, "removed": removed}, "applied": bool(apply)}
