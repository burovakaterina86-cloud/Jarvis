@echo off
rem ASCII only: cmd misparses a .bat with non-ASCII text after "chcp 65001".
rem All messages for the owner are printed by Python in Russian.
chcp 65001 >nul
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [JARVIS] .venv not found. Run once:
  echo     py -3.12 -m venv .venv
  echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" copy /y ".env.example" ".env" >nul
)

".venv\Scripts\python.exe" -m integrations.telegram %*
set CODE=%ERRORLEVEL%
if not "%CODE%"=="0" (
  echo.
  echo [JARVIS] exit code %CODE%
  pause
)
exit /b %CODE%
