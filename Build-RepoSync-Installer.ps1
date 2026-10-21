<#
RepoSync distribution builder for Windows 11 / PowerShell 7.
Creates one redistributable RepoSync_Setup_v0.2.7.exe, containing GUI + agent CLI.
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
# Exit code of the last destructive step, set by Invoke-WithReadOnlyRetry.
$script:reposyncStepExit = 0

function Find-ReadOnlyEntries {
    # Re-scan a tree and report every entry that still carries
    # FILE_ATTRIBUTE_READONLY, plus every entry that cannot be read at all
    # (an unreadable path is a failure to report, never a silent success).
    # Reparse points (junctions, symlinks) are never entered and never
    # reported: their target may live outside the build tree, and the mirror
    # engine itself refuses to traverse reparse points.
    param([Parameter(Mandatory)][string]$Path)
    $ro = [System.IO.FileAttributes]::ReadOnly
    $reparse = [System.IO.FileAttributes]::ReparsePoint
    $readOnly = New-Object System.Collections.Generic.List[string]
    $unreadable = New-Object System.Collections.Generic.List[string]
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($Path)
    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        try { $attrs = [System.IO.File]::GetAttributes($current) }
        catch { $unreadable.Add($current); continue }
        if (($attrs -band $reparse) -ne 0) { continue }
        if (($attrs -band $ro) -ne 0) { $readOnly.Add($current) }
        if (($attrs -band [System.IO.FileAttributes]::Directory) -eq 0) { continue }
        try {
            foreach ($child in [System.IO.Directory]::EnumerateFileSystemEntries($current)) {
                $stack.Push($child)
            }
        } catch {
            $unreadable.Add($current)
        }
    }
    return [pscustomobject]@{ ReadOnly = $readOnly; Unreadable = $unreadable }
}

function Clear-ReadOnlyAttributes {
    # Google Drive for desktop (DriveFS) marks DIRECTORIES read-only inside the
    # mirrored folders it manages, and re-applies the bit asynchronously. That
    # breaks PyInstaller, which removes its work tree with shutil.rmtree and
    # cannot delete a read-only directory. Clear the bit on our own build tree
    # immediately before each destructive step, and only on our own tree.
    #
    # Hardened rules (v0.2.7 kit):
    #  * only the kit's own build trees are swept; the source distribution is
    #    refused outright;
    #  * reparse points (junctions, symlinks) are never entered, so nothing
    #    outside the build tree can ever be touched;
    #  * unreadable paths are recorded instead of being silently skipped;
    #  * after the sweep the tree is re-scanned and anything still read-only
    #    aborts the build naming the offending path, instead of letting a
    #    later destructive step die with an unrelated WinError 5.
    param(
        [Parameter(Mandatory)][string]$Path,
        [int]$VerifyPasses = 3
    )
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not [string]::IsNullOrWhiteSpace($script:sourceRootFull)) {
        $sourcePrefix = $script:sourceRootFull.TrimEnd('\','/') + [System.IO.Path]::DirectorySeparatorChar
        if ($full.Equals($script:sourceRootFull, [System.StringComparison]::OrdinalIgnoreCase) -or
            $full.StartsWith($sourcePrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to clear read-only attributes inside the source distribution: $full"
        }
    }
    $ro = [System.IO.FileAttributes]::ReadOnly
    $reparse = [System.IO.FileAttributes]::ReparsePoint
    $cleared = 0
    $failed = New-Object System.Collections.Generic.List[string]
    $stack = New-Object System.Collections.Generic.Stack[string]
    $stack.Push($Path)
    while ($stack.Count -gt 0) {
        $current = $stack.Pop()
        try { $attrs = [System.IO.File]::GetAttributes($current) }
        catch { $failed.Add("$current (cannot read attributes: $($_.Exception.Message))"); continue }
        if (($attrs -band $reparse) -ne 0) { continue }
        if (($attrs -band $ro) -ne 0) {
            try {
                [System.IO.File]::SetAttributes($current, ($attrs -band (-bnot $ro)))
                $cleared++
            } catch {
                $failed.Add("$current (cannot clear: $($_.Exception.Message))")
            }
        }
        if (($attrs -band [System.IO.FileAttributes]::Directory) -eq 0) { continue }
        try {
            foreach ($child in [System.IO.Directory]::EnumerateFileSystemEntries($current)) {
                $stack.Push($child)
            }
        } catch {
            $failed.Add("$current (cannot enumerate: $($_.Exception.Message))")
        }
    }
    if ($cleared -gt 0) { Write-Host "Cleared read-only attribute on $cleared build-tree item(s) under $Path." -ForegroundColor DarkGray }
    if ($failed.Count -gt 0) { Write-Warning "$($failed.Count) item(s) under $Path could not be swept: $($failed[0])" }
    # Re-scan the tree: DriveFS can re-apply the bit while we sweep, so verify
    # what is left before a destructive step runs.
    $remaining = $null
    for ($pass = 1; $pass -le $VerifyPasses; $pass++) {
        $remaining = Find-ReadOnlyEntries -Path $Path
        if ($remaining.ReadOnly.Count -eq 0 -and $remaining.Unreadable.Count -eq 0) { break }
        if ($pass -lt $VerifyPasses) { Start-Sleep -Milliseconds 750 }
    }
    if ($remaining.ReadOnly.Count -gt 0 -or $remaining.Unreadable.Count -gt 0) {
        $first = if ($remaining.ReadOnly.Count -gt 0) { $remaining.ReadOnly[0] } else { $remaining.Unreadable[0] }
        $detail = "still read-only: $($remaining.ReadOnly.Count); unreadable: $($remaining.Unreadable.Count)"
        throw ("Could not make '$Path' writable ($detail). First offending path: '$first'. " +
               "Google Drive for Desktop (DriveFS) marks directories inside mirrored folders read-only and re-applies the bit asynchronously. " +
               "Move this build kit out of the Google Drive mirror (for example copy it to C:\build\RepoSync) and rebuild, " +
               "or clear the bit manually on that path and rerun. " +
               "Aborting before the destructive build step so it cannot fail later with an unrelated WinError 5.")
    }
}

function Invoke-WithReadOnlyRetry {
    # Run one destructive step. If it fails because a read-only item reappeared
    # (DriveFS re-applies the bit asynchronously between the clear and the
    # delete), clear the bit again and retry: one clear plus up to $MaxRetries
    # extra attempts. Used for the GUI build, the agent CLI build and the
    # Inno Setup compile.
    param(
        [Parameter(Mandatory)][string[]]$Path,
        [Parameter(Mandatory)][scriptblock]$ScriptBlock,
        [string]$Description = 'build step',
        [int]$MaxRetries = 2
    )
    $trees = @($Path)
    foreach ($tree in $trees) { Clear-ReadOnlyAttributes -Path $tree }
    $attempt = 0
    while ($true) {
        $attempt++
        try {
            $script:reposyncStepExit = 0
            & $ScriptBlock
            if ($script:reposyncStepExit -ne 0) { throw "exited with code $script:reposyncStepExit" }
            return
        } catch {
            $reason = $_.Exception.Message
            if ($attempt -gt $MaxRetries) { throw "$Description failed after $attempt attempt(s): $reason" }
            Write-Warning "$Description failed on attempt $attempt ($reason). Clearing read-only attributes and retrying..."
            Start-Sleep -Seconds 1
            foreach ($tree in $trees) { Clear-ReadOnlyAttributes -Path $tree }
        }
    }
}

function Clear-PyInstallerCacheReadOnly {
    # PyInstaller --clean also wipes its own CACHE directory, which lives
    # OUTSIDE this kit (default %LOCALAPPDATA%\pyinstaller\Cache). If that
    # cache sits inside a mirrored folder it fails exactly like the kit's own
    # work tree. A missing cache directory is not an error.
    param([int]$MaxRetries = 2)
    $configDir = $env:PYINSTALLER_CONFIG_DIR
    if ([string]::IsNullOrWhiteSpace($configDir)) {
        $local = $env:LOCALAPPDATA
        if ([string]::IsNullOrWhiteSpace($local)) { $local = Join-Path $env:USERPROFILE 'AppData\Local' }
        $configDir = Join-Path $local 'pyinstaller'
    }
    $cache = Join-Path $configDir 'Cache'
    if (-not (Test-Path -LiteralPath $cache)) {
        Write-Host "PyInstaller cache directory not present, nothing to clear: $cache" -ForegroundColor DarkGray
        return
    }
    for ($attempt = 1; $attempt -le (1 + $MaxRetries); $attempt++) {
        try {
            Clear-ReadOnlyAttributes -Path $cache
            return
        } catch {
            if ($attempt -gt $MaxRetries) { throw }
            Write-Warning "PyInstaller cache not writable yet on attempt $attempt ($($_.Exception.Message)). Retrying."
            Start-Sleep -Seconds 1
        }
    }
}

$root = $PSScriptRoot
$source = Join-Path $root 'source'
$sourceRootFull = [System.IO.Path]::GetFullPath($source)
$stage = Join-Path $root 'stage'
$build = Join-Path $root '.build'
$venv = Join-Path $build '.venv'
$dist = Join-Path $build 'pyinstaller-dist'
$work = Join-Path $build 'pyinstaller-work'
$spec = Join-Path $build 'pyinstaller-spec'
$license = Join-Path $source 'LICENSE'
$iconIco = Join-Path $source 'assets\RepoSync.ico'
$iconPng = Join-Path $source 'assets\RepoSync.png'
$expectedSetup = Join-Path $root 'release\RepoSync_Setup_v0.2.7.exe'

foreach ($name in @('reposync.py','reposync_gui.py','reposync.cmd','native_resize.py','README.md','LICENSE','assets/RepoSync.ico','assets/RepoSync.png','ui/index.html','ui/RepoSync.png','ui/RepoSync.ico','MANUAL.md','skills/reposync/SKILL.md','skills/reposync/references/CLI_REFERENCE.md')) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $name) -PathType Leaf)) {
        throw "Incomplete source distribution: missing $name"
    }
}
New-Item -ItemType Directory -Path $build, $stage, $dist, $work, $spec -Force | Out-Null
# A Google Drive mirrored folder marks directories read-only and re-applies the
# bit asynchronously; PyInstaller deletes its work tree and fails on that.
Clear-ReadOnlyAttributes -Path $build
Clear-ReadOnlyAttributes -Path $stage
Clear-ReadOnlyAttributes -Path (Join-Path $root 'release')

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
    throw 'Cannot use existing executables without a v0.2.7 build environment/license inventory.'
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
    # Drive re-applies the read-only bit asynchronously, so clear again here and
    # retry the destructive step if it still trips over a read-only item.
    Clear-ReadOnlyAttributes -Path $work
    Clear-ReadOnlyAttributes -Path $dist
    Clear-PyInstallerCacheReadOnly
    Invoke-WithReadOnlyRetry -Path @($work, $dist) -Description 'GUI executable build' -ScriptBlock {
        & $venvPython -m PyInstaller --noconfirm --clean --onefile --windowed `
            --name RepoSync --paths $source --distpath $dist `
            --icon $iconIco --add-data "$(Join-Path $source 'ui');ui" `
            --hidden-import clr --hidden-import native_resize --hidden-import webview.platforms.edgechromium --collect-all webview `
            --workpath (Join-Path $work 'gui') --specpath $spec $entry
        $script:reposyncStepExit = $LASTEXITCODE
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller reported a non-zero exit code for the GUI build.' }
    }

    Write-Host 'Building agent CLI (RepoSyncCLI.exe)...' -ForegroundColor Cyan
    Clear-ReadOnlyAttributes -Path $work
    Clear-ReadOnlyAttributes -Path $dist
    Clear-PyInstallerCacheReadOnly
    Invoke-WithReadOnlyRetry -Path @($work, $dist) -Description 'agent CLI executable build' -ScriptBlock {
        & $venvPython -m PyInstaller --noconfirm --clean --onefile --console `
            --name RepoSyncCLI --paths $source --distpath $dist `
            --icon $iconIco `
            --workpath (Join-Path $work 'cli') --specpath $spec `
            (Join-Path $source 'reposync.py')
        $script:reposyncStepExit = $LASTEXITCODE
        if ($LASTEXITCODE -ne 0) { throw 'PyInstaller reported a non-zero exit code for the agent CLI build.' }
    }
} else {
    Write-Host 'Using already-built executables. Ensure both are FROM v0.2.7; never reuse old v0.1.2 binaries.' -ForegroundColor Cyan
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
    if ((& $cli --version).Trim() -ne '0.2.7') { throw 'Wrong compiled CLI version; refuse stale binary.' }
} finally {
    if ($null -eq $oldHome) { Remove-Item Env:REPOSYNC_HOME -ErrorAction SilentlyContinue }
    else { $env:REPOSYNC_HOME = $oldHome }
}

Clear-ReadOnlyAttributes -Path $stage
# The stage directory is pure build output. Purge it first so a re-run can never
# ship a stale artifact: copying a directory into an existing directory nests it
# (stage\skills\skills), and a renamed or dropped source file would otherwise
# survive in the installer.
try {
    Get-ChildItem -LiteralPath $stage -Force | ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
    }
} catch {
    throw "Could not purge the stage directory '$stage': $($_.Exception.Message)"
}
Copy-Item -LiteralPath $gui -Destination (Join-Path $stage 'RepoSync.exe') -Force
Copy-Item -LiteralPath $cli -Destination (Join-Path $stage 'RepoSyncCLI.exe') -Force
Copy-Item -LiteralPath $license -Destination (Join-Path $stage 'LICENSE.txt') -Force
Copy-Item -LiteralPath (Join-Path $source 'README.md') -Destination (Join-Path $stage 'README.md') -Force
Copy-Item -LiteralPath (Join-Path $source 'MANUAL.md') -Destination (Join-Path $stage 'MANUAL.md') -Force
# Copy the CONTENTS of skills\, not the folder: copying a directory into an
# existing directory produces a nested duplicate that the installer would ship.
$stageSkills = Join-Path $stage 'skills'
New-Item -ItemType Directory -Path $stageSkills -Force | Out-Null
Copy-Item -Path (Join-Path $source 'skills\*') -Destination $stageSkills -Recurse -Force
Copy-Item -LiteralPath $pythonLicense -Destination (Join-Path $stage 'PYTHON-LICENSE.txt') -Force
# The agent CLI wrapper ships from source so it can never drift from the CLI it
# wraps; the staged copy used to be a leftover that the build only checked for.
Copy-Item -LiteralPath (Join-Path $source 'reposync.cmd') -Destination (Join-Path $stage 'reposync.cmd') -Force
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
$releaseDir = Join-Path $root 'release'
Clear-ReadOnlyAttributes -Path $releaseDir
# This kit folder is the delivery unit: a stale installer left next to the new
# one ships a build WITHOUT the v0.2.7 read-only fix, which reads as "the fix
# did not work". Keep exactly one installer in release\: the expected one.
$expectedFull = [System.IO.Path]::GetFullPath($expectedSetup)
$staleInstallers = @(Get-ChildItem -LiteralPath $releaseDir -Filter 'RepoSync_Setup_*.exe' -File -ErrorAction SilentlyContinue |
    Where-Object { [System.IO.Path]::GetFullPath($_.FullName) -ne $expectedFull })
foreach ($stale in $staleInstallers) {
    try {
        Remove-Item -LiteralPath $stale.FullName -Force
        Write-Host "Removed stale installer: $($stale.Name)" -ForegroundColor DarkGray
    } catch {
        throw "Could not remove stale installer '$($stale.FullName)': $($_.Exception.Message). Delete it manually and rerun the build; shipping more than one installer risks delivering a build without the v0.2.7 read-only fix."
    }
}
Invoke-WithReadOnlyRetry -Path $releaseDir -Description 'Inno Setup compile' -ScriptBlock {
    & $IsccPath (Join-Path $root 'RepoSync-Setup.iss')
    $script:reposyncStepExit = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compiler reported a non-zero exit code.' }
}
if ($script:reposyncStepExit -ne 0) { throw 'Inno Setup compiler failed.' }
if (-not (Test-Path -LiteralPath $expectedSetup -PathType Leaf)) {
    throw "Installer was not found at expected path: $expectedSetup"
}
$hash = (Get-FileHash -LiteralPath $expectedSetup -Algorithm SHA256).Hash
Write-Host "`nBUILD SUCCESS — DISTRIBUTABLE WINDOWS INSTALLER" -ForegroundColor Green
Write-Host "Installer: $expectedSetup"
Write-Host "SHA256:    $hash"
Write-Host 'Contains GUI + CLI, Start Menu shortcut, optional desktop shortcut and optional user PATH.'
Write-Host 'No synchronization was run. Only distribute after a clean Windows install/uninstall smoke test.'
