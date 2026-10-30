# Install the latest QuotaRing release on Windows 10/11, for the current user (no admin rights):
#   irm https://raw.githubusercontent.com/berat-kaan-akcan/quotaring/main/install.ps1 | iex
# Downloads the installer, checks it against the release's SHA256SUMS.txt, installs it silently
# and starts QuotaRing. It updates itself afterwards (Settings > General > Check for updates).
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # Windows PowerShell 5.1 downloads far slower with the progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$base = 'https://github.com/berat-kaan-akcan/quotaring/releases/latest/download'
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('quotaring-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $setup = Join-Path $tmp 'quotaring-setup.exe'
    $sums = Join-Path $tmp 'SHA256SUMS.txt'
    Write-Host 'Downloading QuotaRing...'
    Invoke-WebRequest "$base/SHA256SUMS.txt" -OutFile $sums -UseBasicParsing
    Invoke-WebRequest "$base/quotaring-setup.exe" -OutFile $setup -UseBasicParsing
    $line = Get-Content $sums | Where-Object { $_ -match ' [ *]?quotaring-setup\.exe$' } | Select-Object -First 1
    if ($line -notmatch '^([0-9a-fA-F]{64}) ') { throw 'the release lists no checksum for quotaring-setup.exe' }
    if ((Get-FileHash $setup -Algorithm SHA256).Hash -ne $Matches[1]) { throw 'checksum mismatch: the download is not the released file' }
    Write-Host 'Installing...'
    # Not Start-Process -Wait: it would also wait for QuotaRing, which the installer starts.
    $p = Start-Process $setup -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/RELAUNCH=1' -PassThru
    $p.WaitForExit()
    if ($p.ExitCode -ne 0) { throw "the installer exited with code $($p.ExitCode)" }
    Write-Host 'QuotaRing is installed and running: look for its ring in the tray (Start menu: QuotaRing).'
}
finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
