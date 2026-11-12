param([switch]$Disable, [switch]$PanelOnly)

$ErrorActionPreference = 'Stop'
$appName = 'Codex Voice Control'
$taskName = 'Friday Voice Listener'
$legacyExe = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$legacyArguments = '-B "{0}" --background' -f (Join-Path $PSScriptRoot 'friday.py')
$launcher = Join-Path $PSScriptRoot 'windowed.pyw'
$arguments = '-s -B "{0}" listener' -f $launcher
$venvConfig = Join-Path $PSScriptRoot '.venv\pyvenv.cfg'

function Get-WindowedPython {
    $bundledPython = Join-Path $PSScriptRoot 'runtime\pythonw.exe'
    if (Test-Path -LiteralPath $bundledPython -PathType Leaf) {
        return $bundledPython
    }
    if (Test-Path -LiteralPath $venvConfig -PathType Leaf) {
        $pythonHome = Select-String -LiteralPath $venvConfig -Pattern '^home\s*=\s*(.+)$' |
            Select-Object -First 1
        if ($pythonHome) {
            return Join-Path $pythonHome.Matches[0].Groups[1].Value.Trim() 'pythonw.exe'
        }
    }
}

function Save-PanelShortcut($pythonExe) {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Join-Path $PSScriptRoot "$appName.lnk"))
    $shortcut.TargetPath = $pythonExe
    $shortcut.Arguments = '-s -B "{0}" panel' -f $launcher
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.Description = $appName
    $icon = Join-Path $PSScriptRoot '.runtime\tray.ico'
    if (Test-Path -LiteralPath $icon -PathType Leaf) { $shortcut.IconLocation = "$icon,0" }
    $shortcut.Save()
}

$exe = Get-WindowedPython
if (-not $Disable) {
    if (-not $exe -or -not (Test-Path -LiteralPath $exe -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.models\whisper-base\model.bin') -PathType Leaf)) {
        & (Join-Path $PSScriptRoot 'Przygotuj.cmd')
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $exe = Get-WindowedPython
    }
    if (-not $exe -or -not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw "Brak interpretera pythonw.exe dla $appName."
    }
    Save-PanelShortcut $exe
    if ($PanelOnly) { return }
}

$existing = Get-ScheduledTask -TaskPath '\' -TaskName $taskName -ErrorAction SilentlyContinue
$isLegacy = $existing -and $existing.Actions.Count -eq 1 -and
    $existing.Actions[0].Execute -eq $legacyExe -and $existing.Actions[0].Arguments -eq $legacyArguments
$isCurrent = $existing -and $existing.Actions.Count -eq 1 -and
    $existing.Actions[0].Execute -eq $exe -and $existing.Actions[0].Arguments -eq $arguments
if ($existing -and -not ($isLegacy -or $isCurrent)) {
    throw "Istnieje inne zadanie o nazwie $taskName. Sprawdz Harmonogram zadan."
}

if ($Disable) {
    if ($existing) {
        Disable-ScheduledTask -TaskPath '\' -TaskName $taskName | Out-Null
        if ($existing.State -eq 'Running') {
            Stop-ScheduledTask -TaskPath '\' -TaskName $taskName
        }
        Unregister-ScheduledTask -TaskPath '\' -TaskName $taskName -Confirm:$false
    }
    return
}

if ($isLegacy -and $existing.State -eq 'Running') {
    Stop-ScheduledTask -TaskPath '\' -TaskName $taskName
}

$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$action = New-ScheduledTaskAction -Execute $exe -Argument $arguments -WorkingDirectory $PSScriptRoot
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskPath '\' -TaskName $taskName -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Description "Lokalny nasluch komend glosowych $appName" -Force |
    Out-Null
if ((Get-ScheduledTask -TaskPath '\' -TaskName $taskName).State -ne 'Running') {
    Start-ScheduledTask -TaskPath '\' -TaskName $taskName
}
