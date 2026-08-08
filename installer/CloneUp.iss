; Inno Setup script for CloneUp (DG3)
; Prerequisites:
;   1) Build exe:  powershell -File scripts\build_exe.ps1
;   2) Export terms: .\.venv\Scripts\python.exe scripts\export_terms_license.py
;   3) Install Inno Setup 6: https://jrsoftware.org/isinfo.php
;   4) Compile this script (or scripts\build_installer.ps1)
;
; Output: installer\Output\CloneUp-Setup.exe

#define MyAppName "CloneUp"
#define MyAppVersion "0.1.6"
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
VersionInfoCopyright=Copyright (C) 2026 {#MyAppPublisher}
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

[Files]
; PyInstaller onedir output
Source: "..\dist\CloneUp\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; App icon next to exe — Control Panel + Start Menu use this path (all sizes in .ico)
Source: "..\assets\icons\{#MyAppIcoName}"; DestDir: "{app}"; Flags: ignoreversion
; Individual PNG sizes (optional consumers / shell thumbnails if needed)
Source: "..\assets\icons\icon-16.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-24.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-32.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-48.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-64.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-128.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-256.png"; DestDir: "{app}\icons"; Flags: ignoreversion
Source: "..\assets\icons\icon-512.png"; DestDir: "{app}\icons"; Flags: ignoreversion
; Terms copy installed with the app
Source: "license\CloneUp_Terms_ko.txt"; DestDir: "{app}\legal"; Flags: ignoreversion

[Icons]
; Start Menu — explicit multi-size .ico so shell picks 16/32/48 correctly
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcoName}"; IconIndex: 0
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppIcoName}"; IconIndex: 0; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; Note: Git is NOT bundled. First launch uses DG1/DG2 bootstrap
; (download official installer / winget) if git is missing.
