; Updated Inno Setup script for LP Markdown Converter
; Places only the standalone EXE and License in Program Files, creates Start Menu and optional desktop shortcuts.

#define MyAppName "Lean Markdown Converter"
#define MyAppVersion "1.0.6"
#define MyAppPublisher "LeanProductivity"
#define MyAppURL "[https://sascha-kasper.com](https://sascha-kasper.com)"
#define MyAppExeName "LPMarkdownConverter.exe"

[Setup]
; Unique application identifier (generate a new GUID if needed)
AppId={{478717CC-FB03-4C52-93E2-4AD613B61F7A}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
;AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Install location and privileges
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
LicenseFile=D:\GitProjects\lean-markdown-converter\setup\LICENSE.txt

; Installer output settings
OutputDir=D:\GitProjects\lean-markdown-converter\setup
OutputBaseFilename=LPMarkdownConverterSetup
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "D:\GitProjects\lean-markdown-converter\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "D:\GitProjects\lean-markdown-converter\resources\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "D:\GitProjects\lean-markdown-converter\setup\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Launch application after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
