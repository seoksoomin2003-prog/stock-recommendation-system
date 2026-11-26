@echo off
chcp 65001 >nul
rem 매일 작업을 지금 한 번 실행합니다. 화면의 '지금 수집' 버튼과 같은 일입니다. 화면이 열리지 않을 때만 쓰세요.
rem 실행하는 동안 컴퓨터가 잠들지 않게 프로그램이 스스로 막습니다. 이 창을 닫으면 멈춥니다.
cd /d "%~dp0..\.."
.venv\Scripts\python.exe -X utf8 app.py automation run
pause
