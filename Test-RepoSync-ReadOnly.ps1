# Disposable Windows acceptance test for the v0.2.7 read-only-safe sync.
# Proves, against the COMPILED CLI only:
#   1. a stale read-only FILE in the destination is deleted,
#   2. a stale read-only DIRECTORY in the destination (with a read-only child) is removed,
#   3. a read-only SOURCE file is mirrored and the mirror copy stays read-only (fidelity),
#   4. a read-only destination file is updated when the source changes,
#   5. the SOURCE tree is never modified.
# Uses temporary folders only. Never touches real RepoSync profiles, mirrors or user data.
$ErrorActionPreference = 'Stop'
$cli = Join-Path $PSScriptRoot '.build\pyinstaller-dist\RepoSyncCLI.exe'
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) { throw "CLI missing: $cli; run the builder first." }

function Test-IsReadOnly([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    return (((Get-Item -LiteralPath $Path -Force).Attributes -band [System.IO.FileAttributes]::ReadOnly) -ne 0)
}
function Set-ReadOnly([string]$Path) {
    (Get-Item -LiteralPath $Path -Force).Attributes = (Get-Item -LiteralPath $Path -Force).Attributes -bor [System.IO.FileAttributes]::ReadOnly
}
function Get-TreeFingerprint([string]$Path) {
    $sb = [System.Text.StringBuilder]::new()
    foreach ($f in (Get-ChildItem -LiteralPath $Path -Recurse -Force -File | Sort-Object FullName)) {
        [void]$sb.Append($f.FullName.Substring($Path.Length)).Append('|').Append($f.Length).Append('|').Append($f.LastWriteTimeUtc.Ticks).Append("`n")
    }
    return $sb.ToString()
}

$root = Join-Path $env:TEMP ('RepoSync-ReadOnlyTest-' + [guid]::NewGuid().ToString('N'))
$oldHome = $env:REPOSYNC_HOME
$failed = $false
try {
    $source = Join-Path $root 'source'
    $destination = Join-Path $root 'destination'
    New-Item -ItemType Directory -Path $source, $destination -Force | Out-Null
    $env:REPOSYNC_HOME = Join-Path $root 'configuration'

    # --- source tree -------------------------------------------------------
    'kept file' | Set-Content -LiteralPath (Join-Path $source 'kept.txt')
    'read only payload' | Set-Content -LiteralPath (Join-Path $source 'locked.bin')
    New-Item -ItemType Directory -Path (Join-Path $source 'sub') -Force | Out-Null
    'nested payload' | Set-Content -LiteralPath (Join-Path $source 'sub\nested.txt')
    Set-ReadOnly (Join-Path $source 'locked.bin')
    $sourceBefore = Get-TreeFingerprint $source

    # --- destination tree (stale + read-only) -------------------------------
    'stale file' | Set-Content -LiteralPath (Join-Path $destination 'stale.txt')
    Set-ReadOnly (Join-Path $destination 'stale.txt')
    $staleDir = Join-Path $destination 'stale-dir'
    New-Item -ItemType Directory -Path (Join-Path $staleDir 'inner') -Force | Out-Null
    'stale nested' | Set-Content -LiteralPath (Join-Path $staleDir 'inner\stale-nested.txt')
    Set-ReadOnly (Join-Path $staleDir 'inner\stale-nested.txt')
    Set-ReadOnly $staleDir

    # --- run the compiled CLI ----------------------------------------------
    & $cli add readonly --source $source --destination $destination --json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Create profile failed' }
    # The destination intentionally holds content (stale read-only entries), so
    # ownership of that folder must be adopted explicitly.
    & $cli sync readonly --yes --adopt --json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Sync failed: read-only destination entries were not handled' }

    # --- assertions ---------------------------------------------------------
    if (Test-Path -LiteralPath (Join-Path $destination 'stale.txt')) { Write-Host 'FAIL: stale read-only file was not deleted' -ForegroundColor Red; $failed = $true }
    if (Test-Path -LiteralPath $staleDir) { Write-Host 'FAIL: stale read-only directory was not removed' -ForegroundColor Red; $failed = $true }
    if (-not (Test-Path -LiteralPath (Join-Path $destination 'kept.txt'))) { Write-Host 'FAIL: kept file missing from mirror' -ForegroundColor Red; $failed = $true }
    if (-not (Test-Path -LiteralPath (Join-Path $destination 'sub\nested.txt'))) { Write-Host 'FAIL: nested file missing from mirror' -ForegroundColor Red; $failed = $true }

    $mirrorLocked = Join-Path $destination 'locked.bin'
    if (-not (Test-Path -LiteralPath $mirrorLocked)) { Write-Host 'FAIL: read-only source file was not mirrored' -ForegroundColor Red; $failed = $true }
    elseif (-not (Test-IsReadOnly $mirrorLocked)) { Write-Host 'FAIL: mirrored copy of a read-only source file is writable (fidelity broken)' -ForegroundColor Red; $failed = $true }

    $sourceAfter = Get-TreeFingerprint $source
    if ($sourceAfter -ne $sourceBefore) { Write-Host 'FAIL: the source tree was modified by the sync' -ForegroundColor Red; $failed = $true }

    # --- update a read-only destination file -------------------------------
    'kept file v2' | Set-Content -LiteralPath (Join-Path $source 'kept.txt')
    $mirrorKept = Join-Path $destination 'kept.txt'
    if (Test-Path -LiteralPath $mirrorKept) { Set-ReadOnly $mirrorKept }
    & $cli sync readonly --yes --adopt --json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Second sync failed' }
    if ((Get-Content -LiteralPath $mirrorKept -Raw).Trim() -ne 'kept file v2') { Write-Host "FAIL: read-only destination file was not updated (content: '$(Get-Content -LiteralPath $mirrorKept -Raw)')" -ForegroundColor Red; $failed = $true }
    if ((Get-Content -LiteralPath (Join-Path $source 'kept.txt') -Raw).Trim() -ne 'kept file v2') { Write-Host 'FAIL: source file not updated as expected' -ForegroundColor Red; $failed = $true }

    & $cli verify readonly --json | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host 'FAIL: verify reported differences after sync' -ForegroundColor Red; $failed = $true }

    if ($failed) { throw 'READ-ONLY ACCEPTANCE FAILED' }
    Write-Host 'PASS: compiled CLI removed stale read-only file and directory, kept read-only source fidelity, updated a read-only destination file, and never modified the source tree.' -ForegroundColor Green
} finally {
    if ($null -eq $oldHome) { Remove-Item Env:REPOSYNC_HOME -ErrorAction SilentlyContinue } else { $env:REPOSYNC_HOME = $oldHome }
    # Remove the read-only bits first so cleanup can succeed.
    if (Test-Path -LiteralPath $root) {
        Get-ChildItem -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
            try { $_.Attributes = $_.Attributes -band (-bnot [System.IO.FileAttributes]::ReadOnly) } catch { }
        }
        Remove-Item -LiteralPath $root -Force -Recurse -ErrorAction SilentlyContinue
    }
}
