; Inno Setup recipe: one setup file that installs Council Archive for the current user (no administrator rights).
; Build after PyInstaller:  iscc /DAppVersion=1.0.0 packaging\installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C1C5E-6C0B-4B0E-9C56-3B0C3E3C7A11}
AppName=Council Archive
AppVersion={#AppVersion}
AppPublisher=stillawake17
AppPublisherURL=https://github.com/stillawake17/council-archive
DefaultDirName={localappdata}\Programs\Council Archive
DefaultGroupName=Council Archive
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Council-Archive-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Council Archive.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Files]
Source: "..\dist\Council Archive\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[InstallDelete]
; Remove the previous version's program files so nothing stale is left behind. Archives and settings are elsewhere.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\Council Archive"; Filename: "{app}\Council Archive.exe"
Name: "{group}\Council Archive guide"; Filename: "{app}\_internal\START-HERE.md"
Name: "{userdesktop}\Council Archive"; Filename: "{app}\Council Archive.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Council Archive.exe"; Description: "Open Council Archive now"; Flags: nowait postinstall skipifsilent

[Messages]
FinishedLabel=Council Archive is installed. Your papers will be kept in Documents\Council Archive. Uninstalling the program never deletes them.
