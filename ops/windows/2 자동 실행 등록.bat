@echo off
chcp 65001 >nul
rem 매일 작업과 화면 서버를 Windows 작업 스케줄러에 등록합니다. 로그인하면 스스로 시작됩니다.
rem 등록하면 서버가 바로 켜집니다. 낮에(한국 시간 09~22시), 매일 작업이 돌고 있지 않을 때만 누르세요.
cd /d "%~dp0..\.."
if not exist .venv\Scripts\python.exe (
  echo 파이썬 환경이 없습니다. "1 처음 설치.bat"을 먼저 누르세요.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -X utf8 app.py automation install
.venv\Scripts\python.exe -X utf8 app.py terminal-agent install
echo 위 두 결과에 "installed": true 가 보이면 등록된 것입니다. 브라우저에서 http://127.0.0.1:8765 를 여세요.
pause
