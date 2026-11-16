#!/bin/zsh
# 매일 작업을 지금 한 번 실행합니다. 화면의 '지금 수집' 버튼과 같은 일입니다. 화면이 열리지 않을 때만 쓰세요.
# caffeinate: 실행하는 동안 맥이 잠들지 않게 합니다(배터리로 쓸 때 화면에서 눈을 떼면 2분 뒤 멈추던 것을 막습니다).
cd "$(dirname "$0")/.." && /usr/bin/caffeinate -i .venv/bin/python app.py automation run
