# Build the Windows bundle and installer. Run from the repository root in PowerShell:
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build_windows.ps1
# Requires: Python 3.11+ (python.org or winget), and Inno Setup 6 (iscc.exe) for the installer.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "tests failed" }
.\.venv\Scripts\python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\quotaring.spec
$version = .\.venv\Scripts\python -c "import quotaring;print(quotaring.__version__)"
New-Item -ItemType Directory -Force packaging\out | Out-Null
Compress-Archive -Force dist\quotaring packaging\out\quotaring-$version-windows-x64.zip
$iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
# Inno Setup installs per machine (Program Files) or, as winget does by default, per user (LocalAppData).
if (-not $iscc) {
    $iscc = @("${env:ProgramFiles(x86)}", "$env:ProgramFiles", "$env:LOCALAPPDATA\Programs") |
        ForEach-Object { Join-Path $_ "Inno Setup 6\ISCC.exe" } | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if ($iscc) { & $iscc /DAppVersion=$version packaging\windows\installer.iss } else { Write-Warning "Inno Setup not found: installer not built" }
