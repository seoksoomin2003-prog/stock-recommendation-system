@echo off
chcp 65001 >nul
rem 매일 작업과 화면 서버를 Windows 작업 스케줄러에 다시 등록합니다. 처음 설치 때는 "1 처음 설치.bat"이 이 일까지 하므로 누를 필요가 없습니다.
rem 등록하면 서버가 바로 켜지고 매일 작업이 한 번 실행됩니다. 낮에(한국 시간 09~22시), 매일 작업이 돌고 있지 않을 때만 누르세요.
cd /d "%~dp0..\.."
if not exist .venv\Scripts\python.exe goto ready
.venv\Scripts\python.exe -c "import sys, datetime as d; sys.exit(0 if (d.datetime.now(d.timezone.utc) + d.timedelta(hours=9)).hour in range(9, 22) else 1)"
if not errorlevel 1 goto ready
echo 지금은 한국 시간으로 밤이나 새벽입니다. 그 시간에는 등록하지 않습니다. 09시에서 22시 사이에 다시 누르세요.
pause
exit /b 1
:ready
if not exist .venv\Scripts\python.exe (
  echo 파이썬 환경이 없습니다. "1 처음 설치.bat"을 먼저 누르세요.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -X utf8 app.py automation install
.venv\Scripts\python.exe -X utf8 app.py terminal-agent install
echo 위 두 결과에 "installed": true 가 보이면 등록된 것입니다. 브라우저에서 http://127.0.0.1:8765 를 여세요.
pause
