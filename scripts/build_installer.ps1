# Build CloneUp.exe (PyInstaller) then CloneUp-Setup.exe (Inno Setup)
# Usage from repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "== Terms: export license for Inno Setup =="
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}
& $py (Join-Path $Root "scripts\export_terms_license.py")
if ($LASTEXITCODE -ne 0) {
    Write-Error "export_terms_license.py failed"
}
$license = Join-Path $Root "installer\license\CloneUp_Terms_ko.txt"
if (-not (Test-Path $license)) {
    Write-Error "Missing $license"
}

$ico = Join-Path $Root "assets\icons\CloneUp.ico"
if (-not (Test-Path $ico)) {
    Write-Error "Missing $ico — run scripts\generate_icons.py first"
}

Write-Host "== P1: PyInstaller (CloneUp app) =="
& (Join-Path $Root "scripts\build_exe.ps1")

$exe = Join-Path $Root "dist\CloneUp\CloneUp.exe"
if (-not (Test-Path $exe)) {
    Write-Error "Missing $exe"
}

Write-Host "== Update manager + release zip =="
& (Join-Path $Root "scripts\build_update_manager.ps1") -ZipApp
$um = Join-Path $Root "dist\CloneUp_update_manager.exe"
if (-not (Test-Path $um)) {
    Write-Error "Missing $um"
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
