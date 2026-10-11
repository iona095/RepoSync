# Changelog

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
