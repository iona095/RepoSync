# RepoSync v0.2.4 — User manual

**Purpose:** manually mirror **any local folder** to another local folder. No Git requirement. The target is an **exact filtered local mirror**, not an archive or historical backup. Google Drive Desktop may then sync the target to the cloud on its own schedule. RepoSync does **not** upload through the Drive API and cannot confirm cloud upload completion.

## 1. Open the application

Open **RepoSync** from Start Menu. The version badge beside the app name displays the installed engine version. You may also run `RepoSyncCLI.exe --version` in PowerShell to check the agent CLI. If either version is not what you expect, check the installed executable/shortcut before syncing.

The Windows app is resizable from any edge or corner, with a minimum 1000×770 window size. Drag its title bar to move; double-click the title bar or use □ to maximize/restore. Smaller windows scroll the content instead of hiding the lower controls. **Native frameless resizing requires validation on your Windows build.**

Choose a profile on the left, or select **New profile**. A profile consists of:

| Setting | Meaning |
| --- | --- |
| Profile | Unique label, e.g. `PixelCraft`, `Pixel-Nodes` or `OCMS-S` |
| Source | Folder to read; **never modified** by a mirror operation |
| Destination | Dedicated folder RepoSync owns and changes; may be inside a Google Drive Desktop-synced folder |
| Preset | `review` includes project media/build artifacts by default; `code` additionally excludes common binary/media files |
| Additional exclusions | One glob per line; files/directories matched here are never mirrored |
| Include-only patterns | Optional allowlist, one glob per line; blank means all source files except exclusions |

Use the circled **i** beside each filter for an explanation: hover with the mouse or focus with Tab. The tooltip does not change any filter. The **Preset** dropdown is custom-rendered for WebView2: click to choose `review` or `code`; keyboard users can open with Enter/Space/Arrow, change focus with Arrow/Home/End, select with Enter or click, and close with Escape.

**Avoid reusing a target that contains irreplaceable files.** The exact mirror removes destination files that no longer belong to the selected source. RepoSync protects unowned populated destinations and asks for explicit adoption, but you should still inspect Preview carefully.

## 2. Choose what to mirror

### Full review mirror

Choose **Preset: review**, leave Include-only blank, and add exclusions such as:

```text
tests
working-files/**
*.psd
```

Default safety exclusions also apply (e.g. `.git`, `.venv`, `node_modules`, `.env`, caches and common credentials). Review those patterns before uploading sensitive work; no filename filter can guarantee that secrets inside arbitrary documents are excluded.

### Only one subtree and one HTML file

Source folder may contain many backups and baselines. In **Include-only patterns** enter:

```text
ComfyUI-Pixel_Nodes/**
Pixel_Nodes_ComfyUI.html
```

This includes all eligible files under `ComfyUI-Pixel_Nodes` and the root HTML file. Other backup directories, root files and `tree.txt` are left out. Default preset exclusions still apply. As a separate step, Preview shows obsolete files in the destination that would be deleted.

**Pattern rules:** a glob without `/` matches any path component (e.g. `tests` matches nested `tests` directories). `folder/**` includes that folder and all eligible descendants. `*.log` matches log filenames. Include-only rules do not override exclusions.

## 3. Safe synchronization workflow

1. **Save profile.** This stores configuration only; no file transfer.
2. **Preview changes.** Inspect files to copy/update, files/directories to delete, warnings and ownership state. This is read-only.
3. **SYNC NOW.** Confirm the dialog. For existing populated unmanaged destinations, a separate explicit adoption confirmation is required. Only then does RepoSync modify the *destination*.
4. **Verify local mirror.** Compares selected source and local target content using SHA-256. A successful check proves local mirroring, **not** Google Drive cloud completion.
5. Check the Google Drive Desktop tray/status if your destination is synced to Drive, and allow its upload to finish.

**Special case:** RepoSync ignores `.tmp.driveupload` and `.tmp.drivedownload` in the destination because Drive Desktop manages these temporary paths. Do not delete them to force completion.

## 4. Agent CLI (PowerShell)

Open a **new terminal** after installing if you enabled user PATH integration. Otherwise invoke by full path:

```powershell
$cli = "$env:LOCALAPPDATA\RepoSync\bin\RepoSyncCLI.exe"
& $cli --version
& $cli list --json
```

Create a profile for **any** local folder (Git is optional):

```powershell
& $cli add Demo --source "C:\Work\Demo" --destination "G:\My Drive\Mirrors\Demo" --preset review --json
& $cli preview Demo --json
```

Set an include-only selection (repeat `--include` once per pattern):

```powershell
& $cli update Demo --include 'ComfyUI-Pixel_Nodes/**' --include 'Pixel_Nodes_ComfyUI.html' --json
& $cli preview Demo --json
```

**Caution:** using `update --include` *replaces* the entire previous include list; `--exclude` similarly replaces the exclusion list when supplied. Omitted flags preserve existing values.

Do a **manual, explicitly authorized** sync only after previewing:

```powershell
& $cli sync Demo --yes --json
& $cli verify Demo --json
& $cli status Demo --json
```

`--yes` is **authorization to delete destination files**. Only use it when you/the user approved the *specific profile and current preview*. To adopt an already populated **unmanaged** destination requires both `--adopt --yes`, after an explicit separate confirmation. Never provide those flags proactively when an agent has not obtained permission.

Other CLI verbs:

| Command | Action |
| --- | --- |
| `list --json` | Inspect configured profiles |
| `preview NAME --json` | Dry-run exact expected local changes |
| `verify NAME --json` | Verify local mirror (SHA-256), no writes |
| `status NAME --json` | Read last successful local sync record |
| `update NAME ... --json` | Modify profile settings; no copying |
| `remove NAME --json` | Remove profile *only*, not its destination |
| `sync NAME --json` | Interactive `SYNC` confirmation where supported; does not run headlessly without `--yes` |

Exit codes: `0` success, `2` invalid input/operation error, `3` local verification mismatch. Prefer interpreting JSON `ok` plus the exit code, and surface failures to the user. JSON can contain local paths: keep it within trusted agent context.

## 5. Install the agent skill

The installer includes a portable skill at:

```text
%LOCALAPPDATA%\RepoSync\skills\reposync\SKILL.md
```

Install per-user Codex/Claude Code skill with PowerShell:

```powershell
$skillRoot = "$env:LOCALAPPDATA\RepoSync\skills\reposync"
& "$skillRoot\Install-RepoSync-AgentSkill.ps1" -Agent Codex
& "$skillRoot\Install-RepoSync-AgentSkill.ps1" -Agent Claude
```

These are **optional user-initiated actions**, never automatic installer side-effects. For another harness, copy the `reposync` skill folder to its documented skill directory manually. Do not assume an arbitrary DSH preset automatically discovers Codex/Claude skills.

The skill explains safe preview/verify workflows, the CLI schema, supported patterns and destructive-operation approval. It grants **no extra permissions** to agents.

## 6. Troubleshooting

| Problem | Recommended action |
| --- | --- |
| `Desktop bridge not ready` | Restart the GUI; inspect `%LOCALAPPDATA%\RepoSync\logs\webview-bridge.log` and verify the installed `.exe` version |
| Native Browse won't open | Check Windows WebView2 Runtime; retry the built EXE and capture bridge log, never sync blindly |
| `Unexpected content in obsolete destination directory` | Stop sync; inspect remaining target files and concurrent apps, then preview again. Avoid manual deletion |
| Destination is `unmanaged-populated` | Use a new empty destination if possible; `--adopt --yes` only after explicit consent and preview |
| Verification differs | Inspect JSON `missing`, `extra`, `different`, `missing_dirs`, `extra_dirs`. Destination may be partially updated; do not blindly rerun on production data |
| Google Drive still uploading | Wait for Drive Desktop; RepoSync can only verify the local target |
| Profile settings appear unsaved | Save the current form before Preview/Sync; switching profiles reloads saved values |

## 7. Limits and safety

RepoSync is **one-way, local, manual**. It is not a versioned backup, cloud upload tool, scheduled service, conflict-resolution system, or security/secret scanner. Symlinks/junctions are not traversed; unsafe target links are rejected. Never synchronize into a source folder or one of its ancestors/descendants. For sensitive source material inspect included files and Drive sharing permissions. Profiles in `%LOCALAPPDATA%\RepoSync\profiles.json` survive ordinary updates/uninstalls.
