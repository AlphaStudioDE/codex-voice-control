# Building the Windows installer

Use Windows x64, PowerShell, `uv`, the MSVC C++ build tools, and NSIS with `makensis.exe` available. Run these commands from the repository root:

```powershell
cd app
.\Przygotuj.cmd
uv pip install --python .\.venv\Scripts\python.exe nuitka==4.3.5
& '.\Zbuduj instalator.ps1'
```

The installer is written to the repository root by default. Pass `-Destination` to choose another path. The build downloads upstream license notices and verifies the speech model checksum before packaging.

For the CPU runtime used in the public beta, build CTranslate2 at the revision and with the options listed in [Third-party software](THIRD_PARTY_NOTICES.md). Build its Release target into `out\Release` and pass the CTranslate2 checkout directory to `-CpuRuntimeSource`. The script replaces the runtime DLL and gathers the corresponding license notices.