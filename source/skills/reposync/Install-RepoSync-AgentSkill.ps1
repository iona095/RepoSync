# Optional, explicit per-user agent skill installation. Never run by the RepoSync installer.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('Codex','Claude','Custom')]
    [string]$Agent,
    [string]$Destination,
    [switch]$Force
)
$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md') -PathType Leaf)) { throw 'SKILL.md not found next to installer script.' }
switch ($Agent) {
    'Codex' { $target = Join-Path $HOME '.agents\skills\reposync' }
    'Claude' { $target = Join-Path $HOME '.claude\skills\reposync' }
    'Custom' {
        if ([string]::IsNullOrWhiteSpace($Destination)) { throw 'Custom requires -Destination pointing to the full reposync skill folder.' }
        $target = [IO.Path]::GetFullPath($Destination)
    }
}
if (Test-Path -LiteralPath $target) {
    if (-not $Force) { throw "A skill folder already exists: $target. Inspect it; use -Force only when intentionally replacing RepoSync files." }
}
New-Item -ItemType Directory -Path (Join-Path $target 'references') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $source 'SKILL.md') -Destination (Join-Path $target 'SKILL.md') -Force
Copy-Item -LiteralPath (Join-Path $source 'references\CLI_REFERENCE.md') -Destination (Join-Path $target 'references\CLI_REFERENCE.md') -Force
Write-Host "RepoSync skill installed for $Agent at: $target" -ForegroundColor Green
Write-Host 'No mirror operation was run; restart your agent session if it only discovers skills at startup.'
