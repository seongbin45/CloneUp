# Download UB-Mannheim Tesseract installer into installer\redist for Inno Setup.
# Usage (repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\fetch_tesseract_redist.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Redist = Join-Path $Root "installer\redist"
New-Item -ItemType Directory -Force -Path $Redist | Out-Null

$Name = "tesseract-ocr-w64-setup-5.4.0.20240606.exe"
$Dest = Join-Path $Redist $Name
$Url = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/$Name"

if (Test-Path $Dest) {
    $len = (Get-Item $Dest).Length
    if ($len -gt 5MB) {
        Write-Host "OK: already present $Dest ($len bytes)"
        exit 0
    }
}

Write-Host "Downloading $Url ..."
Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
Get-Item $Dest | Format-List FullName, Length, LastWriteTime
Write-Host "OK: $Dest"
