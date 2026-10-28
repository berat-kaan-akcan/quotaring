; Inno Setup 6 script. Build after PyInstaller: iscc packaging\windows\installer.iss
; Per-user install (no admin rights), Start menu shortcut, optional start at login.
#define AppName "AI Usage Widget"
#define AppVersion "0.1.0"

[Setup]
AppId={{2002DBE6-F373-4EC2-87A6-AFA57A4849D9}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\AIUsageWidget
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\out
OutputBaseFilename=ai-usage-widget-{#AppVersion}-setup
SetupIconFile=..\icons\ai-usage-widget.ico
UninstallDisplayIcon={app}\ai-usage-widget.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\..\dist\ai-usage-widget\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ai-usage-widget.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Tasks]
Name: "autostart"; Description: "Start at login"; Flags: unchecked

[Registry]
; Same value the in-app "Start at login" setting writes, so either place can turn it off.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "AIUsageWidget"; ValueData: """{app}\ai-usage-widget.exe"""; Tasks: autostart; \
  Flags: uninsdeletevalue

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v AIUsageWidget /f"; \
  Flags: runhidden; RunOnceId: "RemoveAutostart"

[Run]
Filename: "{app}\ai-usage-widget.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
