# Safe, disposable CLI smoke test for built Windows executables.
# Does not touch any real RepoSync profiles or mirrors.
$ErrorActionPreference = 'Stop'
$cli = Join-Path $PSScriptRoot '.build\pyinstaller-dist\RepoSyncCLI.exe'
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) { throw "CLI missing: $cli; run builder first." }
$root = Join-Path $env:TEMP ('RepoSync-BinaryTest-' + [guid]::NewGuid().ToString('N'))
$oldHome = $env:REPOSYNC_HOME
try {
    New-Item -ItemType Directory -Path (Join-Path $root 'source'), (Join-Path $root 'destination') -Force | Out-Null
    $env:REPOSYNC_HOME = Join-Path $root 'configuration'
    'hello from test' | Set-Content -LiteralPath (Join-Path $root 'source\hello.txt')
    & $cli --version
    if ($LASTEXITCODE -ne 0) { throw 'Version check failed' }
    & $cli add disposable --source (Join-Path $root 'source') --destination (Join-Path $root 'destination') --json
    if ($LASTEXITCODE -ne 0) { throw 'Create profile failed' }
    & $cli preview disposable --json
    if ($LASTEXITCODE -ne 0) { throw 'Preview failed' }
    & $cli sync disposable --yes --json
    if ($LASTEXITCODE -ne 0) { throw 'Initial sync failed' }
    & $cli verify disposable --json
    if ($LASTEXITCODE -ne 0) { throw 'Local verify failed' }
    if (-not (Test-Path -LiteralPath (Join-Path $root 'destination\hello.txt'))) { throw 'File missing from mirror' }
    # Simulate Google Drive Desktop creating an upload scratch folder.
    $driveTemp = Join-Path $root 'destination\.tmp.driveupload'
    New-Item -ItemType Directory -Path $driveTemp -Force | Out-Null
    'in progress' | Set-Content -LiteralPath (Join-Path $driveTemp 'busy.part')
    & $cli preview disposable --json
    if ($LASTEXITCODE -ne 0) { throw 'Preview with Drive scratch failed' }
    & $cli verify disposable --json
    if ($LASTEXITCODE -ne 0) { throw 'Verify with Drive scratch failed' }
    Remove-Item -LiteralPath (Join-Path $root 'source\hello.txt')
    & $cli sync disposable --yes --json
    if ($LASTEXITCODE -ne 0) { throw 'Deletion sync failed' }
    if (Test-Path -LiteralPath (Join-Path $root 'destination\hello.txt')) { throw 'Stale file not deleted' }
    if (-not (Test-Path -LiteralPath (Join-Path $driveTemp 'busy.part'))) { throw 'Drive temporary file must remain untouched' }
    & $cli verify disposable --json
    if ($LASTEXITCODE -ne 0) { throw 'Post-delete verify failed' }
    Write-Host 'PASS: compiled CLI preview/sync/verify/stale-delete; Drive transient preserved, disposable folders only.' -ForegroundColor Green
} finally {
    if ($null -eq $oldHome) { Remove-Item Env:REPOSYNC_HOME -ErrorAction SilentlyContinue } else { $env:REPOSYNC_HOME = $oldHome }
    Remove-Item -LiteralPath $root -Force -Recurse -ErrorAction SilentlyContinue
}
