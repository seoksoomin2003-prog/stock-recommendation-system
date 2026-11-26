@echo off
chcp 65001 >nul
rem Windows에 처음 설치할 때 한 번 누릅니다. 파이썬 환경(.venv)을 만들고 필요한 패키지를 받습니다.
rem 먼저 python.org 에서 Python 3.14 (Windows installer, 64-bit)를 설치해 두어야 합니다.
cd /d "%~dp0..\.."
where py >nul 2>nul
if errorlevel 1 (
  echo Python이 없습니다. python.org 에서 Python 3.14 Windows 설치본을 먼저 설치하세요.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  py -3.14 -m venv .venv
  if errorlevel 1 (
    echo 파이썬 환경을 만들지 못했습니다. Python 3.14가 설치돼 있는지 확인하세요.
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.lock
if errorlevel 1 (
  echo 패키지를 받지 못했습니다. 인터넷 연결을 확인하고 다시 누르세요.
  pause
  exit /b 1
)
if not exist .env (
  copy .env.example .env >nul
  echo .env 파일을 만들었습니다. 메모장으로 열어 자기 키를 넣으세요. 안내: reports\RUNBOOK.md
)
echo 설치가 끝났습니다. 이제 "2 자동 실행 등록.bat"을 누르세요.
pause
