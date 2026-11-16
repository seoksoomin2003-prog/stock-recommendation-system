#!/bin/zsh
# 터미널 서버(화면)를 다시 시작합니다. 화면이 열리지 않을 때 Finder에서 이 파일을 두 번 누르세요.
launchctl kickstart -k "gui/$(id -u)/com.quantengine.terminal" && echo "서버를 다시 시작했습니다. 브라우저에서 http://127.0.0.1:8765 를 여세요." || echo "다시 시작하지 못했습니다. reports/RUNBOOK.md의 '화면이 열리지 않을 때'를 보세요."
