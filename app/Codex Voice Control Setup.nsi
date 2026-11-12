# -*- coding: utf-8 -*-
Unicode true
RequestExecutionLevel user
Name "Codex Voice Control"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\Codex Voice Control"
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FridayVoice" "InstallLocation"
SetCompressor zlib
ShowInstDetails show
Var LegacyUpgrade

!include "MUI2.nsh"
!include "x64.nsh"
!include "LogicLib.nsh"

!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_FUNCTION LaunchFriday

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"
!insertmacro MUI_LANGUAGE "Polish"
!insertmacro MUI_LANGUAGE "Albanian"
!insertmacro MUI_LANGUAGE "Arabic"
!insertmacro MUI_LANGUAGE "Armenian"
!insertmacro MUI_LANGUAGE "Bosnian"
!insertmacro MUI_LANGUAGE "Bulgarian"
!insertmacro MUI_LANGUAGE "Catalan"
!insertmacro MUI_LANGUAGE "Croatian"
!insertmacro MUI_LANGUAGE "Czech"
!insertmacro MUI_LANGUAGE "Danish"
!insertmacro MUI_LANGUAGE "Dutch"
!insertmacro MUI_LANGUAGE "Estonian"
!insertmacro MUI_LANGUAGE "Farsi"
!insertmacro MUI_LANGUAGE "Finnish"
!insertmacro MUI_LANGUAGE "French"
!insertmacro MUI_LANGUAGE "Georgian"
!insertmacro MUI_LANGUAGE "German"
!insertmacro MUI_LANGUAGE "Greek"
!insertmacro MUI_LANGUAGE "Hindi"
!insertmacro MUI_LANGUAGE "Hungarian"
!insertmacro MUI_LANGUAGE "Icelandic"
!insertmacro MUI_LANGUAGE "Indonesian"
!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "Japanese"
!insertmacro MUI_LANGUAGE "Korean"
!insertmacro MUI_LANGUAGE "Latvian"
!insertmacro MUI_LANGUAGE "Lithuanian"
!insertmacro MUI_LANGUAGE "Macedonian"
!insertmacro MUI_LANGUAGE "Malay"
!insertmacro MUI_LANGUAGE "Mongolian"
!insertmacro MUI_LANGUAGE "Norwegian"
!insertmacro MUI_LANGUAGE "Portuguese"
!insertmacro MUI_LANGUAGE "PortugueseBR"
!insertmacro MUI_LANGUAGE "Romanian"
!insertmacro MUI_LANGUAGE "Russian"
!insertmacro MUI_LANGUAGE "Serbian"
!insertmacro MUI_LANGUAGE "SerbianLatin"
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "Slovak"
!insertmacro MUI_LANGUAGE "Slovenian"
!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "SpanishInternational"
!insertmacro MUI_LANGUAGE "Swedish"
!insertmacro MUI_LANGUAGE "Thai"
!insertmacro MUI_LANGUAGE "TradChinese"
!insertmacro MUI_LANGUAGE "Turkish"
!insertmacro MUI_LANGUAGE "Ukrainian"
!insertmacro MUI_LANGUAGE "Vietnamese"

!macro RemoveLegacySources
    Delete "$INSTDIR\Autostart.ps1"
    Delete "$INSTDIR\Przygotuj.cmd"
    Delete "$INSTDIR\Uruchom.cmd"
    Delete "$INSTDIR\requirements.txt"
    Delete "$INSTDIR\bar_art.py"
    Delete "$INSTDIR\branding.py"
    Delete "$INSTDIR\chimes.py"
    Delete "$INSTDIR\codex_audio.py"
    Delete "$INSTDIR\codex_chats.py"
    Delete "$INSTDIR\codex_voice_labels.json"
    Delete "$INSTDIR\desktop_tools.py"
    Delete "$INSTDIR\friday.py"
    Delete "$INSTDIR\layered_surface.py"
    Delete "$INSTDIR\listener_state.py"
    Delete "$INSTDIR\localization.py"
    Delete "$INSTDIR\overlay_window.py"
    Delete "$INSTDIR\panel.py"
    Delete "$INSTDIR\settings_art.py"
    Delete "$INSTDIR\settings_dialog.py"
    Delete "$INSTDIR\setup_support.py"
    Delete "$INSTDIR\translations.json"
    Delete "$INSTDIR\tray.py"
    Delete "$INSTDIR\voice_settings.py"
    Delete "$INSTDIR\windowed.pyw"
!macroend

Function .onInit
    SetShellVarContext current
    ${IfNot} ${RunningX64}
        MessageBox MB_ICONSTOP "Codex Voice Control requires 64-bit Windows." /SD IDOK
        Abort
    ${EndIf}
FunctionEnd

Function LaunchFriday
    ExecShell "open" "$INSTDIR\Codex Voice Control.lnk"
FunctionEnd

Section "Codex Voice Control"
    SetShellVarContext current
    StrCpy $LegacyUpgrade "0"
    IfFileExists "$INSTDIR\friday.py" 0 check_existing
    ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FridayVoice" "InstallLocation"
    StrCmp $0 $INSTDIR check_existing
    SetErrorLevel 1
    Abort "Choose a directory outside the application source tree."
check_existing:
    IfFileExists "$INSTDIR\Uninstall.exe" 0 install_files
    IfFileExists "$INSTDIR\app\Cvc.exe" 0 stop_legacy
    nsExec::ExecToLog '"$INSTDIR\app\Cvc.exe" setup stop'
    Goto verify_stop
stop_legacy:
    StrCpy $LegacyUpgrade "1"
    nsExec::ExecToLog '"$INSTDIR\.venv\Scripts\python.exe" "$INSTDIR\setup_support.py" stop'
verify_stop:
    Pop $0
    StrCmp $0 "0" install_files
    SetErrorLevel 1
    Abort "Close Codex Voice Control and try again."

install_files:
    SetOutPath "$INSTDIR\app"
    File /r /x libportaudio64bit-asio.dll "${APPDIST}\*"
    SetOutPath "$INSTDIR\licenses"
    File /r "${NOTICES}\*"
    SetOutPath "$INSTDIR"
    File /oname=README.md "${APPREADME}"
    SetOutPath "$INSTDIR\.models\whisper-base"
    File "${APPMODEL}\config.json"
    File "${APPMODEL}\model.bin"
    File "${APPMODEL}\tokenizer.json"
    File "${APPMODEL}\vocabulary.txt"
    SetOutPath "$INSTDIR"
    nsExec::ExecToLog '"$INSTDIR\app\Cvc.exe" setup install "$SMPROGRAMS"'
    Pop $0
    StrCmp $0 "0" register
    SetErrorLevel 1
    Abort "Setup could not create shortcuts."

register:
    StrCmp $LegacyUpgrade "1" 0 write_registration
    !insertmacro RemoveLegacySources
write_registration:
    CreateShortcut "$DESKTOP\Codex Voice Control.lnk" "$INSTDIR\app\Cvc.exe" "panel" "$INSTDIR\.runtime\tray.ico"
    CreateShortcut "$SMSTARTUP\Codex Voice Control.lnk" "$INSTDIR\app\Cvc.exe" "panel" "$INSTDIR\.runtime\tray.ico"
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FridayVoice" "DisplayName" "Codex Voice Control"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FridayVoice" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FridayVoice" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FridayVoice" "DisplayIcon" "$INSTDIR\.runtime\tray.ico"
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FridayVoice" "NoModify" 1
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FridayVoice" "NoRepair" 1
    IfSilent 0 +2
    Call LaunchFriday
SectionEnd

Section "Uninstall"
    SetShellVarContext current
    ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FridayVoice" "InstallLocation"
    StrCmp $0 $INSTDIR 0 unverified
    IfFileExists "$INSTDIR\app\Cvc.exe" 0 unverified
    nsExec::ExecToLog '"$INSTDIR\app\Cvc.exe" setup uninstall'
    Pop $0
    StrCmp $0 "0" remove_files
    SetErrorLevel 1
    Abort "Setup could not close this installation of Codex Voice Control."

unverified:
    SetErrorLevel 1
    Abort "Setup could not verify the Codex Voice Control installation directory."

remove_files:
    Delete "$SMPROGRAMS\Friday Voice.lnk"
    Delete "$SMPROGRAMS\Codex Voice Control.lnk"
    Delete "$DESKTOP\Codex Voice Control.lnk"
    Delete "$SMSTARTUP\Codex Voice Control.lnk"
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FridayVoice"
    Delete "$INSTDIR\Panel Friday Voice.lnk"
    Delete "$INSTDIR\Codex Voice Control.lnk"
    Delete "$INSTDIR\Uninstall.exe"
    Delete "$INSTDIR\README.md"
    SetOutPath "$TEMP"
    RMDir /r "$INSTDIR\app"
    RMDir /r "$INSTDIR\.venv"
    RMDir /r "$INSTDIR\.python"
    RMDir /r "$INSTDIR\.models"
    RMDir /r "$INSTDIR\.runtime"
    RMDir /r "$INSTDIR\tools"
    RMDir /r "$INSTDIR\licenses"
    RMDir /r "$INSTDIR\__pycache__"
    RMDir "$INSTDIR"
SectionEnd
