@echo off
rem ASCII only: cmd misparses a .bat with non-ASCII text after "chcp 65001".
rem All messages for the owner are printed by Python in Russian.
chcp 65001 >nul
setlocal
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [JARVIS] .venv not found - Python environment is missing.
  echo [JARVIS] Run once in this folder:
  echo     py -3.12 -m venv .venv
  echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo [JARVIS] Step 0 in docs\SETUP.md
  echo.
  pause
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" (
    copy /y ".env.example" ".env" >nul
    echo [JARVIS] Created .env from .env.example - fill it in: docs\SETUP.md, step 2.
  ) else (
    echo [JARVIS] No .env file - see docs\SETUP.md, step 2.
  )
)

where claude >nul 2>&1
if errorlevel 1 (
  echo [JARVIS] Warning: "claude" not found in PATH. Install Claude Code and run: claude then /login
  echo [JARVIS] docs\SETUP.md, step 1
  echo.
)

echo [JARVIS] starting... keep this window open; close it to stop the bot.
".venv\Scripts\python.exe" -m integrations.telegram %*
set CODE=%ERRORLEVEL%
if not "%CODE%"=="0" (
  echo.
  echo [JARVIS] exit code %CODE% - see the message above and docs\SETUP.md
  pause
)
exit /b %CODE%
