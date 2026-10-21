# Changelog

## 0.2.7 — 2026-10-21

### Fixed

- Read-only destination items on Windows no longer abort a sync. The read-only
  bit is cleared just-in-time on the exact path immediately before the
  mutation that failed, with a bounded retry (3 attempts).
- The source tree is never modified by that unlock, and attribute fidelity is
  kept: a read-only source file is still mirrored as a read-only file, and an
  up-to-date read-only destination file stays read-only, because the unlock
  happens only on the path being mutated.
- A genuine lock (a real Windows sharing violation) and a genuinely non-empty
  directory (WinError 145) still stop the sync with an error that names the
  exact path.
- A destination directory that contains a Google Drive managed scratch path
  (.tmp.driveupload / .tmp.drivedownload) is never removed.

### Changed

- The type-conflict path (a directory where the source has a file, and the
  reverse) now raises a named RepoSyncError instead of a raw PermissionError.
- A temp-file cleanup failure no longer masks the primary sync error.
- The agent CLI wrapper `reposync.cmd` is shipped from source instead of a
  stale staged leftover.
- The build script clears the read-only bit in its own build tree before each
  destructive step, re-scans and fails loudly naming the first path it could
  not clear, skips reparse points, and retries a failed destructive step.
- The packaged UI version label now matches the engine version.

### Added

- The upstream proxy_tools 0.1.0 BSD license text is bundled verbatim as
  `stage\licenses\proxy_tools-0.1.0-upstream-BSD-LICENSE.txt` (1 436 B) and
  pinned in the kit at `source\licenses\proxy_tools-0.1.0-BSD-LICENSE.txt`.
  The build license audit fails closed if the pinned text is missing or
  altered.
- Regression coverage for read-only destinations in
  `test_sources\test_readonly_destination.py`.

The agent CLI surface, the saved profile schema and the JSON output schema are
unchanged from v0.2.6.

## 0.2.6 — 2026-10-11

### Added

- Delete saved profiles with mandatory confirmation; source and destination
  folders are untouched. A changed profile snapshot blocks stale deletion.
- Profile count, always-visible sidebar scrollbar and duplicate-name protection.
- Persistent GUI preference for routine Sync confirmation, enabled by default.
  Unmanaged destination adoption still requires its separate confirmation.

### Fixed

- Frameless window resizing now tracks the Windows pointer at all eight edges
  and corners, with DPI-aware minimum dimensions.
- Redistribution includes the upstream proxy_tools 0.1.0 BSD license notice.

The mirroring engine and CLI behavior are unchanged apart from the version.
Google Drive Desktop temporary folder protection is retained.
