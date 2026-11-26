@echo off
chcp 65001 >nul
rem 화면 서버를 다시 시작합니다. 화면이 열리지 않을 때 누르세요.
schtasks /End /TN "QuantEngine Terminal" >nul 2>nul
schtasks /Run /TN "QuantEngine Terminal"
if errorlevel 1 (
  echo 다시 시작하지 못했습니다. "2 자동 실행 등록.bat"을 누르세요.
) else (
  echo 서버를 다시 시작했습니다. 브라우저에서 http://127.0.0.1:8765 를 여세요.
)
pause
