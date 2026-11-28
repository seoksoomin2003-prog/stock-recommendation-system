#!/bin/zsh
# 매일 작업과 화면 서버의 자동 실행을 해제합니다. 프로그램을 지우거나 폴더를 옮기기 전에 누릅니다. 기록은 지워지지 않습니다.
# 이것을 누르지 않고 폴더만 휴지통에 넣으면 자동 실행이 남아 계속 실패합니다. 폴더를 이미 옮긴 뒤에 눌러도 됩니다.
echo "매일 작업과 화면 서버의 자동 실행을 해제합니다. 계속하려면 Enter, 그만두려면 이 창을 닫으세요."
read
for name in com.quantengine.terminal com.quantengine.daily; do
  launchctl bootout "gui/$(id -u)/$name" 2>/dev/null
  rm -f "$HOME/Library/LaunchAgents/$name.plist"
done
echo "해제했습니다. 다시 쓰려면 '처음 설치' 파일을 누르세요."
echo "프로그램을 아주 지우려면 이제 이 폴더를 휴지통에 넣으면 됩니다(기록도 함께 지워집니다. 백업은 홈 폴더의 QuantEngineBackups에 남습니다)."
