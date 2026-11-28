#!/bin/zsh
# 다른 Mac에 처음 설치할 때 한 번 누릅니다. 파이썬을 따로 설치할 필요가 없습니다: 설치 도구(uv)와 Python 3.14, 패키지를
# 이 폴더의 .tools 와 .venv 안에 받은 뒤 화면 서버와 매일 자동 실행을 등록하고 브라우저를 엽니다. 인터넷이 필요합니다.
cd "$(dirname "$0")/.." || exit 1
BASE="$(pwd -P)"
fail() { echo; echo "$1"; echo "이 창의 마지막 몇 줄을 프로그램을 준 사람에게 보여 주세요."; exit 1; }
UV="$BASE/.tools/uv"
export UV_PYTHON_INSTALL_DIR="$BASE/.tools/python"
if [ ! -x "$UV" ]; then
  case "$(uname -m)" in arm64) ARCH=aarch64 ;; *) ARCH=x86_64 ;; esac
  echo "설치 도구를 받는 중입니다."
  rm -rf .tools/dl; mkdir -p .tools/dl
  curl -LsSf --retry 3 -o .tools/dl/uv.tar.gz "https://github.com/astral-sh/uv/releases/latest/download/uv-$ARCH-apple-darwin.tar.gz" \
    && tar -xzf .tools/dl/uv.tar.gz -C .tools/dl && mv ".tools/dl/uv-$ARCH-apple-darwin/uv" "$UV" \
    || fail "설치 도구를 받지 못했습니다. 인터넷 연결을 확인하고 다시 누르세요."
  rm -rf .tools/dl
fi
if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)' 2>/dev/null; then
  fail ".venv 폴더가 다른 파이썬 버전으로 만들어져 있거나 깨져 있습니다. .venv 폴더를 지우고 다시 누르세요."
fi
if [ ! -x .venv/bin/python ]; then
  echo "Python 3.14를 받는 중입니다."
  "$UV" venv --managed-python --python 3.14 --seed .venv || fail "파이썬 환경을 만들지 못했습니다. 인터넷 연결을 확인하고 다시 누르세요."
fi
echo "패키지를 받는 중입니다(몇 분 걸립니다)."
"$UV" pip install --python .venv/bin/python -r requirements.lock || fail "패키지를 받지 못했습니다. 인터넷 연결을 확인하고 다시 누르세요."
[ -f .env ] || { cp .env.example .env; echo ".env 파일을 만들었습니다. 텍스트 편집기로 열어 자기 키를 넣으세요. 안내: reports/RUNBOOK.md"; }
.venv/bin/python ops/set_contact.py
if [ -n "$QE_SKIP_SCHEDULE" ]; then echo "자동 실행 등록은 건너뜁니다(시험용)."; exit 0; fi
PLIST="$HOME/Library/LaunchAgents/com.quantengine.terminal.plist"
if [ -f "$PLIST" ] && ! grep -qF "$BASE/" "$PLIST"; then
  OLD=$(grep -oE '/[^<>&;]*/\.venv/bin/python' "$PLIST" | head -1)
  if [ -n "$OLD" ] && [ -e "$OLD" ]; then
    fail "이 Mac에는 다른 폴더에 있는 이 프로그램이 이미 등록돼 있습니다(${OLD%/.venv/bin/python}). 두 벌을 함께 돌리면 기록이 섞이므로 설치를 멈춥니다. 그 폴더를 그만 쓰려면 그 폴더 ops의 '자동 실행 해제'를 먼저 누르세요."
  fi
  echo "예전 폴더의 등록이 남아 있지만 그 폴더가 없어졌습니다(옮겼거나 지움). 이 폴더로 다시 등록합니다."
  for name in com.quantengine.terminal com.quantengine.daily; do launchctl bootout "gui/$(id -u)/$name" 2>/dev/null; rm -f "$HOME/Library/LaunchAgents/$name.plist"; done
fi
.venv/bin/python app.py terminal-agent install >/dev/null || fail "화면 서버의 자동 실행을 등록하지 못했습니다."
DAILY="$HOME/Library/LaunchAgents/com.quantengine.daily.plist"
hour=$(TZ=Asia/Seoul date +%H)
if [ -f "$DAILY" ] && grep -qF "$BASE/" "$DAILY"; then
  echo "매일 수집은 이미 등록돼 있어 그대로 둡니다."           # registering again would stop a collection that is running
elif [ "$hour" -lt 9 ] || [ "$hour" -ge 22 ]; then
  NIGHT=1
else
  .venv/bin/python app.py automation install >/dev/null || fail "매일 수집의 자동 실행을 등록하지 못했습니다."
fi
for i in $(seq 1 30); do curl -sf -m 2 -o /dev/null http://127.0.0.1:8765/api/health && break; sleep 2; done
open "http://127.0.0.1:8765"
echo
echo "끝났습니다. 브라우저에 화면이 열립니다(안 열리면 http://127.0.0.1:8765 를 직접 여세요)."
if [ -n "$NIGHT" ]; then
  echo "지금은 한국 시간 ${hour}시라 매일 수집은 아직 등록하지 않았습니다(밤과 새벽에는 그날 자료가 덜 나와 있습니다)."
  echo "한국 시간 09시~22시 사이에 이 파일을 한 번 더 누르면 등록되고 첫 수집이 시작됩니다."
else
  echo "첫 자료 수집은 두 시간쯤 걸립니다. 전원을 꽂고 Mac이 잠들지 않게 해 두세요."
fi
