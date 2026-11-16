#!/bin/zsh
# 매일 작업과 터미널 서버의 자동 실행을 다시 등록합니다.
# 쓸 때: '서버 다시 시작'이 "다시 시작하지 못했습니다"라고 할 때, 시스템 설정의 로그인 항목에서 꺼 버렸을 때,
#        파이썬 환경(.venv)을 다시 만들었을 때, 새 맥으로 옮겼을 때. 안내: reports/RUNBOOK.md 8절.
# 등록하면 매일 작업이 그 자리에서 한 번 실행됩니다. 낮에, 매일 작업이 돌고 있지 않을 때만 누르세요.
cd "$(dirname "$0")/.." || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "파이썬 환경(.venv)이 없습니다. reports/RUNBOOK.md 8절대로 먼저 만드세요."
  exit 1
fi
hour=$(TZ=Asia/Seoul date +%H)
if [ "$hour" -lt 9 ] || [ "$hour" -ge 22 ]; then
  echo "지금은 한국 시간 ${hour}시입니다. 밤과 이른 아침에는 등록하지 않습니다(자료가 덜 나온 시간에 기록이 시작될 수 있습니다). 09시~22시에 다시 누르세요."
  exit 1
fi
echo "매일 작업과 서버의 자동 실행을 다시 등록합니다. 계속하려면 Enter, 그만두려면 이 창을 닫으세요."
read
.venv/bin/python app.py automation install && .venv/bin/python app.py terminal-agent install \
  && echo "등록했습니다. 브라우저에서 http://127.0.0.1:8765 를 여세요." \
  || echo "등록하지 못했습니다. 위에 나온 글을 reports/RUNBOOK.md 5절과 함께 고칠 사람에게 보여 주세요."
