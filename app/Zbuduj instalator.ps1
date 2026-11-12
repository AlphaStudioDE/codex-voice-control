param(
    [string]$Destination,
    [string]$BuildRoot = (Join-Path ([IO.Path]::GetTempPath()) 'cvc-native-build'),
    [string]$CpuRuntimeSource,
    [switch]$ReuseBuild
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not $Destination) {
    $Destination = Join-Path (Split-Path -Parent $root) 'Codex Voice Control Setup.exe'
}
$Destination = [IO.Path]::GetFullPath($Destination)
$compiler = (Get-Command makensis.exe -ErrorAction SilentlyContinue).Source
if (-not $compiler) { $compiler = Join-Path ${env:ProgramFiles(x86)} 'NSIS\makensis.exe' }
if (-not (Test-Path -LiteralPath $compiler -PathType Leaf)) { throw 'NSIS compiler not found.' }
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Run Przygotuj.cmd first.' }

Push-Location -LiteralPath $root
try {
    if (-not $ReuseBuild) {
        & $python -B -m nuitka --standalone --msvc=latest --assume-yes-for-downloads --jobs=12 --enable-plugin=tk-inter `
            --include-package=comtypes --nofollow-import-to=comtypes.test,av --no-prefer-source-code `
            "--user-package-configuration-file=$(Join-Path $root 'windows-bundle.nuitka-package.config.yml')" `
            --windows-console-mode=attach --include-data-files=translations.json=translations.json `
            --include-data-files=codex_voice_labels.json=codex_voice_labels.json --include-package-data=faster_whisper `
            --include-package-data=_sounddevice_data --output-filename=Cvc.exe "--output-dir=$BuildRoot" distribution.py
        if ($LASTEXITCODE -ne 0) { throw 'Nuitka compilation failed.' }
    }
    $app = Join-Path $BuildRoot 'distribution.dist'
    if (-not (Test-Path -LiteralPath (Join-Path $app 'Cvc.exe') -PathType Leaf)) { throw 'Missing compiled application.' }
    if ($CpuRuntimeSource) {
        $revision = & git -C $CpuRuntimeSource rev-parse HEAD
        if ($LASTEXITCODE -ne 0 -or $revision -ne 'a22ba1c63ee35d1a0d25db149aa2a66d36a6a732') {
            throw 'Unexpected CTranslate2 source revision.'
        }
        $cpuDll = Join-Path $CpuRuntimeSource 'out\Release\ctranslate2.dll'
        Copy-Item -LiteralPath $cpuDll -Destination (Join-Path $app 'ctranslate2.dll') -Force
        $intel = Join-Path $app 'libiomp5md.dll'
        if (Test-Path -LiteralPath $intel -PathType Leaf) {
            Move-Item -LiteralPath $intel -Destination (Join-Path $BuildRoot 'libiomp5md.dll') -Force
        }
    }
    $sourceNames = Get-ChildItem -LiteralPath $root -File | Where-Object Extension -in '.py','.pyw' | Select-Object -ExpandProperty BaseName
    $unexpected = Get-ChildItem -LiteralPath $app -Recurse -File | Where-Object {
        $_.Extension -in '.py','.pyw','.pyc' -and ($_.BaseName -split '\.')[0] -in $sourceNames
    }
    if ($unexpected) { throw "Application source in distribution: $($unexpected.FullName -join ', ')" }
    if (Get-ChildItem -LiteralPath $app -Recurse -File | Where-Object Name -Match '^(avcodec|avformat|avutil|avdevice|avfilter|swscale|swresample)-.*\.dll$') {
        throw 'Unexpected FFmpeg DLL in the Windows distribution.'
    }
    $exe = Join-Path $app 'Cvc.exe'
    @'
import subprocess
import sys

result = subprocess.run([sys.argv[1], "voice", "--help"], capture_output=True, timeout=30,
                        creationflags=subprocess.CREATE_NO_WINDOW)
if result.returncode or b"--from-wav" not in result.stdout:
    sys.stderr.buffer.write(result.stderr)
    raise SystemExit(1)
'@ | & $python -B - $exe
    if ($LASTEXITCODE -ne 0) { throw 'Compiled voice mode failed its startup check.' }

    $notices = Join-Path $BuildRoot 'licenses'
    New-Item -ItemType Directory -Force -Path $notices | Out-Null
    foreach ($notice in 'LICENSE', 'THIRD_PARTY_NOTICES.md') {
        Copy-Item -LiteralPath (Join-Path (Split-Path -Parent $root) $notice) -Destination $notices
    }
    if ($CpuRuntimeSource) {
        $cpuNotices = @{
            'CTranslate2' = 'LICENSE'
            'Ruy' = 'third_party/ruy/LICENSE'
            'cpu_features' = 'third_party/cpu_features/LICENSE'
            'spdlog' = 'third_party/spdlog/LICENSE'
            'cpuinfo' = 'third_party/ruy/third_party/cpuinfo/LICENSE'
            'clog' = 'third_party/ruy/third_party/cpuinfo/deps/clog/LICENSE'
        }
        foreach ($item in $cpuNotices.GetEnumerator()) {
            Copy-Item -LiteralPath (Join-Path $CpuRuntimeSource $item.Value) -Destination (Join-Path $notices "$($item.Key)-LICENSE.txt")
        }
    }
    Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/PortAudio/portaudio/v19.7.0/LICENSE.txt' `
        -OutFile (Join-Path $notices 'PortAudio-LICENSE.txt')
    $model = Join-Path $root '.models\whisper-base'
    foreach ($name in 'config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt') {
        if (-not (Test-Path -LiteralPath (Join-Path $model $name) -PathType Leaf)) {
            throw 'Run Przygotuj.cmd first to obtain the speech model.'
        }
    }
    $hash = (Get-FileHash -LiteralPath (Join-Path $model 'model.bin') -Algorithm SHA256).Hash
    if ($hash -ne 'D01C3014881C9C6F3133C182F3D2887EB6CA1C789A7538C5C007196857A0A6A9') {
        throw 'Unexpected Whisper base model revision.'
    }
    Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/openai/whisper/main/LICENSE' `
        -OutFile (Join-Path $notices 'Whisper-LICENSE.txt')
    'Systran/faster-whisper-base, revision ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66 (MIT)' |
        Set-Content -LiteralPath (Join-Path $notices 'Whisper-model.txt') -Encoding utf8
    @'
from importlib.metadata import distributions
from pathlib import Path
import re
import shutil
import sys

root = Path(sys.argv[1])
for dist in distributions():
    key = re.sub(r"[^a-zA-Z0-9._-]", "_", dist.metadata["Name"])
    if key.lower() == "av":
        continue
    files = [item for item in dist.files or ()
             if item.name.lower().startswith(("license", "copying", "notice", "authors"))]
    for item in files:
        source = dist.locate_file(item)
        if source.is_file() and not item.is_absolute() and ".." not in item.parts:
            target = root / key / item
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
license_file = Path(sys.base_prefix) / "LICENSE.txt"
if license_file.is_file():
    shutil.copyfile(license_file, root / "Python-LICENSE.txt")
for license_file in (Path(sys.base_prefix) / "tcl").glob("*/license.terms"):
    shutil.copyfile(license_file, root / f"{license_file.parent.name}-license.terms")
'@ | & $python -B - $notices
    if ($LASTEXITCODE -ne 0) { throw 'Could not gather third-party license notices.' }
    & $compiler /V2 "/DAPPDIST=$app" "/DNOTICES=$notices" "/DOUTFILE=$Destination" `
        "/DAPPMODEL=$model" `
        "/DAPPREADME=$(Join-Path (Split-Path -Parent $root) 'README.md')" (Join-Path $root 'Codex Voice Control Setup.nsi')
    if ($LASTEXITCODE -ne 0) { throw 'Could not build the installer.' }
    Get-Item -LiteralPath $Destination | Select-Object FullName,Length
} finally {
    Pop-Location
}
