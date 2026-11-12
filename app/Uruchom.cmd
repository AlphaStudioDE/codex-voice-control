@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto setup
if not exist ".models\whisper-base\model.bin" goto setup
goto run
:setup
call Przygotuj.cmd
if errorlevel 1 (
  pause
  exit /b 1
)
:run
set "PYTHONUTF8=1"
".venv\Scripts\python.exe" friday.py %*
if errorlevel 1 pause
