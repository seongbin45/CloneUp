# Diagnose why CloneUp's independent Update Manager may be missing / idle
# on a specific PC. Run in the SAME Windows user session that uses CloneUp.
#
#   powershell -ExecutionPolicy Bypass -File scripts\diagnose_update_manager.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\diagnose_update_manager.ps1 -OutFile "$env:USERPROFILE\Desktop\cloneup-um-diag.txt"
#
# Exit codes:
#   0 = healthy (exe + Run key + recent log activity)
#   1 = broken / missing install layer
#   2 = installed but not updating (runtime / discovery / network)

param(
    [string]$OutFile = ""
)

$ErrorActionPreference = "Continue"
$lines = New-Object System.Collections.Generic.List[string]
function L([string]$s) { [void]$lines.Add($s); Write-Host $s }

$exeName = "CloneUp_update_manager.exe"
$umDir = Join-Path $env:LOCALAPPDATA "CloneUp\UpdateManager"
$umExe = Join-Path $umDir $exeName
$logPath = Join-Path $env:LOCALAPPDATA "CloneUp\logs\update_manager.log"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$appId = "{A7C1E0B2-4D5F-4A8E-9C3B-1F2E3D4C5B6A}_is1"
$unKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$appId"

$flags = @{
    ExePresent        = $false
    RunKeyPresent     = $false
    RunKeyPointsOk    = $false
    LogPresent        = $false
    LogRecent         = $false
    ProcessRunning    = $false
    AppInstallFound   = $false
    VersionReadable   = $false
    LikelyAvQuarantine = $false
    LikelyWrongProfile = $false
    LikelyTaskOptOut  = $false
}

L "=== CloneUp Update Manager diagnosis ==="
L ("Time          : {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
L ("User          : {0}" -f $env:USERNAME)
L ("UserProfile   : {0}" -f $env:USERPROFILE)
L ("LOCALAPPDATA  : {0}" -f $env:LOCALAPPDATA)
L ("IsAdmin token : {0}" -f ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))
L ""

# --- Layer 1: file install ---
L "--- Layer 1: file on disk ---"
L ("Expected exe  : {0}" -f $umExe)
if (Test-Path -LiteralPath $umExe) {
    $flags.ExePresent = $true
    $fi = Get-Item -LiteralPath $umExe
    L ("STATUS        : PRESENT  size={0}  mtime={1}" -f $fi.Length, $fi.LastWriteTime)
} else {
    L "STATUS        : MISSING"
    if (Test-Path -LiteralPath $umDir) {
        L ("Dir exists, contents: {0}" -f ((Get-ChildItem $umDir -ErrorAction SilentlyContinue | ForEach-Object Name) -join ", "))
    } else {
        L "UpdateManager directory does not exist either."
    }
}

# --- Layer 2: autostart ---
L ""
L "--- Layer 2: HKCU Run autostart ---"
try {
    $run = Get-ItemProperty -Path $runKey -ErrorAction Stop
    $val = $run.CloneUpUpdateManager
    if ($null -ne $val -and "$val".Trim() -ne "") {
        $flags.RunKeyPresent = $true
        L ("Run value     : {0}" -f $val)
        $normalized = ("$val".Trim().Trim('"'))
        if (Test-Path -LiteralPath $normalized) {
            $flags.RunKeyPointsOk = $true
            L "Run target    : exists"
        } else {
            L "Run target    : BROKEN PATH (points to missing file)"
        }
    } else {
        L "Run value     : (absent) — exe may exist but will not start at logon"
        if ($flags.ExePresent) { $flags.LikelyTaskOptOut = $true }
    }
    L ("CloneUpTray   : {0}" -f $(if ($run.CloneUpTray) { $run.CloneUpTray } else { "(absent)" }))
} catch {
    L ("Run key read failed: {0}" -f $_.Exception.Message)
}

# --- Layer 3: process + log ---
L ""
L "--- Layer 3: process / log ---"
$procs = Get-Process -Name "CloneUp_update_manager" -ErrorAction SilentlyContinue
if ($procs) {
    $flags.ProcessRunning = $true
    L ("Process       : RUNNING pid={0}" -f (($procs | ForEach-Object Id) -join ","))
} else {
    L "Process       : not running"
}
if (Test-Path -LiteralPath $logPath) {
    $flags.LogPresent = $true
    $lf = Get-Item -LiteralPath $logPath
    $ageHrs = [math]::Round(((Get-Date) - $lf.LastWriteTime).TotalHours, 2)
    L ("Log           : {0}  (age_hours={1})" -f $logPath, $ageHrs)
    if ($ageHrs -lt 24) { $flags.LogRecent = $true }
    L "---- last 25 log lines ----"
    Get-Content -LiteralPath $logPath -Tail 25 -ErrorAction SilentlyContinue | ForEach-Object { L $_ }
    L "---- end log ----"
    $tail = Get-Content -LiteralPath $logPath -Tail 80 -ErrorAction SilentlyContinue
    $joined = ($tail | Out-String)
    if ($joined -match "install dir not found|CloneUp install dir not found") {
        L "NOTE: log shows install-dir discovery failure (manager runs but cannot find CloneUp.exe)."
    }
    if ($joined -match "no usable release|no zip asset|github latest failed|github latest HTTP") {
        L "NOTE: log shows GitHub/network or missing CloneUp-win64.zip asset."
    }
    if ($joined -match "cannot read installed version") {
        L "NOTE: log shows VERSION unreadable under install dir."
    }
} else {
    L ("Log           : MISSING at {0}" -f $logPath)
    if ($flags.ExePresent -and $flags.RunKeyPresent -and -not $flags.ProcessRunning) {
        L "HINT: exe+Run present but never logged — crash before logging, or AV killed first launch."
        $flags.LikelyAvQuarantine = $true
    }
}

# --- Layer 4: CloneUp app discovery (same rules as update_manager.paths) ---
L ""
L "--- Layer 4: CloneUp app install discovery ---"
$installLocation = $null
if (Test-Path -LiteralPath $unKey) {
    $u = Get-ItemProperty -LiteralPath $unKey
    $installLocation = $u.InstallLocation
    L ("ARP DisplayName    : {0}" -f $u.DisplayName)
    L ("ARP DisplayVersion : {0}" -f $u.DisplayVersion)
    L ("ARP InstallLocation: {0}" -f $installLocation)
} else {
    L "ARP HKCU uninstall key missing — Setup may not have registered for this user."
}

$candidates = New-Object System.Collections.Generic.List[string]
if ($installLocation) { [void]$candidates.Add($installLocation.TrimEnd('\', '/')) }
[void]$candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\CloneUp"))
[void]$candidates.Add((Join-Path ${env:ProgramFiles} "CloneUp"))
if (${env:ProgramFiles(x86)}) {
    [void]$candidates.Add((Join-Path ${env:ProgramFiles(x86)} "CloneUp"))
}

$found = $null
foreach ($c in $candidates) {
    if (-not $c) { continue }
    $exe = Join-Path $c "CloneUp.exe"
    $ver = Join-Path $c "VERSION"
    $ok = Test-Path -LiteralPath $exe
    L ("Candidate {0}  CloneUp.exe={1}  VERSION={2}" -f $c, $ok, (Test-Path -LiteralPath $ver))
    if ($ok -and -not $found) {
        $found = $c
        $flags.AppInstallFound = $true
        if (Test-Path -LiteralPath $ver) {
            $flags.VersionReadable = $true
            L ("VERSION text: {0}" -f ((Get-Content -LiteralPath $ver -Raw).Trim()))
        }
    }
}
if (-not $found) {
    L "STATUS: CloneUp.exe not found via ARP/default paths (manager would log no_install)."
}

# --- Layer 5: Defender / quarantine hints ---
L ""
L "--- Layer 5: Defender / MotW hints ---"
try {
    $mp = Get-MpComputerStatus -ErrorAction Stop
    L ("Defender enabled     : {0}" -f $mp.RealTimeProtectionEnabled)
    L ("AM running           : {0}" -f $mp.AMServiceEnabled)
} catch {
    L "Defender status unavailable (non-Defender AV or restricted)."
}
if ($flags.ExePresent) {
    try {
        $zone = Get-Item -LiteralPath $umExe -Stream Zone.Identifier -ErrorAction SilentlyContinue
        if ($zone) {
            L "Mark-of-the-Web     : Zone.Identifier present on updater exe (downloaded/untrusted)."
        } else {
            L "Mark-of-the-Web     : none"
        }
    } catch {
        L "Mark-of-the-Web     : (could not read alternate stream)"
    }
}
# Quarantine: file missing but Run key still points at it
if (-not $flags.ExePresent -and $flags.RunKeyPresent) {
    $flags.LikelyAvQuarantine = $true
    L "PATTERN: Run key exists but exe missing → classic AV quarantine / manual delete."
}

# Wrong profile: LOCALAPPDATA not under current USERPROFILE (rare redirect)
if ($env:LOCALAPPDATA -and $env:USERPROFILE -and ($env:LOCALAPPDATA -notlike ($env:USERPROFILE + "*"))) {
    $flags.LikelyWrongProfile = $true
    L "PATTERN: LOCALAPPDATA is outside USERPROFILE (folder redirection / special profile)."
}

# Other users' LocalAppData (admin install leftover) — informational
L ""
L "--- Other profile scan (admin-elevation leftover check) ---"
$otherHits = @()
Get-ChildItem "C:\Users" -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Join-Path $_.FullName "AppData\Local\CloneUp\UpdateManager\$exeName"
    if ((Test-Path -LiteralPath $p) -and ($p -ne $umExe)) {
        $otherHits += $p
    }
}
if ($otherHits.Count -gt 0) {
    L "Updater found under OTHER user profiles:"
    $otherHits | ForEach-Object { L ("  {0}" -f $_) }
    if (-not $flags.ExePresent) {
        $flags.LikelyWrongProfile = $true
        L "PATTERN: missing for current user but present elsewhere → Setup likely ran elevated / wrong account."
    }
} else {
    L "No updater exe under other C:\Users\*\AppData\Local profiles (or access denied)."
}

# --- Verdict ---
L ""
L "=== VERDICT ==="
$code = 0
if (-not $flags.ExePresent) {
    $code = 1
    L "PRIMARY: Update manager EXE not installed for this user."
    if ($flags.LikelyWrongProfile) {
        L "CAUSE CANDIDATE #1: Wrong Windows profile (elevated Setup / other user)."
        L "ACTION: Re-run CloneUp-Setup.exe by double-click as the daily user (not 'Run as admin')."
    }
    if ($flags.LikelyAvQuarantine) {
        L "CAUSE CANDIDATE #2: AV removed the exe after install (Run key orphan)."
        L "ACTION: Check Windows Security → Protection history; allow CloneUp_update_manager.exe; reinstall."
    }
    L "CAUSE CANDIDATE #3 (historical Setup): task 'autoupdatemanager' + checkedonce skipped file copy on upgrade."
    L "ACTION: Install a Setup built after fix 0ee55f6 (exe always copied); or copy dist\CloneUp_update_manager.exe manually to the Expected path."
} elseif (-not $flags.RunKeyPresent) {
    $code = 1
    L "PRIMARY: EXE present but HKCU Run missing — will not start at login."
    L "CAUSE CANDIDATE: user unchecked '로그인 시 자동 업데이트 관리자 실행' (or old checkedonce upgrade)."
    L "ACTION: Re-run Setup with that task checked, or add Run value pointing at the exe."
} elseif (-not $flags.RunKeyPointsOk) {
    $code = 1
    L "PRIMARY: Run key points to a missing path."
} elseif (-not $flags.LogPresent -or -not $flags.LogRecent) {
    $code = 2
    L "PRIMARY: Installed/registered but little or no log activity."
    L "ACTION: Start `"$umExe`" once; if still no log, AV/Smart App Control is likely blocking launch."
} elseif (-not $flags.AppInstallFound) {
    $code = 2
    L "PRIMARY: Manager can run but cannot find CloneUp.exe (would keep saying no_install)."
    L "ACTION: Repair app install / ensure ARP InstallLocation matches real folder."
} else {
    $code = 0
    L "PRIMARY: Looks healthy for this user (exe + Run + app discovery)."
    if (-not $flags.ProcessRunning) {
        L "NOTE: process not running right now — should appear after next login or manual start."
    }
}

L ""
L "Flag summary:"
$flags.GetEnumerator() | Sort-Object Name | ForEach-Object {
    L ("  {0}={1}" -f $_.Key, $_.Value)
}

$text = ($lines -join "`r`n")
if ($OutFile) {
    Set-Content -LiteralPath $OutFile -Value $text -Encoding UTF8
    Write-Host ""
    Write-Host "Wrote $OutFile"
}
exit $code
