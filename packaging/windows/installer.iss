; Inno Setup 6 script. Build after PyInstaller: iscc packaging\windows\installer.iss
; Per-user install (no admin rights), Start menu shortcut, optional start at login.
#define AppName "QuotaRing"
; build_windows.ps1 passes /DAppVersion from quotaring.__version__
#ifndef AppVersion
#define AppVersion "0.1.0"
#endif

[Setup]
AppId={{2002DBE6-F373-4EC2-87A6-AFA57A4849D9}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Berat Kaan Akcan
AppPublisherURL=https://github.com/berat-kaan-akcan/quotaring
DefaultDirName={localappdata}\Programs\QuotaRing
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\out
OutputBaseFilename=quotaring-{#AppVersion}-setup
SetupIconFile=..\icons\quotaring.ico
UninstallDisplayIcon={app}\quotaring.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\..\dist\quotaring\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\quotaring.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"

[Tasks]
Name: "autostart"; Description: "Start at login"; Flags: unchecked

[Registry]
; Same value the in-app "Start at login" setting writes, so either place can turn it off.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "QuotaRing"; ValueData: """{app}\quotaring.exe"""; Tasks: autostart; \
  Flags: uninsdeletevalue

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c reg delete HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v QuotaRing /f"; \
  Flags: runhidden; RunOnceId: "RemoveAutostart"

[Run]
Filename: "{app}\quotaring.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
; The in-app updater runs setup with /VERYSILENT /RELAUNCH=1: start the new version afterwards.
Filename: "{app}\quotaring.exe"; Flags: nowait; Check: Relaunch

[Code]
function Relaunch: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:relaunch|0}') = '1');
end;
