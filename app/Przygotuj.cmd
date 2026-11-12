@echo off
setlocal
cd /d "%~dp0"
set "FRIDAY_UV=uv.exe"
set "FRIDAY_PYTHON=3.12"
set "FRIDAY_PYTHON_FLAGS="
if exist "tools\uv.exe" (
  set "FRIDAY_UV=%~dp0tools\uv.exe"
  set "FRIDAY_PYTHON=3.12.13"
  set "FRIDAY_PYTHON_FLAGS=--managed-python"
  set "UV_PYTHON_INSTALL_DIR=%~dp0.python"
  set "UV_CACHE_DIR=%~dp0.runtime\setup-cache"
  set "UV_NO_CONFIG=true"
  set "UV_LINK_MODE=copy"
) else (
  where uv >nul 2>&1
  if errorlevel 1 (
    echo Brak uv. Zainstaluj uv i uruchom ten plik ponownie.
    exit /b 1
  )
)
if not exist ".venv\Scripts\python.exe" (
  "%FRIDAY_UV%" venv %FRIDAY_PYTHON_FLAGS% --python "%FRIDAY_PYTHON%" .venv
  if errorlevel 1 exit /b 1
)
"%FRIDAY_UV%" pip install --only-binary :all: --python ".venv\Scripts\python.exe" -r requirements.txt
if errorlevel 1 exit /b 1
set "HF_HUB_DISABLE_TELEMETRY=1"
set "HF_HUB_DISABLE_XET=1"
if not exist ".models\whisper-base\model.bin" (
  ".venv\Scripts\python.exe" friday.py --prepare
  if errorlevel 1 exit /b 1
)
echo Codex Voice Control jest gotowy do uruchomienia.
