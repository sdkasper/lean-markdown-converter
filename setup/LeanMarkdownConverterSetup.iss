; Inno Setup script for Lean Markdown Converter v2.0.0
;
; Component model (v2.0.0): the PyInstaller exe contains NO external binaries.
; ffmpeg/ffprobe (audio) and exiftool (image EXIF) ship as optional installer
; components installed to {app}\tools\ and discovered at runtime by
; core/binaries.py (PATH > env var > {app}\tools > dev fallback).
;
; BUILD PREREQUISITE: run build.ps1 first. It builds dist\LPMarkdownConverter.exe
; and extracts resources\bin\exiftool-13.59.zip to setup\staging\exiftool\
; (the [Files] exiftool source below). Paths are relative to this .iss file.

#define MyAppName "Lean Markdown Converter"
#define MyAppVersion "2.0.1"
#define MyAppPublisher "LeanProductivity"
#define MyAppURL "https://sascha-kasper.com"
#define MyAppExeName "LPMarkdownConverter.exe"

[Setup]
AppId={{478717CC-FB03-4C52-93E2-4AD613B61F7A}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
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
LicenseFile=LICENSE.txt

; Installer output settings
OutputDir=.
OutputBaseFilename=LeanMarkdownConverterSetup
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Full installation (recommended)"
Name: "minimal"; Description: "Minimal installation (documents only - no audio or image metadata support)"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "core"; Description: "Lean Markdown Converter (required)"; Types: full minimal custom; Flags: fixed
Name: "audio"; Description: "Audio conversion support (MP3/M4A/WAV) - installs FFmpeg and ffprobe (~226 MB)"; Types: full custom; Flags: checkablealone
Name: "exiftool"; Description: "Image metadata support (EXIF mode) - installs ExifTool (~40 MB)"; Types: full custom; Flags: checkablealone

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Orphaned payloads from v1.0.8 and earlier, which installed resources\* into {app}
; (v2.0.0 ships binaries under {app}\tools\ as optional components instead).
Type: filesandordirs; Name: "{app}\bin"
Type: files; Name: "{app}\logo.png"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\resources\LeanProductivity.ico"; DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\resources\bin\ffmpeg.exe"; DestDir: "{app}\tools"; Flags: ignoreversion; Components: audio
Source: "..\resources\bin\ffprobe.exe"; DestDir: "{app}\tools"; Flags: ignoreversion; Components: audio
Source: "staging\exiftool\*"; DestDir: "{app}\tools\exiftool"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: exiftool

; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Registry]
; Backup discovery path for exiftool. Not reliable within the install session
; (environment broadcast timing), which is why core/binaries.py also checks
; {app}\tools\exiftool\ directly as a first-class fallback.
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "EXIFTOOL_PATH"; \
    ValueData: "{app}\tools\exiftool\exiftool.exe"; Flags: preservestringtype uninsdeletevalue; Components: exiftool

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Launch application after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
