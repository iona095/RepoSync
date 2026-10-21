# RepoSync v0.2.7 — User manual

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
| `Access is denied` / `[WinError 5]` while deleting or updating destination files | See **Read-only destination items (Windows)** below. RepoSync clears the read-only attribute on the exact item it is about to change; if it still fails, the item is locked by another program — close anything using the destination, preview again, then retry |
| Google Drive still uploading | Wait for Drive Desktop; RepoSync can only verify the local target |
| Profile settings appear unsaved | Save the current form before Preview/Sync; switching profiles reloads saved values |

## 7. Limits and safety

RepoSync is **one-way, local, manual**. It is not a versioned backup, cloud upload tool, scheduled service, conflict-resolution system, or security/secret scanner. Symlinks/junctions are not traversed; unsafe target links are rejected. Never synchronize into a source folder or one of its ancestors/descendants. For sensitive source material inspect included files and Drive sharing permissions. Profiles in `%LOCALAPPDATA%\RepoSync\profiles.json` survive ordinary updates/uninstalls.

## Read-only destination items (Windows)

On Windows, an application can mark a file or a folder as **read-only**. Google
Drive for desktop does this to folders inside a synced drive, and a read-only
file in your source folder carries the same attribute into the mirror. Windows
then refuses to delete or overwrite a read-only item, which used to end a sync
with `PermissionError: [WinError 5] Access is denied`.

**What RepoSync does now**

- Right before RepoSync updates or deletes one specific item in the
  **destination**, it clears the read-only attribute on that exact item and
  then makes the change. No other destination item is affected, and the
  attribute is not stripped in advance across the whole tree.
- The **source** folder is never modified. RepoSync does not remove read-only
  attributes from your source files.
- A read-only file in the source is still mirrored as a read-only file, so the
  mirror stays faithful to the source. Such a mirrored file can still be
  updated or removed by a later sync, because RepoSync clears the attribute on
  that file only at the moment it is about to change it.

**When a deletion still fails**

If the item is genuinely locked — for example another program currently has it
open, or the file was created again by a concurrent process — the sync stops
with an error that names the exact path, states that the mirror is **not fully
verified**, and tells you to stop and preview again before retrying.

What to do:

1. Read the error and note the exact path it names.
2. Close any program that may be using that file or folder (editor, viewer,
   archive tool, antivirus scan).
3. Run **Preview** again and check the deletion list before you sync once more.
4. Do **not** delete files by hand to force the sync through.

## Saved profile list and routine confirmation (v0.2.6)

The sidebar displays a persistent vertical scrollbar and a count of all saved profiles. After saving a new profile, its row is automatically brought into view. A profile does not disappear merely because it is below the visible area. Saving a new profile using the name of a different existing profile is rejected rather than silently overwriting it. Renaming by saving under a new, unused name creates an additional profile and preserves the previous one.

**Confirm each sync** is an opt-in safety preference change in the GUI (ON by default). Turning it OFF skips the routine browser confirmation before each manual Sync Now, but the action **still previews first**, can delete obsolete destination files, and requires a click. A separate warning when adopting an unmanaged populated destination cannot be skipped. This preference is stored in `ui-preferences.json` alongside `profiles.json` in the RepoSync user configuration directory; no synchronization occurs while changing it. If the preference file cannot be read, routine confirmations remain ON. The agent CLI's explicit `--yes` requirement is unchanged.


## GUI updates in v0.2.6

- **Delete profile** removes only the selected saved profile entry after an explicit confirmation. It does not delete or alter the source folder, destination folder, or the files within either one. This confirmation cannot be disabled using *Confirm each sync*.
- **Resize the window** by dragging any outer edge or corner. The custom frameless window uses native Windows pointer tracking. If resizing fails, leave the application running and check `%LOCALAPPDATA%\RepoSync\logs\webview-bridge.log`; report which edge/corner, Windows DPI scaling, and whether the window was maximized.
- The agent CLI and mirroring engine remain unchanged except for the version identifier.

## Updates in v0.2.7

- **Read-only destination items are handled safely.** RepoSync clears the Windows
  read-only attribute on the exact destination item it is about to update or
  delete, immediately before doing so. The source folder is never modified, a
  read-only source file is still mirrored as a read-only file, and such a mirror
  file can still be updated or removed by a later sync. A deletion that fails
  for any other reason still stops the sync with the exact path and a clear
  instruction to preview again before retrying.
- The GUI, profiles, filters, presets and the Drive transient-directory rules
  are unchanged from v0.2.6.
