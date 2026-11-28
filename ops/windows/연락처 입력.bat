@echo off
chcp 65001 >nul
rem 미국 재무 자료를 주는 SEC가 요구하는 연락처(이메일)를 넣거나, 설치 때 건너뛴 것을 나중에 넣습니다.
rem 자동 실행은 건드리지 않습니다. 넣은 뒤 화면 서버만 다시 시작합니다. 매일 작업은 다음 시각부터 미국 종목을 기록합니다.
cd /d "%~dp0..\.."
if not exist .venv\Scripts\python.exe goto novenv
.venv\Scripts\python.exe -X utf8 ops\set_contact.py
schtasks /End /TN "QuantEngine Terminal" >nul 2>nul
schtasks /Run /TN "QuantEngine Terminal" >nul 2>nul
pause
exit /b 0
:novenv
echo 파이썬 환경이 없습니다. "1 처음 설치.bat"을 먼저 누르세요.
pause
exit /b 1
