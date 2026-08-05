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
Write-Host "OK: $out"
Get-Item $out | Format-List FullName, Length, LastWriteTime
