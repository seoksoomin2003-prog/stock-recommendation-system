"""A copy of the program to hand to someone else, from a button (SH-1, 2026-11-27, user decision).

The user's choices: the data keys stay in the copy (DART, KRX, ECOS, data.go.kr and the SEC contact line), the Telegram
token and chat id do not, and what the user typed about their own money does not (journal, paper trades, watchlist, alert
rules, screen settings).  The daily records stay, so the receiver continues the same record instead of starting at day 0.

What goes in: the source files git tracks (or, in a copy without git, every file outside the folders named in ``SKIP_DIRS``),
the key file with its Telegram lines removed, and the records the backup copies less the personal ones.  Nothing else under
``data/`` goes in: no cache, no log, no phone pairing, no automation state.  The key file's values are never read into a
message, a log or the result: the result names the keys that went out and the keys that were held back, never a value.

The zip holds the user's keys.  It is written for the owner only (0600) and the result says so.
"""
from __future__ import annotations

import fnmatch
import os
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from terminal import automation

VERSION = "SH-1"
TOP = "quant-stock-engine"
HELD_BACK_KEYS = ("TELEGRAM",)                       # a key whose name starts with one of these is left out of the copy's key file
PERSONAL = frozenset({"data/terminal/journal.jsonl", "data/terminal/paper_journal.jsonl", "data/terminal/settings.json",
                      "data/terminal/watchlist.json", "data/terminal/alerts.json", "data/terminal/alerts_log.jsonl"})
SKIP_DIRS = frozenset({".git", ".venv", "__pycache__", ".pytest_cache", "data", "research_data", "tracking", "cache", "cache.nosync",
                       "runs", "scratch", "node_modules", ".idea"})
CHOICES = ("data/qsf/stance.json", "data/qsf/*_switch.json")      # the owner's screen choices (stance, apply buttons): the receiver starts from the program's defaults
README = "먼저 읽기.txt"
README_TEXT = """퀀트 터미널 배포본

1. 이 폴더를 원하는 곳에 둡니다(예: 홈 폴더 아래 Developer). 바탕화면, 문서, 다운로드 폴더와 iCloud·OneDrive 폴더는 피합니다.
2. Python 3.14를 설치합니다(python.org). 다른 버전으로는 설치되지 않습니다.
3. 낮에(한국 시간 09~22시) 설치합니다. 설치하면 첫 수집이 곧 시작되는데, 밤과 새벽에는 그날 자료가 덜 나와 있습니다.
   Mac: ops 폴더의 '처음 설치.command'를 두 번 누릅니다.
   Windows: ops\\windows 폴더의 '1 처음 설치.bat', 그다음 '2 자동 실행 등록.bat'을 두 번 누릅니다.
4. 브라우저에서 http://127.0.0.1:8765 를 엽니다.

경고 창이 뜰 때
- Mac "확인되지 않은 개발자" 또는 "열 수 없습니다": 창을 닫고 시스템 설정 > 개인정보 보호 및 보안 > 아래쪽의
  "그래도 열기"를 누른 뒤 파일을 다시 두 번 누릅니다. (예전 macOS는 파일을 오른쪽 클릭 > 열기)
- Windows "Windows의 PC 보호": "추가 정보" > "실행"을 누릅니다.

알아 둘 것
- 자료를 받는 키(.env)는 들어 있습니다. 텔레그램 알림 키는 들어 있지 않습니다. 알림을 받으려면 자기 텔레그램 봇의
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 두 줄을 .env에 넣습니다.
- 텔레그램을 넣지 않으면 Mac은 컴퓨터 알림으로만 알려 줍니다. Windows는 알림이 전혀 없으므로 화면의 '오늘' 탭과
  연구실 탭의 '자동 실행'을 직접 열어 봐야 합니다.
- 컴퓨터가 켜져 있고 로그인돼 있고 잠들지 않아야 매일 수집이 돕니다.
- 계좌, 매매 일지, 모의 매매, 관심종목, 알림 규칙은 비어 있고 성향은 '기본'입니다. 화면에서 새로 입력합니다.
- 시세와 재무 자료는 처음 실행할 때 새로 받으므로 첫 수집은 오래 걸립니다(두 시간 안팎).
- 준 사람과 같은 키를 씁니다. 키마다 하루 호출 한도가 있어 함께 쓰면 한도를 나눠 씁니다.
- 자세한 사용법: reports/RUNBOOK.md
- 투자 권유가 아닌 연구용 프로그램입니다. 주문 기능은 없습니다.
"""


def _tracked(base: Path) -> Optional[List[str]]:
    """The files git tracks, or None in a copy that has no git (such a copy is one this button made)."""
    if not (base / ".git").exists():
        return None
    try:
        out = subprocess.run(["git", "-C", str(base), "-c", "core.quotepath=false", "ls-files", "-z"], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return [x for x in out.stdout.decode("utf-8", "replace").split("\0") if x]


def _walked(base: Path) -> List[str]:
    out: List[str] = []
    for folder, dirs, files in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            rel = (Path(folder) / name).relative_to(base).as_posix()
            if name == ".env" or name.startswith(".env.") and name != ".env.example" or name.endswith((".pyc", ".log", ".tmp", ".DS_Store")):
                continue
            out.append(rel)
    return out


def source_files(base: Path) -> List[str]:
    got = _tracked(base)
    return sorted(set(got if got is not None else _walked(base)))


def _left_out(rel: str) -> bool:
    return rel in PERSONAL or any(fnmatch.fnmatchcase(rel, c) for c in CHOICES)


def record_files(base: Path) -> List[str]:
    """What the backup copies, less the personal files: index lines, score shards, the separate records, one-time reports, news."""
    out = {p.relative_to(base).as_posix() for pattern in automation.BACKUP_GLOBS for p in base.glob(pattern) if p.is_file()}
    out |= {p.relative_to(base).as_posix() for p in (base / "data" / "qsf" / "ledger").glob("*.jsonl.gz")}
    out |= {p.relative_to(base).as_posix() for name in automation.FORWARD_STORES for p in (base / "research_data" / name).glob("*.json.gz")}
    out |= {p.relative_to(base).as_posix() for pattern in ("QSF_*.json", "IC1_*.json") for p in (base / "reports" / "qsf").glob(pattern)}
    out |= {p.relative_to(base).as_posix() for p in (base / "data" / "news").glob("*/*.jsonl.gz")}
    return sorted(x for x in out if not _left_out(x))


def _key_name(line: str) -> Optional[str]:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    if s.startswith("export "):
        s = s[len("export "):]
    return s.split("=", 1)[0].strip()


def key_file(text: str) -> Tuple[str, List[str], List[str]]:
    """(the key file for the copy, names kept, names held back).  A held-back line is dropped whole; no value is looked at."""
    lines, kept, held = [], [], []
    for raw in text.splitlines():
        name = _key_name(raw)
        if name and name.upper().startswith(HELD_BACK_KEYS):
            held.append(name)
            continue
        if any(k in raw.upper() for k in HELD_BACK_KEYS):       # a comment that names the key may be a switched-off line with its value
            continue
        if name:
            kept.append(name)
        lines.append(raw)
    return "\n".join(lines) + "\n", kept, held


def default_folder() -> Path:
    desk = Path.home() / "Desktop"
    return desk if desk.is_dir() else Path.home()


def _put(z: zipfile.ZipFile, arc: str, src: Optional[Path] = None, text: Optional[str] = None) -> None:
    info = zipfile.ZipInfo(f"{TOP}/{arc}", date_time=datetime.now().timetuple()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if arc.endswith((".command", ".sh")) else 0o600 if arc == ".env" else 0o644
    info.external_attr = (0o100000 | mode) << 16
    z.writestr(info, src.read_bytes() if src is not None else (text or "").encode("utf-8"))


def make(base: Path, folder: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Writes ``QuantEngine-배포본-<date>.zip`` and says what went in.  The program's own files are read and nothing is changed."""
    base, when = Path(base), now or datetime.now()
    folder = Path(folder or default_folder())
    target = folder / f"QuantEngine-배포본-{when:%Y-%m-%d}.zip"
    part = target.with_name(target.name + ".part")
    src, rec = source_files(base), record_files(base)
    env = base / ".env"
    kept: List[str] = []
    held: List[str] = []
    n = 0
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in sorted(set(src) | set(rec)):
                p = base / rel
                if _left_out(rel) or rel == ".env" or rel == README or "/evidence/" in rel or not p.is_file():      # audit evidence holds saved screen replies of the owner's own terminal
                    continue
                _put(z, rel, src=p)
                n += 1
            if env.is_file():
                text, kept, held = key_file(env.read_text(encoding="utf-8"))
                _put(z, ".env", text=text)
            _put(z, README, text=README_TEXT)
        os.chmod(part, 0o600)
        os.replace(part, target)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    shown = str(target).replace(str(Path.home()), "~")
    return {"status": "REAL", "version": VERSION, "path": shown, "size_mb": round(target.stat().st_size / 1e6, 1), "files": n, "records": len(rec),
            "keys_kept": kept, "keys_held_back": held, "key_file": env.is_file(), "personal_left_out": sorted(PERSONAL) + list(CHOICES),
            "text": _text(shown, n, len(rec), kept, held, env.is_file()),
            "note": "이 zip에는 자료를 받는 키가 들어 있습니다. 믿는 사람에게만 주고, 공개된 곳에 올리지 마세요. 값은 이 화면에 보이지 않습니다."}


def _text(shown: str, n: int, rec: int, kept: Iterable[str], held: Iterable[str], has_env: bool) -> str:
    kept, held = list(kept), list(held)
    keys = "키 파일(.env)이 없어 키 없이 만들었습니다." if not has_env else \
        f"키 {len(kept)}개를 넣고" + (f" {', '.join(held)}는 뺐습니다." if held else " 뺄 텔레그램 키는 없었습니다.")
    return f"{shown} 을 만들었습니다(파일 {n}개, 그중 기록 {rec}개). {keys} 계좌·매매 일지·모의 매매·관심종목·알림 규칙은 넣지 않았습니다."
