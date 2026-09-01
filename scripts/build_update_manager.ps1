# Build CloneUp_update_manager.exe (onefile) + optional release zip of app onedir.
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\build_update_manager.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\build_update_manager.ps1 -ZipApp

param(
    [switch]$ZipApp
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Error "Missing venv: $py"
}

Write-Host "== pip: pyinstaller =="
& $py -m pip install -q "pyinstaller>=6.0"

Write-Host "== PyInstaller update_manager.spec =="
& $py -m PyInstaller --noconfirm (Join-Path $Root "update_manager.spec")

$out = Join-Path $Root "dist\CloneUp_update_manager.exe"
if (-not (Test-Path $out)) {
    Write-Error "Build failed: $out not found"
}
Write-Host "OK: $out"
Get-Item $out | Format-List FullName, Length, LastWriteTime

if ($ZipApp) {
    $appDir = Join-Path $Root "dist\CloneUp"
    $exe = Join-Path $appDir "CloneUp.exe"
    if (-not (Test-Path $exe)) {
        Write-Error "Missing $exe — run scripts\build_exe.ps1 first"
    }
    $verSrc = Join-Path $Root "VERSION"
    if (Test-Path $verSrc) {
        Copy-Item -Force $verSrc (Join-Path $appDir "VERSION")
    }
    $zip = Join-Path $Root "dist\CloneUp-win64.zip"
    if (Test-Path $zip) { Remove-Item -Force $zip }
    Write-Host "== Zip onedir for GitHub Releases: $zip =="
    # Top-level folder CloneUp\ so updater can find CloneUp\CloneUp.exe
    Compress-Archive -Path $appDir -DestinationPath $zip -CompressionLevel Optimal
    Write-Host "OK: $zip (attach this asset to the GitHub Release — not Setup.exe for auto-update)"
    Get-Item $zip | Format-List FullName, Length, LastWriteTime
}
