; RepoSync v0.2.4 — per-user GUI and CLI installer.
; Compile from Windows with ISCC.exe after Build-RepoSync-Installer.ps1 stages binaries.
; Never executes a synchronization. Profiles in {localappdata}\RepoSync\profiles.json
; are user data: never included in [Files] and never removed by uninstall.
#define ProductVersion "0.2.4"

[Setup]
AppId={{4F7EBE67-96FD-4B58-A625-7E0904F73A26}
AppName=RepoSync
AppVersion={#ProductVersion}
AppVerName=RepoSync {#ProductVersion}
AppPublisher=RepoSync contributors
DefaultDirName={localappdata}\RepoSync
UsePreviousAppDir=no
DisableDirPage=yes
PrivilegesRequired=lowest
DefaultGroupName=RepoSync
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\bin\RepoSync.exe
OutputDir=release
OutputBaseFilename=RepoSync_Setup_v{#ProductVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=0.2.4.0
VersionInfoDescription=RepoSync Windows installer (GUI and agent CLI)
LicenseFile=stage\LICENSE.txt
SetupIconFile=source\assets\RepoSync.ico

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "addpath"; Description: "Add RepoSync command to my user PATH (recommended for agents)"; GroupDescription: "Command-line integration:"; Flags: checkedonce

[Files]
Source: "stage\RepoSync.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "stage\RepoSyncCLI.exe"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "stage\reposync.cmd"; DestDir: "{app}\bin"; Flags: ignoreversion
Source: "stage\LICENSE.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "stage\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "stage\MANUAL.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "stage\skills\*"; DestDir: "{app}\skills"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "stage\PYTHON-LICENSE.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "stage\licenses\*"; DestDir: "{app}\docs\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\RepoSync"; Filename: "{app}\bin\RepoSync.exe"
Name: "{group}\RepoSync Manual"; Filename: "{app}\docs\MANUAL.md"
Name: "{group}\RepoSync README"; Filename: "{app}\docs\README.md"
Name: "{autodesktop}\RepoSync"; Filename: "{app}\bin\RepoSync.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\bin\RepoSync.exe"; Description: "Launch RepoSync"; Flags: nowait postinstall skipifsilent

[Code]
const
  EnvironmentKey = 'Environment';
  AppRegistryKey = 'Software\RepoSync';

function EntryInPath(const WholePath, Desired: string): Boolean;
var
  Tokens: TArrayOfString;
  N: Integer;
  Part: string;
begin
  Result := False;
  Tokens := StringSplit(WholePath, [';'], stExcludeEmpty);
  for N := 0 to GetArrayLength(Tokens) - 1 do
  begin
    Part := Trim(Tokens[N]);
    if CompareText(Part, Desired) = 0 then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

procedure AddRepoSyncToPath();
var
  OldPath, NewPath, BinPath: string;
begin
  if not WizardIsTaskSelected('addpath') then Exit;
  BinPath := ExpandConstant('{app}\bin');
  if not RegQueryStringValue(HKCU, EnvironmentKey, 'Path', OldPath) then OldPath := '';
  if EntryInPath(OldPath, BinPath) then Exit;
  NewPath := OldPath;
  if (NewPath <> '') and (Copy(NewPath, Length(NewPath), 1) <> ';') then
    NewPath := NewPath + ';';
  NewPath := NewPath + BinPath;
  if not RegWriteExpandStringValue(HKCU, EnvironmentKey, 'Path', NewPath) then
    RaiseException('Could not update user PATH. You can still run RepoSyncCLI.exe by full path.');
  RegWriteStringValue(HKCU, AppRegistryKey, 'PathAddedByInstaller', BinPath);
end;

procedure RemoveRepoSyncFromPath();
var
  BinPath, AddedPath, OldPath, NewPath, Part: string;
  Tokens: TArrayOfString;
  I: Integer;
begin
  if not RegQueryStringValue(HKCU, AppRegistryKey, 'PathAddedByInstaller', AddedPath) then Exit;
  BinPath := ExpandConstant('{app}\bin');
  if CompareText(AddedPath, BinPath) <> 0 then Exit;
  if not RegQueryStringValue(HKCU, EnvironmentKey, 'Path', OldPath) then Exit;
  Tokens := StringSplit(OldPath, [';'], stExcludeEmpty);
  NewPath := '';
  for I := 0 to GetArrayLength(Tokens) - 1 do
  begin
    Part := Trim(Tokens[I]);
    if (Part <> '') and (CompareText(Part, BinPath) <> 0) then
    begin
      if NewPath <> '' then NewPath := NewPath + ';';
      NewPath := NewPath + Tokens[I];
    end;
  end;
  RegWriteExpandStringValue(HKCU, EnvironmentKey, 'Path', NewPath);
  RegDeleteValue(HKCU, AppRegistryKey, 'PathAddedByInstaller');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then AddRepoSyncToPath();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then RemoveRepoSyncFromPath();
end;
