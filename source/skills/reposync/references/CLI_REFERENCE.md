# RepoSync CLI reference — v0.2.6

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
