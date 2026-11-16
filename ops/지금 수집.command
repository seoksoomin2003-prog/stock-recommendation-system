#!/bin/zsh
# 매일 작업을 지금 한 번 실행합니다. 화면의 '지금 수집' 버튼과 같은 일입니다. 화면이 열리지 않을 때만 쓰세요.
cd "$(dirname "$0")/.." && .venv/bin/python app.py automation run
