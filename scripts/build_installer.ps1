# Build CloneUp.exe (PyInstaller) then CloneUp-Setup.exe (Inno Setup)
# Usage from repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "== P1: PyInstaller =="
& (Join-Path $Root "scripts\build_exe.ps1")

$exe = Join-Path $Root "dist\CloneUp\CloneUp.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Missing $exe"
}

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    Write-Host "Inno Setup 6 (ISCC.exe) not found."
    Write-Host "Install: winget install --id JRSoftware.InnoSetup -e"
    Write-Host "PyInstaller output is ready at dist\CloneUp\"
    exit 2
}

Write-Host "== DG3: Inno Setup ($iscc) =="
& $iscc (Join-Path $Root "installer\CloneUp.iss")
if ($LASTEXITCODE -ne 0) {
    Write-Error "ISCC failed with exit $LASTEXITCODE"
}

$setup = Join-Path $Root "installer\Output\CloneUp-Setup.exe"
if (-not (Test-Path $setup)) {
    Write-Error "Missing $setup"
}
Write-Host "OK: $setup"
Get-Item $setup | Format-List FullName, Length, LastWriteTime
