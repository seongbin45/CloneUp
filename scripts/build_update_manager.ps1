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

# Hidden launchers beside the exe (manual copy / diagnose); Setup also ships them.
$launchSrc = Join-Path $Root "update_manager\launchers"
foreach ($name in @("CloneUp_update_manager.bat", "CloneUp_update_manager_hidden.vbs")) {
    $src = Join-Path $launchSrc $name
    if (Test-Path $src) {
        Copy-Item -Force $src (Join-Path $Root "dist\$name")
        Write-Host "OK: dist\$name"
    }
}

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

    # Stage zip root with BOTH app onedir and UpdateManager payload so apply
    # can refresh ProgramData\CloneUp\UpdateManager (closes deploy gap).
    $stage = Join-Path $Root "dist\_zip_stage"
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    New-Item -ItemType Directory -Path $stage | Out-Null
    Copy-Item -Recurse -Force $appDir (Join-Path $stage "CloneUp")

    $umDir = Join-Path $stage "UpdateManager"
    New-Item -ItemType Directory -Path $umDir | Out-Null
    Copy-Item -Force $out (Join-Path $umDir "CloneUp_update_manager.exe")
    $launchSrc = Join-Path $Root "update_manager\launchers"
    foreach ($name in @("CloneUp_update_manager.bat", "CloneUp_update_manager_hidden.vbs")) {
        $src = Join-Path $launchSrc $name
        if (-not (Test-Path $src)) { Write-Error "Missing launcher $src" }
        Copy-Item -Force $src (Join-Path $umDir $name)
    }

    $zip = Join-Path $Root "dist\CloneUp-win64.zip"
    if (Test-Path $zip) { Remove-Item -Force $zip }
    Write-Host "== Zip app+UM for GitHub Releases: $zip =="
    # Top-level CloneUp\ + UpdateManager\ (not a single nested folder)
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal
    Remove-Item -Recurse -Force $stage
    Write-Host "OK: $zip (CloneUp\ + UpdateManager\ — attach to GitHub Release)"
    Get-Item $zip | Format-List FullName, Length, LastWriteTime
}
