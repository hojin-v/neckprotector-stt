#ifndef RuntimeDir
  #define RuntimeDir "..\dist\Sori"
#endif
#ifndef ReleaseDir
  #define ReleaseDir "..\dist"
#endif

[Setup]
AppId={{DF8F76D4-0884-43F6-A63E-BE681523F049}
AppName=Sori
AppVersion=0.2.0
AppPublisher=Sori
DefaultDirName={localappdata}\Programs\Sori
DefaultGroupName=Sori
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#ReleaseDir}
OutputBaseFilename=Sori-Setup-0.2.0
SetupIconFile={#RuntimeDir}\_internal\sori\assets\sori.ico
UninstallDisplayIcon={app}\Sori.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
UninstallDisplayName=Sori

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[CustomMessages]
english.StartAtLogin=Start Sori when I sign in to Windows
korean.StartAtLogin=Windows 로그인 시 Sori 자동 실행

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "{cm:StartAtLogin}"; Flags: unchecked

[Files]
Source: "{#RuntimeDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Sori"; Filename: "{app}\Sori.exe"; AppUserModelID: "Sori.Dictation"
Name: "{group}\Sori Records and Settings"; Filename: "{app}\Sori.exe"; Parameters: "--dashboard"; AppUserModelID: "Sori.Dictation"
Name: "{autodesktop}\Sori"; Filename: "{app}\Sori.exe"; Tasks: desktopicon; AppUserModelID: "Sori.Dictation"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Sori"; ValueData: """{app}\Sori.exe"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Sori.exe"; Description: "Launch Sori"; Flags: nowait postinstall skipifsilent
