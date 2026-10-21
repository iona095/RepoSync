# RepoSync v0.2.7 — focused regression and Windows acceptance

Status: **built, installed and verified on the real profile** (2026-10-21). Every
number below is a run on this machine; this kit has **no CI**.

## Root cause (confirmed, not assumed)

Google Drive for Desktop (DriveFS `132.0.0.0`,
`C:\Program Files\Google\Drive File Stream\132.0.0.0\GoogleDriveFS.exe`) marks the
**directories** of every folder that is a Drive *mirrored folder* with
`FILE_ATTRIBUTE_READONLY`, and re-applies the bit asynchronously. `%LOCALAPPDATA%\Google\DriveFS\root_preference_sqlite.db`
(`roots` table) lists 5 mirrored roots, all on media `M2` = `M:\`:

| root_id | path | relation |
|---|---|---|
| 3 | `M:\AIFUN\Film_Tool\PixelCraft_ReviewSnapshot` | the **destination** that failed |
| 4 | `M:\AIFUN\RepoSync` | this build kit |
| 5 | `M:\AIFUN\OCMS-S` | another RepoSync destination |
| 6 | `M:\AIFUN\PixelCraftsCo` | — |
| 7 | `M:\AIFUN\Film_Tool\Pixel-Nodes_ReviewSnapshot` | another RepoSync destination |

The source `M:\AIFUN\Film_Tool\PixelCraft` is **not** a Drive root. Measured on this
machine: 5 Drive roots = 98.1–100 % read-only directories, 0 read-only files;
non-Drive trees = 0–41.9 %. Windows then refuses `unlink` / `rmdir` /
`os.replace`-overwrite on those paths with `WinError 5`. A second, independent
cause: `shutil.copy2` propagates the *source* file's read-only bit onto the
mirrored copy, so a mirrored read-only file also cannot be deleted.

## Implemented

- Read-only destination items are handled safely on Windows. Before RepoSync
  updates or deletes one exact path in the destination, it clears the
  read-only attribute (`FILE_ATTRIBUTE_READONLY`) on that path only, with a
  bounded retry. The source folder is never modified and the attribute is
  never cleared across the destination tree in advance.
- A read-only source file is still mirrored as a read-only file, so the mirror
  stays faithful to the source; such a mirrored file can still be updated or
  removed by a later sync.
- A deletion that fails for any other reason (genuine lock, concurrent
  process) still aborts the sync with an error that names the exact path,
  states that the mirror is not fully verified, and asks the user to stop and
  preview again before retrying. `WinError 145` / `ENOTEMPTY` is explicitly
  **not** treated as a permission problem.
- RepoSync refuses to delete a tree that contains a Drive managed scratch path
  (`.tmp.driveupload` / `.tmp.drivedownload`), which it never traversed before.
- The type-conflict path (a directory where the source has a file, and the
  reverse) is now guarded with the same error contract as the delete loops.
- Unchanged from v0.2.6: GUI, saved profiles, filters, presets, and the agent
  CLI surface (9 subcommands, same JSON schema, same profile schema).
- The packaged UI's version chip and its mock bridge now read `v0.2.7` (the
  previous build still shipped the fallback label `v0.2.6`), and the three UI
  tests now assert the engine's `VERSION` instead of a hardcoded string, so
  the packaged label can no longer drift away from the engine version.

## Verification completed on this machine

Windows 11 Pro 10.0.26200, `py -3.12` = CPython 3.12.3, pytest 8.3.5,
PyInstaller 6.22.3, pywebview 6.2.1, Inno Setup 7.1.0.

### 1. Python regression suite

Run in place (`.build\.testvenv\Scripts\python.exe`, a self-contained
Python 3.12.3 + pytest 8.3.5 environment so the suite does not depend on the
user's site-packages):

    cd M:\AIFUN\RepoSync\RepoSync_v0.2.7_ReadOnly_Safe_Sync_Build_Kit
    .build\.testvenv\Scripts\python.exe -m pytest -q test_sources
    77 passed, 1 skipped in 3.63s

Same suite in a **clean environment** (fresh temporary
`HOME`/`USERPROFILE`/`APPDATA`/`LOCALAPPDATA`, `DSH_HOME` unset, the npm
directory removed from `PATH`), via
`~/.agents/skills/clean-env-verification/scripts/clean-env-run.mjs`:

    clean-env-run.mjs --timeout 900 --cwd <kit> -- <testvenv python> -m pytest -q test_sources
    77 passed, 1 skipped in 3.62s
    clean-env: command exited 0 after 4.2s

The single skip is `test_helpers_are_no_ops_off_windows` (POSIX-only, skipped
on Windows by design).

New file `test_sources/test_readonly_destination.py`: **26 tests** (25 passed,
1 skipped on Windows). It pins the read-only classification, the real
sharing-violation lock, the DriveFS re-mark race, both type-conflict
directions, the Drive scratch-path refusal, the error wording, and source
immutability. Non-vacuity was proven with 4 mutants applied to a *copy* of the
engine in `%TEMP%` (raw-OSError leak, swallowed delete, source unlock,
disabled Drive-managed guard); each mutant made its target test fail.

Two pre-existing defects in the kit's own test harness were fixed while
verifying this:

- `test_sources/test_bridge_ready_contract.py` read `source/ui/index.html`
  with the machine's cp1253 locale encoding and raised
  `UnicodeDecodeError`; it now reads with `encoding="utf-8"`. The suite is
  therefore green **without** `-X utf8` now (it previously needed it).
- `test_sources/test_reposync.py` inserted the **kit root** into `sys.path`
  instead of the engine directory, so it could only import the engine when
  another test file happened to be collected first. Running that file alone
  raised `ModuleNotFoundError: No module named 'reposync'`. It now inserts
  `<kit>/source`; the file runs standalone (16 passed) and the suite is
  order-independent.

### 2. Build

    pwsh -NoProfile -ExecutionPolicy Bypass -File .\Build-RepoSync-Installer.ps1
    BUILD SUCCESS — DISTRIBUTABLE WINDOWS INSTALLER
    Installer: ...\release\RepoSync_Setup_v0.2.7.exe
    SHA256:    2B50585B085457D9D604C6F0899BA8A2ADE532237841D2D7339754B444793A66

    (The build printed 1E5AA13BA326EA3ABB35C538757FA3B0D036D93F6EF42FE59F118C3656E4D024
     for the pre-notice rebuild; the installer in release\ is the later
     notice-only repackage and carries the digest above. See the final section
     below.)

- installer `release\RepoSync_Setup_v0.2.7.exe`, 28 393 167 bytes,
  LastWriteTime 2026-10-21 16:21:21, `FileVersion 0.2.7.0`,
  `ProductVersion 0.2.7` (the earlier pre-notice rebuild was 28 392 931 bytes
  and is dated 2026-10-21 15:55:13; see the final section below).
- compiled binaries: `RepoSync.exe` 13 734 290 B, `RepoSyncCLI.exe`
  13 014 312 B (2026-10-21 15:54 / 15:55).
- `stage\` is clean: exactly one `skills\reposync` tree, no nested
  `skills\skills` duplicate, one `reposync.cmd`, and `release\` holds exactly
  one installer.
- The build itself is read-only-hostile by design now: the kit folder is a
  Drive mirror root, so the builder clears `FILE_ATTRIBUTE_READONLY` in its own
  build tree before every destructive step (skipping reparse points), re-scans
  and **throws naming the first path** it could not clear, retries a failed
  destructive step up to 2 more times, and clears PyInstaller's own cache
  directory.

### 3. Acceptance against the compiled CLI

    pwsh -NoProfile -ExecutionPolicy Bypass -File .\Test-RepoSync-ReadOnly.ps1
    PASS: compiled CLI removed stale read-only file and directory, kept
    read-only source fidelity, updated a read-only destination file, and never
    modified the source tree.
    (exit 0; temporary folders only)

### 4. Install over v0.2.6

    release\RepoSync_Setup_v0.2.7.exe /VERYSILENT /SUPPRESSMSGBUTS /NORESTART
    installer exit=0
    installed CLI version before: 0.2.6   after: 0.2.7
    uninstall entry: "RepoSync 0.2.7" -> C:\Users\GNV\AppData\Local\RepoSync\

Same AppId, so it is an in-place per-user upgrade. User data untouched:
`%LOCALAPPDATA%\RepoSync\profiles.json` is 928 B with `LastWriteTime
2026-10-11 19:08:59` (unchanged) and still holds the three profiles
`OCMS-S`, `Pixel-Nodes`, `PixelCraft`. No stale `sync-*.lock` is left behind.

### 5. The real failing scenario (this is the actual user bug)

The destination is a live Drive mirror, so it is still marked read-only by
DriveFS. Measured with .NET attributes immediately before the run:
**2429 entries, 255 read-only**.

- A stale read-only file and a stale read-only directory containing a
  read-only child were planted in the real destination
  (`__ro_probe_stale.txt`, `__ro_probe_stale_dir\child.txt`, all with
  `ReadOnly` set, the directory `ReadOnly, Directory`).
- `RepoSyncCLI.exe sync PixelCraft --yes --json` (installed v0.2.7):

      "ok": true, "copied": 6, "deleted_files": 2, "deleted_dirs": 1,
      "source_files": 2173,
      "verification": "local SHA-256 verified; Drive Desktop uploads asynchronously"
      (exit 0)

  The read-only stale file, the read-only stale directory and its read-only
  child were removed. **No `WinError 5`.** This is the exact operation that
  produced `PermissionError: [WinError 5] Access is denied` on v0.2.6.
- `RepoSyncCLI.exe verify PixelCraft --json`: `ok:true`,
  `source_files 2173 = destination_files 2173`, `missing []`, `extra []`,
  `different []` (exit 0).
- Source immutability, measured directly: 13 435 source files (excluding
  `.git`) were snapshotted before and after a further sync that deleted and
  re-copied a **read-only** source file
  (`docs\Vision\VISUAL FORENSICS Test\glm 5.3 flash\screenshots\REF-001__image-node-idle-empty.png`):
  **0 differences** in size, `mtime_ns` and the read-only attribute; the
  mirrored copy came back byte-identical **and** kept the read-only
  attribute (fidelity).

### 6. Independent review

Three specialist reviews (code reviewer, test engineer, security auditor) ran
over the v0.2.7 change. Consensus: the core fix is correct — just-in-time
unlock on the exact path only, zero source paths touched, attribute fidelity
preserved, source never modified, CLI/profile/output schema unchanged, and
the old raw-`PermissionError` escape removed. All six must-fix items they
raised (type-conflict path unwrapped, Drive-managed scratch paths deletable,
`atomic_json` temp cleanup masking the primary error, retry ordering versus
the DriveFS re-mark race, unverified retry budget, `source\reposync.cmd`
missing) are closed in this build.

## Environment change made on this machine (2026-10-21)

The legacy scheduled task **`PixelCraft Review Mirror`** (disabled, last run
2026-10-10 04:19:01) was deleted together with its script folder
`C:\Users\GNV\AppData\Local\PixelCraftReviewMirror`. It was a second mirror
into the same destination using `robocopy /MIR`, which would delete
RepoSync's `.reposync` metadata and any file the source does not have if it
were ever re-enabled. Its past run log was captured before deletion.

## Still open (not blockers for local use)

1. The destination is still a **Drive mirrored folder** (root_id 3). DriveFS
   keeps re-applying the read-only bit and keeps uploading the review
   snapshot — including its `.git` internals and `evidence/` — to Google
   Drive. Removing that folder from Drive's mirrored list stops both.
   Drive for desktop 132.0.0.0 exposes no command line for it; the supported
   route is its own preferences dialog: tray icon → Preferences → "My
   computer" → "Folders from your computer" → "PixelCraft_ReviewSnapshot" →
   overflow (⋮) → "Stop syncing" → Save. The change is instant, the local
   files stay on disk ("Existing files will remain on your computer"), and
   the already-set read-only bits stay set — they need one `attrib -R /S /D`
   afterwards. Do **not** use "Sign out" (DriveFS may remove files that were
   never uploaded) and do **not** edit `root_preference_sqlite.db` (live WAL,
   server-reconciled, mirrored by `mirror_sqlite.db`).
   Measured directly on 2026-10-21: a new directory inside the destination
   read "Directory" at t=0 s and "ReadOnly, Directory" at t=20 s, and the
   marker is scoped to Drive roots only.
2. This kit folder is itself a Drive mirror root (root_id 4), which is why
   the builder needs the read-only handling. Moving the kit out of the
   mirrored set removes that need.
3. Closed on 2026-10-21: the license audit had flagged `proxy_tools` because
   the installed wheel ships license metadata but no LICENSE file. The
   upstream BSD text is now bundled and pinned, and the audit passes with no
   review items - see the final section below.
4. The kit has **no CI**. The suite is wired into no automation; it was run
   by hand, in place and in a clean environment, on one machine.
5. The installed folder still carries leftovers from older installs that the
   current kit never ships and that an uninstall does not remove:
   `app\reposync.py` (a stale source copy — the frozen `bin\` executables are
   what actually run), `app\__pycache__\`, `bin\Start-RepoSync.cmd` and a
   whole `exe-build\build-venv\` tree. Harmless, but they are dead weight.
6. The POSIX path of the new helpers is exercised by exactly one test, which
   cannot run on Windows.
7. The **source** tree contains a literal directory
   `%SystemDrive%\ProgramData\Microsoft\Windows\Caches` — a leftover of an
   earlier tool that wrote an unexpanded `%SystemDrive%` path. It is source
   content, not a RepoSync path-expansion bug: RepoSync mirrors it faithfully,
   which is why the same folder exists in the destination. The source tree
   also still carries 603 read-only directories, fossils of the period when
   the source itself was Drive mirror root_id 2 (purged 2026-10-09 23:51:54).

If a deletion still fails, provide the exact path and the error text, say
whether another program had the destination open, and check
`%LOCALAPPDATA%\RepoSync\logs\webview-bridge.log`.

## Final artifact digests and license closure (2026-10-21)

The installer in `release\` was repackaged notice-only after the build above.
The GUI and CLI were byte-identical across that repackage. The shipped
artifacts are:

- Installer `RepoSync_Setup_v0.2.7.exe`, 28 393 167 B,
  LastWriteTime 2026-10-21 16:21:21
  SHA-256 `2B50585B085457D9D604C6F0899BA8A2ADE532237841D2D7339754B444793A66`
- GUI `RepoSync.exe`, 13 734 290 B
  SHA-256 `2B8729822458E8C72431686B4CC64964CEFA94B8032A6137B2EEC94273CACD77`
- CLI `RepoSyncCLI.exe`, 13 014 312 B
  SHA-256 `F8BCDD8A052DD907853411C55D707C1EE1679113550EC8218BEAEC356EF950A8`

The digest printed by the build (`1E5AA13B...`) was the pre-notice rebuild
(28 392 931 B, dated 2026-10-21 15:55:13) and is not the shipped artifact;
the shipped installer file is dated 2026-10-21 16:21:21.

License gate closed: `scripts\audit_build_licenses.py` now passes with 8 named
packages/optional dependencies and no review items. The upstream proxy_tools
0.1.0 BSD license text is bundled verbatim as
`stage\licenses\proxy_tools-0.1.0-upstream-BSD-LICENSE.txt` (1 436 B) and the
pinned copy lives in the kit at
`source\licenses\proxy_tools-0.1.0-BSD-LICENSE.txt`. The audit fails closed
(exit 2, "LICENSING GATE NEEDS REVIEW") when that pinned text is missing or
altered. Open item 3 in the list above is therefore closed.

See `WINDOWS_ACCEPTANCE_v0.2.7.md` for the acceptance checklist and
`CHANGELOG.md` for the 0.2.7 release notes.
