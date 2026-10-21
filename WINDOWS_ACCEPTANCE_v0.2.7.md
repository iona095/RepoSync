# RepoSync v0.2.7 Windows acceptance

This document lists the checks that were actually executed for the v0.2.7
build on 2026-10-21, and what was not checked. It is not an owner acceptance
statement: no product-owner sign-off for this build is recorded here.

The installer was repackaged notice-only. The supplied GUI and CLI executables
are byte-identical across that repackage - same SHA-256 as the binaries the
build produced.

## Publication checks performed on Windows

Environment: Windows 11 Pro 10.0.26200, `py -3.12` = CPython 3.12.3,
pytest 8.3.5, PyInstaller 6.22.3, pywebview 6.2.1, Inno Setup 7.1.0.

- Regression suite: 77 passed, 1 skipped in 3.81 s in place, and 77 passed,
  1 skipped in 3.58 s in a clean temporary environment (fresh
  HOME/USERPROFILE/APPDATA/LOCALAPPDATA, DSH_HOME unset, global npm tool
  directory removed from PATH). The single skip is a POSIX-only test.
- 26 of those tests are the new `test_sources\test_readonly_destination.py`.
  Non-vacuity was proven with 4 mutants applied to a copy of the engine; each
  mutant made its target test fail.
- Baseline of the same suite in the untouched v0.2.6 kit: 1 failed / 51 passed.
  That failure is a pre-existing cp1253 locale bug in
  `test_bridge_ready_contract.py` (fixed by reading the file as utf-8), not a
  regression.
- Compiled CLI acceptance:
  `pwsh -NoProfile -ExecutionPolicy Bypass -File .\Test-RepoSync-ReadOnly.ps1`
  -> "PASS: compiled CLI removed stale read-only file and directory, kept
  read-only source fidelity, updated a read-only destination file, and never
  modified the source tree." (exit 0; temporary folders only).
- Install over v0.2.6 (same AppId, per-user): installer exit 0; installed CLI
  reports 0.2.6 before and 0.2.7 after; `%LOCALAPPDATA%\RepoSync\profiles.json`
  unchanged (928 B, still the three profiles OCMS-S, Pixel-Nodes, PixelCraft);
  no stale `sync-*.lock` left behind.
- Real failing scenario, live Google Drive marked destination
  (`M:\AIFUN\Film_Tool\PixelCraft_ReviewSnapshot`, 255 read-only entries
  measured immediately before the run): a planted stale read-only file and a
  planted stale read-only directory were deleted by the sync - `ok:true`,
  copied 6, deleted_files 2, deleted_dirs 1, source_files 2173 - and the
  following `verify` reported 2173 = 2173 files with no missing, extra or
  different entries.
- Source immutability over 13 435 source files (excluding `.git`): 0
  differences in size, mtime and read-only attribute across a sync that
  deleted and re-copied a read-only source file. The mirrored copy came back
  byte-identical and kept the read-only attribute.
- Third-party license audit (`scripts\audit_build_licenses.py`): passes with
  8 named packages/optional dependencies and no review items. The upstream
  proxy_tools 0.1.0 BSD license text is bundled verbatim as
  `stage\licenses\proxy_tools-0.1.0-upstream-BSD-LICENSE.txt` (1 436 B) and
  pinned in the kit at `source\licenses\proxy_tools-0.1.0-BSD-LICENSE.txt`.
  The audit fails closed if that pinned text is missing or altered.
- Independent review: three specialist reviews (code reviewer, test engineer,
  security auditor) ran over the v0.2.7 change, and the six must-fix items
  they raised are closed in this build.

The kit has **no CI**. Every number above is a local run on one machine
(Windows 11, `py -3.12` = Python 3.12.3, pytest 8.3.5).

## Not independently observed

- The publishing agent did not independently observe the native GUI window
  interactions: no title-bar drag, edge or corner resize, preset dropdown,
  information tooltip or native Browse interaction was driven on Windows for
  this build. The offline Chromium interface test referenced in
  README-DISTRIBUTION.txt is not evidence of native window behaviour.
- The installer was not exercised on a second machine; the upgrade described
  above ran on the build machine.
- Google Drive cloud propagation was not checked. Drive for Desktop uploads
  asynchronously and RepoSync cannot verify it.
- The POSIX path of the new helpers is exercised by exactly one test, which
  cannot run on Windows.
- No product-owner acceptance statement is recorded for this build.

## Known open items

- The destination is still a Google Drive mirrored folder. DriveFS keeps
  re-applying the read-only bit and keeps uploading the snapshot, including
  `.git` and `evidence/`, until the user removes the folder in Drive's
  preferences.
- The kit folder is itself inside a Drive mirrored root, which is why the
  builder has to clear the read-only bit in its own build tree.
- The installed folder still carries leftovers from older installs
  (`app\reposync.py`, `app\__pycache__\`, `bin\Start-RepoSync.cmd`,
  `exe-build\build-venv\`) that the current kit never ships.

## Artifact SHA-256

- GUI: `2B8729822458E8C72431686B4CC64964CEFA94B8032A6137B2EEC94273CACD77` (13 734 290 B)
- CLI: `F8BCDD8A052DD907853411C55D707C1EE1679113550EC8218BEAEC356EF950A8` (13 014 312 B)
- Installer: `2B50585B085457D9D604C6F0899BA8A2ADE532237841D2D7339754B444793A66` (28 393 167 B, dated 2026-10-21 16:21:21)

The installer is unsigned, so SmartScreen may warn. Google Drive cloud
propagation is outside these checks.
The detailed checks are recorded in `VERIFICATION_v0.2.7.md`; the release notes
are in `CHANGELOG.md`.
