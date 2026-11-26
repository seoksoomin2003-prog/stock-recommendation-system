@echo off
chcp 65001 >nul
rem 매일 작업과 화면 서버의 자동 실행을 해제합니다(프로그램을 지우기 전에 누릅니다). 기록은 지워지지 않습니다.
cd /d "%~dp0..\.."
.venv\Scripts\python.exe -X utf8 app.py terminal-agent uninstall
.venv\Scripts\python.exe -X utf8 app.py automation uninstall
pause
