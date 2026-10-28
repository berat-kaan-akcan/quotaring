# Build the Windows bundle and installer. Run from the repository root in PowerShell:
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
# Requires: Python 3.11+ (python.org or winget), and Inno Setup 6 (iscc.exe) for the installer.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\aiusage.spec
New-Item -ItemType Directory -Force packaging\out | Out-Null
Compress-Archive -Force dist\ai-usage-widget packaging\out\ai-usage-widget-0.1.0-windows-x64.zip
$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (Test-Path $iscc) { & $iscc packaging\windows\installer.iss } else { Write-Warning "Inno Setup not found: installer not built" }
