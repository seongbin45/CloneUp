# Build CloneUp Windows onedir with PyInstaller
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Missing venv: $py"
}

Write-Host "== pip: pyinstaller =="
& $py -m pip install -q "pyinstaller>=6.0"

Write-Host "== PyInstaller cloneup.spec =="
& $py -m PyInstaller --noconfirm (Join-Path $Root "cloneup.spec")

$out = Join-Path $Root "dist\CloneUp\CloneUp.exe"
if (-not (Test-Path $out)) {
    Write-Error "Build failed: $out not found"
}

# VERSION next to exe (update_manager reads {app}\VERSION; datas land in _internal)
$verSrc = Join-Path $Root "VERSION"
$verDst = Join-Path $Root "dist\CloneUp\VERSION"
if (Test-Path $verSrc) {
    Copy-Item -Force $verSrc $verDst
    Write-Host "OK: $verDst"
}

# Field diagnosis script (tray auto-report embeds its output when present)
$diagSrc = Join-Path $Root "scripts\diagnose_update_manager.ps1"
$diagDir = Join-Path $Root "dist\CloneUp\scripts"
$diagDst = Join-Path $diagDir "diagnose_update_manager.ps1"
if (Test-Path $diagSrc) {
    New-Item -ItemType Directory -Force -Path $diagDir | Out-Null
    Copy-Item -Force $diagSrc $diagDst
    Write-Host "OK: $diagDst"
}

Write-Host "OK: $out"
Get-Item $out | Format-List FullName, Length, LastWriteTime
