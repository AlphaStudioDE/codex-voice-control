@echo off
setlocal
cd /d "%~dp0"
if not exist "Codex Voice Control.lnk" (
  powershell.exe -NoProfile -NonInteractive -File "%~dp0Autostart.ps1" -PanelOnly
  if errorlevel 1 (
    pause
    exit /b 1
  )
)
start "" "%~dp0Codex Voice Control.lnk"
