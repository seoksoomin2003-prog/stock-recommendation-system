"""Asks the receiver of a copy for the contact address the SEC requires, once, at install (2026-11-28, user decision).

The SEC serves its company data only to a requester that names itself ("<program> <e-mail>").  The owner's own address is
not in the copy, so each computer gives its own.  The address goes into this folder's .env and nowhere else: it is not
printed back, logged or sent anywhere but to the SEC as the request's User-Agent.  An empty answer skips: US fundamentals
then read as missing and everything else works.  Pressing the install file again asks again.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils import runtime_config  # noqa: E402

KEY = "SEC_USER_AGENT"
NAME = "QuantEngine"
ASK = ("\n미국 기업의 재무 자료는 미국 증권거래위원회(SEC)에서 받습니다. SEC는 자료를 받는 사람의 연락처(이메일)를 요구합니다.\n"
       "입력한 주소는 이 컴퓨터의 .env 파일에만 저장되고 SEC에 보내는 요청에만 쓰입니다.\n"
       "건너뛰려면 그냥 Enter를 누르세요(미국 재무 자료만 '자료 없음'이 되고, 설치 파일을 다시 누르면 다시 묻습니다).\n")


def stored(text: str) -> str:
    """The value on the key's line of a key file ('' when the line is absent or empty)."""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[len("export "):]
        if line.startswith(KEY + "="):
            return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def with_value(text: str, value: str) -> str:
    """The key file with the key's line set (the first such line is replaced, or a line is added at the end)."""
    lines, done = [], False
    for raw in text.splitlines():
        s = raw.strip()
        if not done and (s.startswith(KEY + "=") or s.startswith("export " + KEY + "=")):
            lines.append(f"{KEY}={value}")
            done = True
        else:
            lines.append(raw)
    if not done:
        lines.append(f"{KEY}={value}")
    return "\n".join(lines) + "\n"


def value_for(answer: str) -> str:
    return f"{NAME} {answer.strip()}"


def main(env: Path = ROOT / ".env", ask=input, tty: bool | None = None) -> str:
    text = env.read_text(encoding="utf-8") if env.is_file() else ""
    if runtime_config.sec_user_agent_status(stored(text) or os.getenv(KEY, ""))["status"] == "CONFIGURED":
        return "ALREADY"
    if os.getenv("QE_SKIP_SCHEDULE") or not (sys.stdin.isatty() if tty is None else tty):
        return "NOT_ASKED"
    print(ASK)
    for _ in range(5):
        try:
            answer = ask("이메일 주소: ").strip()
        except EOFError:
            return "NOT_ASKED"
        if not answer:
            print("건너뜁니다.")
            return "SKIPPED"
        if runtime_config.sec_user_agent_status(value_for(answer))["status"] == "CONFIGURED":
            env.write_text(with_value(text, value_for(answer)), encoding="utf-8")
            try:
                os.chmod(env, 0o600)
            except OSError:
                pass
            print("저장했습니다.")
            return "SAVED"
        print("이메일 주소로 읽히지 않습니다. 다시 입력하거나 그냥 Enter로 건너뛰세요.")
    return "SKIPPED"


if __name__ == "__main__":
    main()
