# RepoSync v0.2.6

**RepoSync** is a Windows-first, standalone **manual exact-folder mirror** for **any local folder**, including non-Git projects. It preserves your source files and updates/deletes *destination* files until they match the filtered source. It does **not** produce ZIP snapshots, run scheduled jobs or directly upload to Google Drive. If the destination is watched by Google Drive Desktop, that separate application handles cloud synchronization.

## What is included

- Premium dark WebView2 GUI with cyan glowing selection, lime Sync button, the selected glass-folder icon, visible app version, custom dark keyboard-operable preset dropdown, accessible tooltips on filter info buttons, and Windows edge/corner resize handles.
- Saved reusable profiles, native folder pickers, `review` and `code` presets, custom include/exclude globs, manual Preview / Sync / Verify.
- Separate agent-compatible `RepoSyncCLI.exe` and `reposync.cmd` wrapper. Read-only operations can return JSON; destructive sync requires explicit confirmation/authorization.
- Bundled **MANUAL.md** with user instructions and **skills/reposync/SKILL.md** with an agent-use contract and CLI reference.
- SHA-256 local verification; protection against source/target nesting, unmanaged targets and link/junction traversal. Drive transient upload/download directories are ignored in the local destination.

## Windows user guide

Open **RepoSync** via Start Menu. Select or add a profile, use the **i** tooltips, Save, Preview, inspect deletions, and then explicitly confirm **SYNC NOW**. Verify local mirror afterward. **Google Drive upload completion must be checked separately**. See [MANUAL.md](MANUAL.md) for full illustrated-by-examples steps and troubleshooting.

## Agent CLI quick start

```powershell
$cli = "$env:LOCALAPPDATA\RepoSync\bin\RepoSyncCLI.exe"
& $cli --version
& $cli list --json
& $cli preview PixelCraft --json
& $cli verify PixelCraft --json
# SYNC IS DESTRUCTIVE TO THE DESTINATION; HUMAN AUTHORIZATION REQUIRED:
# & $cli sync PixelCraft --yes --json
```

To install the optional reusable agent skill, see `skills/reposync/SKILL.md` and `skills/reposync/Install-RepoSync-AgentSkill.ps1`. Installation **does not** grant agents permission to run destructive operations. Profiles remain in `%LOCALAPPDATA%\RepoSync\profiles.json` through updates/uninstallation.

## Build and release

Build from the Windows distribution kit with `Build-RepoSync-Installer.ps1` (Python 3.12, PyInstaller, pywebview, Inno Setup). The installed GUI requires Microsoft Edge WebView2 Runtime. Run local tests first, then verify native WebView2, folder picker, **all eight window resize directions (especially bottom-right)**, maximize/restore, profile persistence, preview, sync, verify and uninstallation using disposable data. Recheck dependency licensing notices before redistribution; the earlier v0.2.3 kit flagged a missing authoritative `proxy_tools` notice. The installer is unsigned until signed separately.

The core mirroring engine is unchanged from v0.2.3 except for the version constant; there is **no automatic sync**.

### v0.2.6 GUI improvements

- Sidebar always shows a scrollbar and total profile count; newly saved profile is scrolled into view.
- New profile names cannot silently overwrite existing entries.
- GUI-only **Confirm each sync** switch (default ON) persists across restarts in `ui-preferences.json`. Turn OFF to skip the routine Sync dialog; the separate unmanaged-destination safety confirmation always remains.
- Agent CLI and mirroring behavior unchanged.


## GUI updates in v0.2.6

- **Delete profile** removes only the selected saved profile entry after an explicit confirmation. It does not delete or alter the source folder, destination folder, or the files within either one. This confirmation cannot be disabled using *Confirm each sync*.
- **Resize the window** by dragging any outer edge or corner. The custom frameless window uses native Windows pointer tracking. If resizing fails, leave the application running and check `%LOCALAPPDATA%\RepoSync\logs\webview-bridge.log`; report which edge/corner, Windows DPI scaling, and whether the window was maximized.
- The agent CLI and mirroring engine remain unchanged except for the version identifier.
