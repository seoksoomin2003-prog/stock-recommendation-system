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
# a key whose name starts with one of these is left out of the copy's key file.  2026-11-29 (user decision after the hand-over
# audit): the owner's capital, the SEC contact (an e-mail address: each computer gives its own at install, and a receiver who
# makes a copy does not pass theirs on) and the two lines that hold a folder path of the owner's computer.
HELD_BACK_KEYS = ("TELEGRAM", "QPP_CAPITAL", "SEC_USER_AGENT", "QPP_BACKUP_DIR", "HORIZON_BOT_DIR")
# reports/ holds hundreds of audit texts written about the owner's own terminal (some name a holding and its share of the
# account).  A copy takes the guide, the registered rules a screen points at, and the one-time result files; nothing else.
REPORT_WORDS = ("PROTOCOL", "RULES", "RUNBOOK", "FACTOR_INVENTORY", "FORMULA_FREEZE", "QSF_1_6_0")      # the last: the formula in force
OWNER_ONLY = ("tracking/", "docs/", ".agents/", ".vscode/")                 # the baseline scan record carries the capital of each run; docs/ are set-up notes of the owner's computer
PERSONAL = frozenset({"data/terminal/journal.jsonl", "data/terminal/paper_journal.jsonl", "data/terminal/settings.json",
                      "data/terminal/watchlist.json", "data/terminal/alerts.json", "data/terminal/alerts_log.jsonl"})
SKIP_DIRS = frozenset({".git", ".venv", "__pycache__", ".pytest_cache", "data", "research_data", "tracking", "cache", "cache.nosync",
                       "runs", "scratch", "node_modules", ".idea", ".tools"})
CHOICES = ("data/qsf/stance.json", "data/qsf/*_switch.json")      # the owner's screen choices (stance, apply buttons): the receiver starts from the program's defaults
FOLDER = "QuantEngine-배포본"
README = "먼저 읽기.txt"
README_TEXT = """퀀트 터미널 배포본

파이썬이나 다른 프로그램을 미리 설치할 필요가 없습니다. 인터넷에 연결된 컴퓨터에서 아래 두 가지만 합니다.

1. 받은 zip의 압축을 풉니다(Mac: 두 번 누르기 / Windows: 오른쪽 클릭 > 압축 풀기. 풀지 않고 zip 안에서 누르면 안 됩니다).
2. 풀린 폴더에서 Mac은 'Mac 설치.command', Windows는 'Windows 설치.bat'을 두 번 누릅니다.

설치 창이 이메일 주소를 한 번 묻습니다(미국 재무 자료를 주는 SEC가 받는 사람의 연락처를 요구합니다). 건너뛸 수 있지만,
건너뛰면 미국 종목의 점수는 매일 기록되지 않습니다. 나중에 QuantEngine 폴더 ops(Windows는 ops\\windows)의 '연락처 입력' 파일로 넣을 수 있습니다.
몇 분 뒤 브라우저에 화면이 스스로 열립니다. 주소는 http://127.0.0.1:8765 입니다.
프로그램은 홈 폴더의 QuantEngine 폴더에 설치됩니다. 설치가 끝나면 받은 zip과 풀린 폴더는 지워도 됩니다(키가 들어 있으니
지우는 편이 좋습니다). 낮에(한국 시간 09~22시) 설치합니다: 설치하면 첫 수집이 곧 시작되는데, 밤과 새벽에는 그날 자료가
덜 나와 있습니다. 밤에 누르면 화면만 열리고 매일 수집은 등록되지 않으니, 낮에 같은 파일을 한 번 더 누릅니다.

경고 창이 뜰 때
- Mac "확인되지 않은 개발자" 또는 "열 수 없습니다": 창을 닫고 시스템 설정 > 개인정보 보호 및 보안 > 아래쪽의
  "그래도 열기"를 누른 뒤 파일을 다시 두 번 누릅니다. (예전 macOS는 파일을 오른쪽 클릭 > 열기)
- Mac "터미널이 다운로드 폴더의 파일에 접근하려고 합니다": "허용"을 누릅니다.
- Windows "Windows의 PC 보호": "추가 정보" > "실행"을 누릅니다.

알아 둘 것
- 설치할 때 설치 도구(uv)와 Python 3.14, 패키지를 인터넷에서 받아 QuantEngine 폴더 안에 둡니다. 그 밖에 생기는 것은
  자동 실행 등록, 홈 폴더의 QuantEngineBackups(기록 백업), 설치 도구의 내려받기 보관 폴더입니다. 이미 있는 파이썬과
  섞이지 않고, 다른 버전으로는 설치되지 않습니다.
- 자료를 받는 키(.env)는 들어 있습니다. 텔레그램 알림 키, SEC 연락처(준 사람의 이메일), 준 사람의 자본금은 들어 있지
  않습니다. 자본금은 화면의 모델 탭에서 넣습니다(넣기 전에는 기준 모델 스캔만 건너뜁니다). 알림을 받으려면 자기 텔레그램 봇의
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 두 줄을 QuantEngine 폴더의 .env에 넣습니다.
- 텔레그램을 넣지 않으면 Mac은 컴퓨터 알림으로만 알려 줍니다. Windows는 알림이 전혀 없으므로 화면의 '오늘' 탭과
  연구실 탭의 '자동 실행'을 직접 열어 봐야 합니다.
- 컴퓨터가 켜져 있고 로그인돼 있고 전원에 연결돼 있고 잠들지 않아야 매일 수집이 돕니다.
- 계좌, 매매 일지, 모의 매매, 관심종목, 알림 규칙은 비어 있고 성향은 '기본'입니다. 화면에서 새로 입력합니다.
- 시세와 재무 자료는 처음 실행할 때 새로 받으므로 첫 수집은 오래 걸립니다(두 시간 안팎).
- 준 사람과 같은 키를 씁니다. 키마다 하루 호출 한도가 있어 함께 쓰면 한도를 나눠 씁니다.
- 화면이 안 열릴 때: QuantEngine 폴더의 ops('서버 다시 시작') 파일을 두 번 누릅니다. Windows는 ops\\windows 폴더입니다.
  Mac에서는 이 파일들도 처음 누를 때 경고 창이 한 번씩 뜹니다(위 '그래도 열기').
- 새 판을 받았을 때: 새 zip을 풀고 같은 설치 파일을 누르면 프로그램 파일만 바꿀지 묻습니다. 기록과 키는 그대로 둡니다.
- 지우거나 폴더를 옮길 때: 먼저 ops의 '자동 실행 해제' 파일을 누릅니다. 폴더만 지우면 자동 실행이 남아 계속 실패합니다.
- 자세한 사용법: QuantEngine 폴더의 reports/RUNBOOK.md
- 투자 권유가 아닌 연구용 프로그램입니다. 주문 기능은 없습니다.
"""
INSTALL_FOLDER = "QuantEngine"                       # under the receiver's home folder: outside the Desktop, Documents and Downloads a cloud may upload or macOS may fence off
MAC_START = "Mac 설치.command"
WIN_START = "Windows 설치.bat"
MAC_START_TEXT = """#!/bin/zsh
# 받은 폴더에서 한 번 누릅니다. 프로그램을 홈 폴더의 QuantEngine 으로 복사한 뒤 그 안의 설치 파일을 실행합니다.
# 이미 설치돼 있으면 프로그램 파일만 새 판으로 바꿀지 묻습니다(기록과 키는 그대로 둡니다).
SRC="$(cd "$(dirname "$0")" && pwd)/quant-stock-engine"
DST="${QE_INSTALL_DIR:-$HOME/QuantEngine}"
if [ ! -f "$SRC/app.py" ]; then echo "옆에 quant-stock-engine 폴더가 없습니다. zip을 통째로 푼 뒤 풀린 폴더에서 다시 누르세요."; exit 1; fi
if [ -d "$DST" ] && [ ! -f "$DST/app.py" ]; then
  rmdir "$DST" 2>/dev/null || { echo "$DST 폴더가 이미 있는데 이 프로그램이 아닙니다. 그 폴더의 이름을 바꾸거나 지운 뒤 다시 누르세요."; exit 1; }
fi
if [ -f "$DST/app.py" ]; then
  if [ -x "$DST/.venv/bin/python" ]; then
    (cd "$DST" && .venv/bin/python "$SRC/ops/update_from.py" "$SRC" "$DST")
  else
    echo "설치 폴더가 이미 있습니다: $DST"
    echo "그 폴더의 기록을 지키기 위해 새로 받은 파일로 덮어쓰지 않고, 있는 폴더에서 설치를 이어 갑니다."
  fi
else
  echo "프로그램을 $DST 로 복사합니다."
  rm -rf "$DST.part"
  mkdir -p "$(dirname "$DST")" && ditto "$SRC" "$DST.part" && mv "$DST.part" "$DST" || { echo "복사하지 못했습니다. 디스크 여유 공간을 확인하세요."; exit 1; }
fi
exec /bin/zsh "$DST/ops/처음 설치.command"
"""
WIN_START_TEXT = """@echo off
chcp 65001 >nul
rem 받은 폴더에서 한 번 누릅니다. 프로그램을 사용자 폴더의 QuantEngine 으로 복사한 뒤 그 안의 설치 파일을 실행합니다.
rem 이미 설치돼 있으면 프로그램 파일만 새 판으로 바꿀지 묻습니다. 기록과 키는 그대로 둡니다.
set "SRC=%~dp0quant-stock-engine"
if defined QE_INSTALL_DIR (set "DST=%QE_INSTALL_DIR%") else (set "DST=%USERPROFILE%\\QuantEngine")
if not exist "%SRC%\\app.py" goto nofolder
if exist "%DST%\\app.py" goto have
if exist "%DST%\\" rmdir "%DST%" 2>nul
if exist "%DST%\\" goto notours
echo 프로그램을 %DST% 로 복사합니다.
if exist "%DST%.part\\" rmdir /s /q "%DST%.part"
robocopy "%SRC%" "%DST%.part" /E /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto nocopy
move "%DST%.part" "%DST%" >nul
if not exist "%DST%\\app.py" goto nocopy
goto run
:have
if not exist "%DST%\\.venv\\Scripts\\python.exe" goto havesay
pushd "%DST%"
.venv\\Scripts\\python.exe -X utf8 "%SRC%\\ops\\update_from.py" "%SRC%" "%DST%"
popd
goto run
:havesay
echo 설치 폴더가 이미 있습니다: %DST%
echo 그 폴더의 기록을 지키기 위해 새로 받은 파일로 덮어쓰지 않고, 있는 폴더에서 설치를 이어 갑니다.
:run
call "%DST%\\ops\\windows\\1 처음 설치.bat"
exit /b %errorlevel%
:nofolder
echo 옆에 quant-stock-engine 폴더가 없습니다. zip 파일을 오른쪽 클릭해 압축을 모두 푼 뒤, 풀린 폴더에서 다시 누르세요.
pause
exit /b 1
:notours
echo %DST% 폴더가 이미 있는데 이 프로그램이 아닙니다. 그 폴더의 이름을 바꾸거나 지운 뒤 다시 누르세요.
pause
exit /b 1
:nocopy
echo 복사하지 못했습니다. 디스크 여유 공간을 확인하세요.
pause
exit /b 1
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


def _report_stays_home(rel: str) -> bool:
    if not rel.startswith("reports/"):
        return False
    rest = rel[len("reports/"):]
    if rest.startswith("qsf/"):
        return not (rest.endswith(".json") and "/" not in rest[len("qsf/"):])
    return "/" in rest or not (rest.endswith(".md") and any(w in rest for w in REPORT_WORDS))


def _left_out(rel: str) -> bool:
    return rel in PERSONAL or any(fnmatch.fnmatchcase(rel, c) for c in CHOICES) or rel.startswith(OWNER_ONLY) or _report_stays_home(rel)


def _names_this_computer(data: bytes) -> bool:
    """A text that spells out the owner's home folder (a path pasted into a note or a test) stays home too."""
    home = str(Path.home())
    return len(home) > 3 and home.encode("utf-8") in data


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
        if name and (name.upper().startswith(HELD_BACK_KEYS) or name.upper().endswith(("_DIR", "_ROOT"))):       # a folder of the owner's computer
            held.append(name)
            continue
        if any(k in raw.upper() for k in HELD_BACK_KEYS):       # a comment that names the key may be a switched-off line with its value
            continue
        if name:
            kept.append(name)
        lines.append(raw)
    return "\n".join(lines) + "\n", kept, held


def default_folder() -> Path:
    """A folder of its own in the home folder, never the Desktop: a Mac with "Desktop & Documents" in iCloud Drive (or a Windows
    PC with OneDrive) uploads whatever lands there, and this file holds the keys (found 2026-11-27: the copy had been uploaded)."""
    return Path.home() / FOLDER


def _put(z: zipfile.ZipFile, arc: str, src: Optional[Path] = None, text: Optional[str] = None, beside: bool = False) -> None:
    """``beside``: next to the program's folder, where the receiver looks first (the two start files and the first page)."""
    info = zipfile.ZipInfo(arc if beside else f"{TOP}/{arc}", date_time=datetime.now().timetuple()[:6])
    info.compress_type = zipfile.ZIP_DEFLATED
    mode = 0o755 if arc.endswith((".command", ".sh")) else 0o600 if arc == ".env" else 0o644
    info.external_attr = (0o100000 | mode) << 16
    z.writestr(info, src.read_bytes() if src is not None else (text or "").encode("utf-8"))


def _start_files(z: zipfile.ZipFile) -> None:
    """One file to press per system, beside the folder: it copies the program into the home folder and runs the real installer."""
    _put(z, README, text=README_TEXT, beside=True)
    _put(z, MAC_START, text=MAC_START_TEXT, beside=True)
    _put(z, WIN_START, text=WIN_START_TEXT.replace("\n", "\r\n"), beside=True)


def make(base: Path, folder: Optional[Path] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Writes ``QuantEngine-배포본-<date>.zip`` and says what went in.  The program's own files are read and nothing is changed."""
    base, when = Path(base), now or datetime.now()
    folder = Path(folder or default_folder())
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"QuantEngine-배포본-{when:%Y-%m-%d}.zip"
    part = target.with_name(target.name + ".part")
    src, rec = source_files(base), record_files(base)
    env = base / ".env"
    kept: List[str] = []
    held: List[str] = []
    named: List[str] = []
    n = 0
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in sorted(set(src) | set(rec)):
                p = base / rel
                if _left_out(rel) or rel == ".env" or rel == README or "/evidence/" in rel or not p.is_file():      # audit evidence holds saved screen replies of the owner's own terminal
                    continue
                if not rel.endswith(".gz") and _names_this_computer(p.read_bytes()):
                    named.append(rel)
                    continue
                _put(z, rel, src=p)
                n += 1
            if env.is_file():
                text, kept, held = key_file(env.read_text(encoding="utf-8"))
                _put(z, ".env", text=text)
            _put(z, README, text=README_TEXT)
            _start_files(z)
        os.chmod(part, 0o600)
        os.replace(part, target)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    shown = str(target).replace(str(Path.home()), "~")
    return {"status": "REAL", "version": VERSION, "path": shown, "size_mb": round(target.stat().st_size / 1e6, 1), "files": n, "records": len(rec),
            "keys_kept": kept, "keys_held_back": held, "key_file": env.is_file(), "files_naming_this_computer": named, "personal_left_out": sorted(PERSONAL) + list(CHOICES),
            "text": _text(shown, n, len(rec), kept, held, env.is_file()),
            "note": "이 zip에는 자료를 받는 키가 들어 있습니다. 믿는 사람에게만 주고, 공개된 곳에 올리지 마세요. iCloud·OneDrive처럼 저절로 올라가는 폴더(바탕화면, 문서)에도 두지 마세요. 값은 이 화면에 보이지 않습니다."}


def _text(shown: str, n: int, rec: int, kept: Iterable[str], held: Iterable[str], has_env: bool) -> str:
    kept, held = list(kept), list(held)
    keys = "키 파일(.env)이 없어 키 없이 만들었습니다." if not has_env else \
        f"키 {len(kept)}개를 넣고" + (f" {', '.join(held)}는 뺐습니다." if held else " 뺄 텔레그램 키는 없었습니다.")
    return f"{shown} 을 만들었습니다(파일 {n}개, 그중 기록 {rec}개). {keys} 계좌·매매 일지·모의 매매·관심종목·알림 규칙, 자본금, 기준 모델 스캔 기록, 점검 보고서는 넣지 않았습니다."
