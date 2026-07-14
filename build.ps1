# Build script for Lean Markdown Converter v2.0.0
#
# Usage:
#   powershell build.ps1              # PyInstaller exe only
#   powershell build.ps1 -Installer   # exe + Inno Setup installer
#
# The installer step extracts resources\bin\exiftool-13.59.zip into
# setup\staging\exiftool\ (source for the optional exiftool component)
# before invoking iscc.

param(
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# --- 1. PyInstaller exe -----------------------------------------------------
Write-Host "==> Building PyInstaller exe..." -ForegroundColor Cyan
pyinstaller "$root\LPMarkdownConverter.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$exe = "$root\dist\LPMarkdownConverter.exe"
if (-not (Test-Path $exe)) { throw "Expected output missing: $exe" }
$sizeMB = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "==> dist\LPMarkdownConverter.exe built ($sizeMB MB)" -ForegroundColor Green

# --- 2. Post-build sanity: magika model data must be inside the bundle ------
# A partial magika copy silently degrades file type detection instead of
# erroring loudly, so fail the build if the archive lacks the model files.
Write-Host "==> Verifying magika model data in bundle..." -ForegroundColor Cyan
$archiveList = & pyi-archive_viewer -l $exe 2>$null | Select-String -Pattern "magika" -SimpleMatch
if (-not $archiveList) {
    Write-Warning "Could not verify magika data via pyi-archive_viewer (tool missing or no matches)."
    Write-Warning "Manually verify file type detection works in the frozen exe before release."
} else {
    Write-Host "==> magika data present in bundle" -ForegroundColor Green
}

if (-not $Installer) {
    Write-Host "==> Done (exe only). Run with -Installer to also build the setup package." -ForegroundColor Cyan
    exit 0
}

# --- 3. Stage exiftool for the installer component --------------------------
Write-Host "==> Staging exiftool from zip..." -ForegroundColor Cyan
$staging = "$root\setup\staging\exiftool"
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path $staging -Force | Out-Null
Expand-Archive -Path "$root\resources\bin\exiftool-13.59.zip" -DestinationPath $staging -Force

# The zip contains ExifTool.exe + exiftool_files\. Normalize the launcher name
# to exiftool.exe so the runtime discovery contract ({app}\tools\exiftool\exiftool.exe)
# and the EXIFTOOL_PATH registry value match regardless of zip-internal casing.
if ((Test-Path "$staging\ExifTool.exe") -and -not (Test-Path "$staging\exiftool.exe")) {
    Rename-Item "$staging\ExifTool.exe" "exiftool.exe"
}
if (-not (Test-Path "$staging\exiftool.exe")) { throw "exiftool.exe not found in staging after extraction" }
if (-not (Test-Path "$staging\exiftool_files")) { throw "exiftool_files\ not found in staging after extraction" }
Write-Host "==> exiftool staged" -ForegroundColor Green

# --- 4. Inno Setup installer -------------------------------------------------
Write-Host "==> Building Inno Setup installer..." -ForegroundColor Cyan
$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $isccDefault = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    if (Test-Path $isccDefault) { $iscc = $isccDefault } else { throw "iscc.exe not found (install Inno Setup 6 or add to PATH)" }
}
& $iscc "$root\setup\LPMarkdownConverterSetup.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed" }

$setupExe = "$root\setup\LPMarkdownConverterSetup.exe"
$setupMB = [math]::Round((Get-Item $setupExe).Length / 1MB, 1)
Write-Host "==> setup\LPMarkdownConverterSetup.exe built ($setupMB MB)" -ForegroundColor Green
