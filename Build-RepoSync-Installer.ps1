<#
RepoSync distribution builder for Windows 11 / PowerShell 7.
Creates one redistributable RepoSync_Setup_v0.2.4.exe, containing GUI + agent CLI.
No RepoSync profiles are changed, no folder sync performed, no existing app overwritten.
Requires Python 3.12 (py -3.12), Internet for isolated PyInstaller install,
and Inno Setup 6/7 (ISCC.exe) installed once on the BUILD PC.
#>
[CmdletBinding()]
param(
    [switch]$UseExistingExe,
    [string]$IsccPath
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$root = $PSScriptRoot
$source = Join-Path $root 'source'
$stage = Join-Path $root 'stage'
$build = Join-Path $root '.build'
$venv = Join-Path $build '.venv'
$dist = Join-Path $build 'pyinstaller-dist'
$work = Join-Path $build 'pyinstaller-work'
$spec = Join-Path $build 'pyinstaller-spec'
$license = Join-Path $source 'LICENSE'
$iconIco = Join-Path $source 'assets\RepoSync.ico'
$iconPng = Join-Path $source 'assets\RepoSync.png'
$expectedSetup = Join-Path $root 'release\RepoSync_Setup_v0.2.4.exe'

foreach ($name in @('reposync.py','reposync_gui.py','README.md','LICENSE','assets/RepoSync.ico','assets/RepoSync.png','ui/index.html','ui/RepoSync.png','ui/RepoSync.ico','MANUAL.md','skills/reposync/SKILL.md','skills/reposync/references/CLI_REFERENCE.md')) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $name) -PathType Leaf)) {
        throw "Incomplete source distribution: missing $name"
    }
}
New-Item -ItemType Directory -Path $build, $stage, $dist, $work, $spec -Force | Out-Null

$probe = & py -3.12 -c 'import sys; assert sys.version_info[:2] == (3, 12); print(sys.base_prefix)' 2>&1
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 is required on the BUILD machine. $probe" }
$pythonHome = ([string]($probe | Select-Object -Last 1)).Trim()
$pythonLicense = Join-Path $pythonHome 'LICENSE.txt'
if (-not (Test-Path -LiteralPath $pythonLicense -PathType Leaf)) {
    $pythonLicense = Join-Path $pythonHome 'LICENSE'
}
if (-not (Test-Path -LiteralPath $pythonLicense -PathType Leaf)) {
    throw "Python license not found under $pythonHome. Review licensing before making redistributable binaries."
}

if ($UseExistingExe -and -not (Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) {
    throw 'Cannot use existing executables without a v0.2.4 build environment/license inventory.'
}
if (-not $UseExistingExe) {
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        Write-Host 'Creating isolated build environment...' -ForegroundColor Cyan
        & py -3.12 -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed.' }
    }
    Write-Host 'Installing PyInstaller into isolated build environment...' -ForegroundColor Cyan
    & $venvPython -m pip install --disable-pip-version-check 'pyinstaller==6.22.3' 'pywebview==6.2.1'
    if ($LASTEXITCODE -ne 0) { throw 'Windows GUI dependency installation failed.' }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency consistency check failed.' }

    $entry = Join-Path $build 'repo_gui_entry.py'
    @'
from reposync_gui import run_gui
if __name__ == '__main__':
    run_gui()
'@ | Set-Content -LiteralPath $entry -Encoding utf8

    Write-Host 'Building GUI (RepoSync.exe)...' -ForegroundColor Cyan
    & $venvPython -m PyInstaller --noconfirm --clean --onefile --windowed `
        --name RepoSync --paths $source --distpath $dist `
        --icon $iconIco --add-data "$(Join-Path $source 'ui');ui" `
        --hidden-import clr --hidden-import webview.platforms.edgechromium --collect-all webview `
        --workpath (Join-Path $work 'gui') --specpath $spec $entry
    if ($LASTEXITCODE -ne 0) { throw 'GUI executable build failed.' }

    Write-Host 'Building agent CLI (RepoSyncCLI.exe)...' -ForegroundColor Cyan
    & $venvPython -m PyInstaller --noconfirm --clean --onefile --console `
        --name RepoSyncCLI --paths $source --distpath $dist `
        --icon $iconIco `
        --workpath (Join-Path $work 'cli') --specpath $spec `
        (Join-Path $source 'reposync.py')
    if ($LASTEXITCODE -ne 0) { throw 'CLI executable build failed.' }
} else {
    Write-Host 'Using already-built executables. Ensure both are FROM v0.2.4; never reuse old v0.1.2 binaries.' -ForegroundColor Cyan
}

$gui = Join-Path $dist 'RepoSync.exe'
$cli = Join-Path $dist 'RepoSyncCLI.exe'
foreach ($file in @($gui,$cli)) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Expected executable not found: $file" }
}

$oldHome = $env:REPOSYNC_HOME
$smokeHome = Join-Path $build 'test-empty-config'
try {
    $env:REPOSYNC_HOME = $smokeHome
    Write-Host 'Read-only smoke test of packaged agent CLI...' -ForegroundColor Cyan
    & $cli --version
    if ($LASTEXITCODE -ne 0) { throw 'Compiled CLI --version smoke test failed.' }
    & $cli list --json
    if ($LASTEXITCODE -ne 0) { throw 'Compiled CLI list --json smoke test failed.' }
    if ((& $cli --version).Trim() -ne '0.2.4') { throw 'Wrong compiled CLI version; refuse stale binary.' }
} finally {
    if ($null -eq $oldHome) { Remove-Item Env:REPOSYNC_HOME -ErrorAction SilentlyContinue }
    else { $env:REPOSYNC_HOME = $oldHome }
}

Copy-Item -LiteralPath $gui -Destination (Join-Path $stage 'RepoSync.exe') -Force
Copy-Item -LiteralPath $cli -Destination (Join-Path $stage 'RepoSyncCLI.exe') -Force
Copy-Item -LiteralPath $license -Destination (Join-Path $stage 'LICENSE.txt') -Force
Copy-Item -LiteralPath (Join-Path $source 'README.md') -Destination (Join-Path $stage 'README.md') -Force
Copy-Item -LiteralPath (Join-Path $source 'MANUAL.md') -Destination (Join-Path $stage 'MANUAL.md') -Force
Copy-Item -LiteralPath (Join-Path $source 'skills') -Destination (Join-Path $stage 'skills') -Recurse -Force
Copy-Item -LiteralPath $pythonLicense -Destination (Join-Path $stage 'PYTHON-LICENSE.txt') -Force
# Include third-party license texts from installed wheel metadata before distribution.
$licenses = Join-Path $stage 'licenses'
New-Item -ItemType Directory -Path $licenses -Force | Out-Null
$licenseAudit = Join-Path $root 'scripts\audit_build_licenses.py'
& (Join-Path $venv 'Scripts\python.exe') $licenseAudit $licenses
if ($LASTEXITCODE -ne 0) { throw 'Third-party licensing audit failed; no installer produced.' }
if (-not (Test-Path -LiteralPath (Join-Path $stage 'reposync.cmd') -PathType Leaf)) { throw 'Agent CLI wrapper missing.' }

if (-not $IsccPath) {
    $pf86 = [Environment]::GetFolderPath('ProgramFilesX86')
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 7\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 7\ISCC.exe'),
        (Join-Path $pf86 'Inno Setup 7\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
        (Join-Path $pf86 'Inno Setup 6\ISCC.exe')
    )
    $found = @($candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
    if ($found.Count -gt 0) { $IsccPath = $found[0] }
    else {
        $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($null -ne $cmd) { $IsccPath = $cmd.Source }
    }
}
if (-not $IsccPath -or -not (Test-Path -LiteralPath $IsccPath -PathType Leaf)) {
    throw 'Install Inno Setup 7 once with: winget install --id JRSoftware.InnoSetup.7 -e -s winget -i ; then rerun. Build inputs are ready.'
}

Write-Host "Compiling distributable installer with $IsccPath ..." -ForegroundColor Cyan
& $IsccPath (Join-Path $root 'RepoSync-Setup.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compiler failed.' }
if (-not (Test-Path -LiteralPath $expectedSetup -PathType Leaf)) {
    throw "Installer was not found at expected path: $expectedSetup"
}
$hash = (Get-FileHash -LiteralPath $expectedSetup -Algorithm SHA256).Hash
Write-Host "`nBUILD SUCCESS — DISTRIBUTABLE WINDOWS INSTALLER" -ForegroundColor Green
Write-Host "Installer: $expectedSetup"
Write-Host "SHA256:    $hash"
Write-Host 'Contains GUI + CLI, Start Menu shortcut, optional desktop shortcut and optional user PATH.'
Write-Host 'No synchronization was run. Only distribute after a clean Windows install/uninstall smoke test.'
