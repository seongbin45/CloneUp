; Inno Setup script for CloneUp (DG3)
; Prerequisites:
;   1) Build exe:  powershell -File scripts\build_exe.ps1
;   2) Export terms: .\.venv\Scripts\python.exe scripts\export_terms_license.py
;   3) Install Inno Setup 6: https://jrsoftware.org/isinfo.php
;   4) Compile this script (or scripts\build_installer.ps1)
;
; Output: installer\Output\CloneUp-Setup.exe

#define MyAppName "CloneUp"
#define MyAppVersion "0.1.10"
#define MyAppPublisher "CloneUp"
#define MyAppURL "https://github.com/seongbin45/CloneUp"
#define MyAppExeName "CloneUp.exe"
; Multi-size icon (16–256) used by Setup wizard, shortcuts, Control Panel
#define MyAppIcoName "CloneUp.ico"

[Setup]
AppId={{A7C1E0B2-4D5F-4A8E-9C3B-1F2E3D4C5B6A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 이용약관 (desin/provision → scripts/export_terms_license.py)
LicenseFile=license\CloneUp_Terms_ko.txt
; Setup wizard icon
SetupIconFile=..\assets\icons\{#MyAppIcoName}
; Control Panel / Apps & Features uninstall entry icon
UninstallDisplayIcon={app}\{#MyAppIcoName}
UninstallDisplayName={#MyAppName}
; Version resources shown in file properties / Add-Remove Programs
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} — GitHub helper for beginners
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=Copyright 2026 최성빈
OutputDir=Output
OutputBaseFilename=CloneUp-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
; Autostart only — the update_manager.exe itself is ALWAYS installed (see [Files]).
; Do NOT use checkedonce here: that flag unchecks the task on upgrade when a
; previous version is found, which left many PCs without the updater after
; updating from builds that never offered this task (or after one opt-out).
Name: "autoupdatemanager"; Description: "로그인 시 자동 업데이트 관리자 실행"; GroupDescription: "업데이트:"; Flags: checked
; Path B Expiration OCR — bundles UB-Mannheim Tesseract setup (runs with its own UAC)
Name: "tesseractocr"; Description: "Tesseract OCR 설치 (키 만료일 화면 인식용)"; GroupDescription: "OCR:"; Flags: checkedonce

[Files]
; PyInstaller onedir output
Source: "..\dist\CloneUp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Plain VERSION next to exe (update_manager); also copied by build_exe.ps1 into dist
Source: "..\VERSION"; DestDir: "{app}"; Flags: ignoreversion
; App icon next to exe — Control Panel + Start Menu use this path (all sizes in .ico)
Source: "..\assets\icons\{#MyAppIcoName}"; DestDir: "{app}"; Flags: ignoreversion
; Independent update manager — ALWAYS install (not gated on the autostart task).
; Autostart (HKCU Run) remains optional via Tasks: autoupdatemanager below.
; Separate folder so zip onedir updates never overwrite the manager.
Source: "..\dist\CloneUp_update_manager.exe"; DestDir: "{localappdata}\CloneUp\UpdateManager"; Flags: ignoreversion
; Per-PC diagnosis script (also copied by build_exe.ps1 into dist\CloneUp\scripts)
Source: "..\scripts\diagnose_update_manager.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
; Individual PNG sizes (optional consumers / shell thumbnails if needed)
Source: "..\assets\icons\icon-16.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-24.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-32.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-48.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-64.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-128.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-256.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-512.png"; DestDir: "{app}\icons"; Flags: ignoreversion
; Legal: terms (also LicenseFile above), Apache LICENSE, OSS notices
Source: "license\CloneUp_Terms_ko.txt"; DestDir: "{app}\legal"; Flags: ignoreversion
Source: "..\legal\CloneUp_OpenSourceNotices_ko.txt"; DestDir: "{app}\legal"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
; Tesseract OCR installer (downloaded by scripts\fetch_tesseract_redist.ps1)
Source: "redist\tesseract-ocr-w64-setup-5.4.0.20240606.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall; Tasks: tesseractocr

[Icons]
; Start Menu — explicit multi-size .ico so shell picks 16/32/48 correctly
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcoName}"; IconIndex: 0
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcoName}"; IconIndex: 0; Tasks: desktopicon

[Registry]
; Silent background updater — separate from CloneUpTray (--tray)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "CloneUpUpdateManager"; ValueData: """{localappdata}\CloneUp\UpdateManager\CloneUp_update_manager.exe"""; Flags: uninsdeletevalue; Tasks: autoupdatemanager

[Run]
; Tesseract — own UAC elevation; silent-ish English UI (UB-Mannheim Inno-based)
Filename: "{tmp}\tesseract-ocr-w64-setup-5.4.0.20240606.exe"; Parameters: "/S"; StatusMsg: "Tesseract OCR 설치 중…"; Flags: waituntilterminated; Tasks: tesseractocr
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
; Start update manager once after install (also registered for logon)
Filename: "{localappdata}\CloneUp\UpdateManager\CloneUp_update_manager.exe"; Description: "자동 업데이트 관리자 시작"; Flags: nowait postinstall skipifsilent unchecked; Tasks: autoupdatemanager

; Note: Git is NOT bundled. First launch uses DG1/DG2 bootstrap
; (download official installer / winget) if git is missing.
; Auto-update uses GitHub zip (CloneUp-win64.zip) + file copy — never runs Setup GUI.
; Tesseract setup is bundled under installer\redist\ and run when task is checked.
; Windows built-in OCR (Windows.Media.Ocr) needs no extra installer.
