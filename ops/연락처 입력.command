#!/bin/zsh
# 미국 재무 자료를 주는 SEC가 요구하는 연락처(이메일)를 넣거나, 설치 때 건너뛴 것을 나중에 넣습니다.
# 자동 실행은 건드리지 않습니다. 넣은 뒤 화면 서버만 다시 시작합니다. 매일 작업은 다음 시각부터 미국 종목을 기록합니다.
cd "$(dirname "$0")/.." || exit 1
if [ ! -x .venv/bin/python ]; then echo "파이썬 환경(.venv)이 없습니다. '처음 설치' 파일을 먼저 누르세요."; exit 1; fi
.venv/bin/python ops/set_contact.py
launchctl kickstart -k "gui/$(id -u)/com.quantengine.terminal" >/dev/null 2>&1 && echo "화면 서버를 다시 시작했습니다."
