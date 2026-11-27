#!/bin/zsh
# 다른 Mac에 처음 설치할 때 한 번 누릅니다. 파이썬 환경(.venv)을 만들고 패키지를 받은 뒤 화면 서버와 매일 자동 실행을 등록합니다.
# 먼저 python.org 에서 Python 3.14를 설치해 두어야 합니다.
cd "$(dirname "$0")/.." || exit 1
PY=$(command -v python3.14 || ls /Library/Frameworks/Python.framework/Versions/3.14/bin/python3.14 /usr/local/bin/python3.14 /opt/homebrew/bin/python3.14 2>/dev/null | head -1)
[ -n "$PY" ] || PY=$(command -v python3)
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)' 2>/dev/null; then
  echo "Python 3.14가 없습니다. python.org 에서 Python 3.14(macOS 64-bit universal2 installer)를 설치한 뒤 다시 누르세요."
  echo "(이 Mac에서 찾은 파이썬: ${PY:-없음} $("$PY" --version 2>/dev/null))"
  exit 1
fi
if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)' 2>/dev/null; then
  echo ".venv 폴더가 다른 파이썬 버전으로 만들어져 있습니다. .venv 폴더를 지우고 다시 누르세요."; exit 1
fi
[ -x .venv/bin/python ] || "$PY" -m venv .venv || { echo "파이썬 환경을 만들지 못했습니다."; exit 1; }
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.lock || { echo "패키지를 받지 못했습니다. 인터넷 연결을 확인하고 다시 누르세요."; exit 1; }
[ -f .env ] || { cp .env.example .env; echo ".env 파일을 만들었습니다. 텍스트 편집기로 열어 자기 키를 넣으세요. 안내: reports/RUNBOOK.md"; }
.venv/bin/python app.py terminal-agent install && .venv/bin/python app.py automation install
echo "끝났습니다. 브라우저에서 http://127.0.0.1:8765 를 여세요."
