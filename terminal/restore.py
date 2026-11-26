"""Putting a damaged score record back from the backup, and looking at the backups, from a button (RS-1, 2026-11-26).

The institutional assessment found that one damaged shard of the score ledger stops every later record (``Ledger.append``
refuses a broken ledger) and that the only way back was a file swapped by hand.  A shard is written once and never changed,
and the index keeps its SHA-256, so a copy in a backup is the right file exactly when its hash equals the index's.  This puts
such a copy back and nothing else: the damaged file is moved aside (never deleted), no index line is written or changed, and a
shard whose backup copy does not match is left alone and named.
"""
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from terminal import automation
from terminal.qsf.ledger import Ledger

ASIDE = "damaged"          # data/qsf/ledger/damaged/<file>.<time>: what was on disk when the repair ran
DATALESS = 0x40000000      # macOS SF_DATALESS: the file's name and size are here, its content only in iCloud until it is read


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def roots(base: Path) -> List[Path]:
    """The backup folders there are: the first, then the second when one is set."""
    second = automation.second_backup_root(base)
    return [r for r in (automation.backup_root(), second) if r is not None and Path(r).exists()]


def repair_ledger(base: Path, now: Optional[datetime] = None, backups: Optional[List[Path]] = None) -> Dict[str, Any]:
    """{"status": "NOTHING_TO_DO" | "REPAIRED" | "PARTLY" | "NO_GOOD_COPY" | "INDEX_BROKEN", "repaired": [...], "left": [...]}."""
    led = Ledger(Path(base))
    idx = led.read_index()
    if idx["status"] != "OK":
        return {"status": "INDEX_BROKEN", "repaired": [], "left": [], "text": "기록의 목록 파일(index.jsonl) 자체가 깨져 있습니다. 이 버튼으로는 되돌리지 못합니다. reports/RUNBOOK.md 5절을 보세요."}
    want = {r["file"]: r["sha256"] for r in idx["rows"] if r.get("type") != "VOID"}
    bad = led.verify().get("bad_files") or []
    if not bad:
        return {"status": "NOTHING_TO_DO", "repaired": [], "left": [], "text": "깨진 기록 묶음이 없습니다."}
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    repaired, left = [], []
    for name in bad:
        good = next((p for p in (Path(r) / "qsf_ledger" / name for r in (backups if backups is not None else roots(base))) if p.exists() and not (getattr(p.lstat(), "st_flags", 0) & DATALESS) and _sha(p) == want[name]), None)      # a copy held in iCloud only is not read here: download it first
        if good is None:
            left.append(name)
            continue
        here = led.dir / name
        if here.exists():
            aside = led.dir / ASIDE
            aside.mkdir(parents=True, exist_ok=True)
            here.rename(aside / f"{name}.{stamp}")
        tmp = led.dir / f".{name}.restoring"
        shutil.copy2(good, tmp)
        if _sha(tmp) != want[name]:
            tmp.unlink()
            left.append(name)
            continue
        tmp.rename(here)
        repaired.append(name)
    status = "REPAIRED" if repaired and not left else "PARTLY" if repaired else "NO_GOOD_COPY"
    text = (f"기록 묶음 {len(repaired)}개를 백업에서 되돌렸습니다. 깨졌던 파일은 지우지 않고 '{ASIDE}' 폴더로 옮겼습니다." if repaired else "") + \
           (f" {len(left)}개는 백업에 맞는 사본이 없어 그대로 두었습니다: {', '.join(left[:5])}." if left else "")
    return {"status": status, "repaired": repaired, "left": left, "text": text.strip(), "integrity": led.verify()["status"]}


def in_cloud_only(root: Path) -> int:
    """How many files of a backup folder iCloud keeps as download-on-read entries.  macOS does this by itself when the disk is
    short ("Mac 저장 공간 최적화").  Reading one downloads it, which can take minutes and fails inside the background server
    (first seen 2026-11-26: 166 of 421 files a few hours after the first copy).  The copy is whole in iCloud; it is the local
    read that is not possible, so the check says that instead of hanging."""
    n = 0
    for p in Path(root).rglob("*"):
        try:
            n += bool(getattr(p.lstat(), "st_flags", 0) & DATALESS)
        except OSError:
            continue
    return n


def check(base: Path) -> Dict[str, Any]:
    """Each backup folder restored into a throw-away folder and verified (``automation.check_backup``).  Reads only."""
    out = []
    for r in roots(base):
        shown = str(r).replace(str(Path.home()), "~")
        away = in_cloud_only(r)
        if away:
            out.append({"path": shown, "status": "IN_CLOUD", "latest": automation.backup_status(r)["latest"], "checked": 0, "failed": [], "in_cloud_only": away})
            continue
        try:
            res = automation.check_backup(r)
        except Exception as exc:                    # one unreadable folder never hides the other's result
            out.append({"path": shown, "status": "UNREADABLE", "latest": None, "checked": 0, "failed": [type(exc).__name__]})
            continue
        fails = sorted(k for k, v in (res.get("checks") or {}).items() if (v.get("status") if isinstance(v, dict) else v) != "OK")
        out.append({"path": shown, "status": res.get("status"), "latest": res.get("latest"), "checked": len(res.get("checks") or {}), "failed": fails})
    return {"status": "REAL", "backups": out, "second": automation.second_backup_status(base),
            "note": "백업을 임시 폴더에 풀어 각 기록의 검증을 돌린 결과입니다. 백업과 기록은 바꾸지 않습니다."}


def set_second(base: Path, on: bool) -> Dict[str, Any]:
    return automation.set_second_backup(base, bool(on))
