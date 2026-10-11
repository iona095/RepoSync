# RepoSync v0.2.6 — focused regression and Windows acceptance

## Implemented

- Frameless window native pointer-drag resizing via Win32 `GetCursorPos`,
  `GetAsyncKeyState`, `GetWindowRect`, `GetDpiForWindow` and `SetWindowPos`.
  Previous asynchronous `WM_NCLBUTTONDOWN` method removed because it could
  report success but leave the window fixed. All eight edges/corners covered.
  Keeps minimum logical width 1000 and height 770; respects Windows DPI.
  No moving/resizing a maximized window.
- "Delete profile" button beside "New profile", enabled only for an existing
  selected profile, disabled during other operations and on a new profile.
  Separate, mandatory user confirmation even when routine Sync confirmation
  is disabled. Deletes only the named entry in profiles.json; does not touch
  source files, destination files, or the mirror metadata under destination.
  An expected-profile snapshot guard blocks stale concurrent edits.
- Visible app version 0.2.6; keeps original v0.2.5 palette and controls.

## Verification completed in Linux

- `python -m pytest -q test_sources`: **52 passed**.
- `node --check` on embedded JS: **PASS**.
- Chromium + real Python DesktopAPI bridge: **PASS**. Cancel and confirm
  Delete profile; profile count/selection changes; selected-profile buttons;
  source and destination files unchanged; native resize event dispatched.
- Win32 backend test with simulated user32 cursor & mouse button: **PASS**.
  Verified exact SetWindowPos dimensions and state cleanup after release.
- Mirror engine `reposync.py` diff to v0.2.5: **version string only**.
- No real user directories or Google Drive synchronized content used for tests.

## Still mandatory on Windows before release

1. Extract kit to Downloads, run Build-RepoSync-Installer.ps1 *without*
   -UseExistingExe; verify CLI --version is 0.2.6.
2. Close v0.2.5, launch freshly built `.build\pyinstaller-dist\RepoSync.exe`
   directly, NOT an old Start Menu shortcut.
3. On your Windows monitor, restore (unmaximize) then drag bottom-right corner
   slowly outwards and inwards; repeat right edge, bottom edge and top-left.
   Observe actual window bounds changing (not just the cursor icon).
   Check minimum size, maximize/restore, titlebar drag and content layout.
4. Select a disposable saved profile. "Delete profile" must be active.
   Cancel the prompt: profile remains. Confirm: entry disappears. Verify
   folders are untouched. For this test use a disposable profile only.
5. With "Confirm each sync" OFF, Delete profile must *still* confirm.
6. Run Test-RepoSync-Binaries.ps1 (disposable CLI sync/verify) and confirm
   existing OCMS-S, PixelCraft and Pixel-Nodes profiles survive the installer.
7. Run the installed version via Start Menu, check installer/uninstall behavior.
8. Keep public v0.2.4 GitHub release unchanged until v0.2.6 is accepted and
   redistribution license notices are cleared.

If window resizing still fails, provide Windows display scaling (100%/125% etc.)
and `%LOCALAPPDATA%\RepoSync\logs\webview-bridge.log` (review for sensitive paths).

## Publication follow-up - 2026-10-11

The owner confirmed Windows acceptance passed. See WINDOWS_ACCEPTANCE_v0.2.6.md
for current publication checks and artifact hashes. The missing proxy_tools notice
was added and the installer repackaged with byte-identical GUI and CLI binaries.
The earlier pending items above describe the original kit snapshot.
