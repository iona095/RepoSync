---
name: reposync
summary: Inspect, preview and verify RepoSync local folder mirror profiles using the agent CLI. Only synchronize when a human explicitly approves the destination changes.
description: >
  Use when asked to work with RepoSync, configure a local folder mirror,
  mirror a project to a Google Drive Desktop folder, inspect changed files,
  or verify a previously synchronized snapshot. Never assume Git is required.
---

# RepoSync — agent CLI skill

RepoSync is a **manual, exact, one-way local-folder mirror**, not an archive or direct Google Drive uploader. It works on **any local folder**, including non-Git folders. The *destination* may be a Google Drive Desktop synchronized folder; cloud transfer is separate.

## First: locate the CLI

On Windows, prefer `%LOCALAPPDATA%\RepoSync\bin\RepoSyncCLI.exe`. In PowerShell:

```powershell
$cli = Join-Path $env:LOCALAPPDATA 'RepoSync\bin\RepoSyncCLI.exe'
if (-not (Test-Path -LiteralPath $cli)) { throw 'RepoSyncCLI.exe is not installed' }
& $cli --version
& $cli list --json
```

All subcommands accept `--json` (after the subcommand). Do not invent flags. See [CLI reference](references/CLI_REFERENCE.md).

## Read-only workflow (safe default)

1. Run `list --json` or `status NAME --json`.
2. Run `preview NAME --json`; inspect `copy`, `delete_files`, `delete_dirs`, `owner`, warnings, filters and paths.
3. Run `verify NAME --json` to check local source/target integrity. Exit code `3` means mismatch and should be reported, not masked.
4. Report results and limitations. **Do not claim the Google Drive cloud has finished syncing** from a local `ok`.

```powershell
& $cli preview PixelCraft --json
& $cli verify PixelCraft --json
```

## Profiles and filters

Config updates are writes to RepoSync's saved profile, not file synchronization. For changes, show the proposed source, destination, preset, include/exclude patterns before changing a profile if the user hasn't already approved them.

```powershell
& $cli add Demo --source 'C:\Work\Demo' --destination 'G:\My Drive\RepoSync\Demo' --preset review --json
& $cli update Demo --include 'ComfyUI-Pixel_Nodes/**' --include 'Pixel_Nodes_ComfyUI.html' --json
& $cli preview Demo --json
```

**Important:** `--include` and `--exclude` are repeatable. Passing either flag to `update` **replaces** the entire corresponding list; omitted flags leave lists unchanged. The `review` preset includes eligible media, while `code` excludes common media and binaries. Default safety exclusions apply in both cases.

## High-risk operation: exact sync

**No autonomous or implied synchronization.** A human must explicitly approve the specific profile, source/destination and current preview before the agent may run a destructive command. `sync --yes` explicitly permits changes and deletions **in the destination**. If owner is `unmanaged-populated`, `--adopt --yes` also requires separately confirmed adoption of that destination. Never self-authorize these flags; never target an untrusted, shared, source-adjacent, nested, or unspecified folder.

With explicit permission only:

```powershell
& $cli preview Demo --json
# Review the changes and receive the user's specific authorization.
& $cli sync Demo --yes --json
& $cli verify Demo --json
```

A user request to *inspect*, *review*, or *verify* does not constitute permission to sync, delete or adopt. If a command fails midway, report that the target may be partially updated; do not auto-retry or clean up without permission.

## Special cases

- RepoSync deliberately ignores `.tmp.driveupload` and `.tmp.drivedownload` in **the destination**; these are Drive Desktop managed transient paths, not project data.
- GUI errors, backend errors, or folder-lock conflicts are **not** a reason to delete source files, disable protections, or grant broad permissions.
- Git branch and commit metadata are optional and do not determine what the tool can mirror.
- No network access or direct Drive API required to run the CLI.
- Version check: `& $cli --version`. GUI badge should report the same installed engine version. GUI `review`/`code` dropdown appearance is independent of the CLI `--preset` flag; saved profiles share the same settings.
- Profiles normally reside in `%LOCALAPPDATA%\RepoSync\profiles.json`. Do not read user secrets unnecessarily.

Read `references/CLI_REFERENCE.md` for exact argument syntax, flags, exit codes and examples. `MANUAL.md` is shipped with the installed application at `%LOCALAPPDATA%\RepoSync\docs\MANUAL.md`.
