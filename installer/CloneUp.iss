; Inno Setup script for CloneUp (DG3)
; Prerequisites:
;   1) Build exe:  powershell -File scripts\build_exe.ps1
;   2) Install Inno Setup 6: https://jrsoftware.org/isinfo.php
;   3) Compile this script in Inno Setup Compiler
;
; Output: installer\Output\CloneUp-Setup.exe

#define MyAppName "CloneUp"
#define MyAppVersion "0.1.2"
#define MyAppPublisher "CloneUp"
#define MyAppURL "https://github.com/seongbin45/CloneUp"
#define MyAppExeName "CloneUp.exe"

[Setup]
AppId={{A7C1E0B2-4D5F-4A8E-9C3B-1F2E3D4C5B6A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=CloneUp-Setup
SetupIconFile=..\assets\icons\CloneUp.ico
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

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; Note: Git is NOT bundled. First launch uses DG1/DG2 bootstrap
; (download official installer / winget) if git is missing.
