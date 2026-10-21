# RepoSync CLI reference — v0.2.7

Entrypoint (Windows): `%LOCALAPPDATA%\RepoSync\bin\RepoSyncCLI.exe`. Optional PATH wrapper: `reposync` if installed. CLI doesn't require Git. In PowerShell:

```powershell
$cli = "$env:LOCALAPPDATA\RepoSync\bin\RepoSyncCLI.exe"
& $cli --version
```

| Command | Required argument(s) | Optional flags | Writes files? |
|---|---|---|---|
| `add` | `NAME --source DIR --destination DIR` | `--preset review\|code`, repeatable `--include`, repeatable `--exclude`, `--json` | Configuration only |
| `update` | `NAME` | `--source`, `--destination`, `--preset`, repeatable `--include`, repeatable `--exclude`, `--json` | Configuration only |
| `list` | None | `--json` | No |
| `preview` | `NAME` | `--json` | No |
| `sync` | `NAME` | `--yes`, `--adopt`, `--json` | **YES: changes and deletes destination** |
| `verify` | `NAME` | `--json` | No |
| `status` | `NAME` | `--json` | No |
| `remove` | `NAME` | `--json` | Removes configuration only, NOT destination |
| `gui` | None | `--json` accepted | Opens UI; no implicit sync |

`--json` goes **after** the subcommand, e.g. `preview Demo --json`. `--version` is a top-level flag.

### Preview and verify

```powershell
& $cli list --json
& $cli preview Demo --json
& $cli verify Demo --json
& $cli status Demo --json
```

`preview` gives expected `copy`, `delete_files`, `delete_dirs`, `create_dirs`, ownership and warnings. `verify` compares local file content with SHA-256 and reports `missing`, `extra`, `different`, missing/extra directories. These operations do not upload to Google Drive.

### Exact mirror, human-authorized only

```powershell
& $cli sync Demo --yes --json
```

Only run if user specifically authorized the current source, target and pending deletion preview. A populated unowned destination additionally requires `--adopt --yes`; **do not infer approval**. Without `--yes`, interactive CLI prompts for literal `SYNC` and refuses noninteractive execution.

### Filter examples

```powershell
& $cli add PixelNodes --source 'M:\AIFUN\Film_Tool\Pixel-Nodes' --destination 'M:\AIFUN\Film_Tool\Pixel-Nodes_ReviewSnapshot' --preset review --include 'ComfyUI-Pixel_Nodes/**' --include 'Pixel_Nodes_ComfyUI.html' --json
& $cli update PixelNodes --exclude 'tests' --exclude 'temp' --json
```

For `update`, supplied repeatable filter arguments **replace the entire corresponding custom list**. Omitted filter arguments retain existing lists. No-slash globs match path components at any depth; slash globs match relative paths; `folder/**` includes a subtree. Include-only rules never bypass preset/default exclusions.

### Exit codes and errors

`0` command success; `2` operation error; `3` `verify` returned mismatch. JSON errors include `ok:false` and an `error` object. GUI native bridge unavailable is not a CLI issue. `status` reports **local** sync state only; cloud upload status belongs to Google Drive Desktop.

### Read-only destination items (v0.2.7)

A destination that is a Google Drive "mirrored folder" has its directories marked read-only by DriveFS, and Windows then refuses to delete or replace them. The engine now clears the read-only attribute on the exact path it is about to mutate, immediately before that mutation, and retries a bounded number of times. The source is never modified, a read-only source file is still mirrored as read-only, and the CLI surface, JSON schema and exit codes are unchanged.

When a removal still fails for another reason, `sync` exits `2` with an `error` object whose message names the exact destination path, states that the mirror is not fully verified, and asks for a new preview before retrying. These are the two messages you can meet:

- `Could not remove obsolete destination file <path>: ... The file may still carry a read-only attribute, or another process may hold it open; mirror is not fully verified. Stop and preview before retrying.`
- `Could not remove obsolete destination directory <path>: ... The directory may still carry a read-only attribute, or a concurrent process may have created content or retained an open handle; mirror is not fully verified. Stop and preview before retrying.`

Do not work around such an error by deleting files by hand: a genuine lock or a directory that is not empty is real stale content, and the path belongs in the bug report. A destination that contains a Google Drive managed scratch path (`.tmp.driveupload`, `.tmp.drivedownload`) is never removed; the sync stops instead.
