@echo off
chcp 65001 >nul
rem Windows에 처음 설치할 때 한 번 누릅니다. 파이썬을 따로 설치할 필요가 없습니다: 설치 도구와 Python 3.14, 패키지를
rem 이 폴더의 .tools 와 .venv 안에 받은 뒤 자동 실행을 등록하고 브라우저를 엽니다. 인터넷이 필요합니다.
cd /d "%~dp0..\.."
if not exist app.py goto nofolder
set "UV_PYTHON_INSTALL_DIR=%CD%\.tools\python"
if exist .tools\uv.exe goto haveuv
if not exist .tools mkdir .tools
echo 설치 도구를 받는 중입니다.
curl.exe -L --fail --silent --show-error --retry 3 -o .tools\uv.zip https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip
if errorlevel 1 goto nouv
tar.exe -xf .tools\uv.zip -C .tools
del .tools\uv.zip
if not exist .tools\uv.exe goto nouv
:haveuv
if exist .venv\Scripts\python.exe goto havevenv
echo Python 3.14를 받는 중입니다.
.tools\uv.exe venv --managed-python --python 3.14 --seed .venv
if errorlevel 1 goto novenv
:havevenv
echo 패키지를 받는 중입니다. 몇 분 걸립니다.
.tools\uv.exe pip install --python .venv\Scripts\python.exe -r requirements.lock
if errorlevel 1 goto nopkg
if exist .env goto haveenv
copy .env.example .env >nul
echo .env 파일을 만들었습니다. 메모장으로 열어 자기 키를 넣으세요. 안내: reports\RUNBOOK.md
:haveenv
.venv\Scripts\python.exe -X utf8 ops\set_contact.py
if defined QE_SKIP_SCHEDULE goto skipped
.venv\Scripts\python.exe -X utf8 app.py automation install
.venv\Scripts\python.exe -X utf8 app.py terminal-agent install
ping -n 16 127.0.0.1 >nul
start "" http://127.0.0.1:8765
echo.
echo 끝났습니다. 브라우저에 화면이 열립니다. 안 열리면 http://127.0.0.1:8765 를 직접 여세요.
echo 첫 자료 수집은 두 시간쯤 걸립니다. 전원을 꽂고 컴퓨터가 잠들지 않게 해 두세요.
pause
exit /b 0
:skipped
echo 자동 실행 등록은 건너뜁니다. 시험용입니다.
exit /b 0
:nofolder
echo 프로그램 폴더를 찾지 못했습니다. zip 파일을 오른쪽 클릭해 압축을 모두 푼 뒤, 풀린 폴더에서 다시 누르세요.
goto failed
:nouv
echo 설치 도구를 받지 못했습니다. 인터넷 연결을 확인하고 다시 누르세요.
goto failed
:novenv
echo 파이썬 환경을 만들지 못했습니다. 인터넷 연결을 확인하고 다시 누르세요.
goto failed
:nopkg
echo 패키지를 받지 못했습니다. 인터넷 연결을 확인하고 다시 누르세요.
:failed
echo 이 창의 마지막 몇 줄을 프로그램을 준 사람에게 보여 주세요.
pause
exit /b 1
