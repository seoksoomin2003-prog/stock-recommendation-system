"""Puts a newer copy's program files into an installed folder and leaves everything the computer made itself (2026-11-29).

Run by the start file of a newer zip when the install folder already exists:  python update_from.py <new copy> <installed>.
Program files are copied over.  Never touched: the key file, data/, research_data/, tracking/, the one-time result files in
reports/qsf/, and the Python of the folder (.venv, .tools).  So the receiver's records, entries, contact and choices stay,
and the records that came inside the new zip (the giver's days) are not taken.  Nothing is deleted.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

KEEP = (".env", "data/", "research_data/", "tracking/", "reports/qsf/", ".venv/", ".tools/")
ASK = ("\n이 컴퓨터에는 프로그램이 이미 설치돼 있습니다: {dst}\n"
       "새로 받은 판으로 프로그램 파일만 바꿀 수 있습니다. 이 컴퓨터의 기록, 계좌·일지, 키와 연락처는 그대로 둡니다.\n"
       "바꾸려면 y 를 입력하고 Enter, 그대로 두려면 그냥 Enter를 누르세요.\n")


def kept(rel: str) -> bool:
    if rel.startswith("data/") and rel.endswith(".py"):
        return False                                    # data/ is also a package of the program (data/loader.py)
    return rel == ".env" or any(rel.startswith(k) for k in KEEP if k.endswith("/"))


def files(src: Path):
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src).as_posix()
        if p.is_file() and not kept(rel) and "__pycache__" not in rel:
            yield rel


def running(dst: Path):
    """The daily job's own word on whether it is running (None when it is not, or when it cannot be asked)."""
    sys.path.insert(0, str(dst))
    try:
        from terminal import automation
        return automation.status(dst).get("running")
    except Exception:
        return None


def stop_server() -> None:
    """Windows keeps the files of a running program open: the server task is ended before its files and packages are replaced
    (the installer that runs next starts it again).  A Mac replaces files under a running program, and its installer restarts it."""
    if sys.platform != "win32":
        return
    import subprocess
    import time
    try:
        subprocess.run(["schtasks", "/End", "/TN", "QuantEngine Terminal"], capture_output=True, timeout=20)
        time.sleep(3)
    except (OSError, subprocess.SubprocessError):
        pass


def copy(src: Path, dst: Path) -> int:
    n = 0
    for rel in files(src):
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, target)
        n += 1
    return n


def main(src: Path, dst: Path, ask=input, tty=None, is_running=running) -> str:
    if not (src / "app.py").is_file() or not (dst / "app.py").is_file() or src.resolve() == dst.resolve():
        return "NOT_A_PAIR"
    if not (sys.stdin.isatty() if tty is None else tty):
        return "NOT_ASKED"
    print(ASK.format(dst=dst))
    try:
        if ask("바꿀까요? ").strip().lower() not in ("y", "yes", "ㅛ"):
            print("그대로 둡니다.")
            return "KEPT"
    except EOFError:
        return "NOT_ASKED"
    if is_running(dst):
        print("지금 매일 수집이 도는 중이라 바꾸지 않았습니다. 끝난 뒤(연구실 탭의 '자동 실행' 줄에서 확인) 다시 누르세요.")
        return "BUSY"
    stop_server()
    print(f"프로그램 파일 {copy(src, dst)}개를 바꿨습니다. 이어서 패키지를 맞추고 화면 서버를 다시 시작합니다.")
    return "UPDATED"


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
