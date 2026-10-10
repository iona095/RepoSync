# RepoSync v0.2.4 — Windows acceptance gate

Run on an actual Windows 11 machine with Edge WebView2 Runtime installed. A passing
Chromium mock and unit test is NOT evidence of native resize success.

1. Build without `-UseExistingExe` (both binaries MUST report 0.2.4).
2. Launch fresh `.build\pyinstaller-dist\RepoSync.exe` before installation.
3. Confirm `v0.2.4` badge; GUI profile list, Browse and native bridge ready.
4. Click Preset: dark popup must show `review` and `code` without a white/unstyled native menu.
   Test mouse selection, Enter/Arrow/Space/End/Home/Escape, Save/reload persistence.
5. Hover and keyboard-focus both `i` controls; readable tooltips must appear and disappear.
6. **Drag the RIGHT window edge, BOTTOM edge, BOTTOM-RIGHT corner and TOP-LEFT
   corner**; verify the window physically changes size on Windows, and the source
   fields stay usable. Also test titlebar drag, maximize and restore.
   If edges fail, STOP: do not install or claim resize is fixed; send diagnostic.
7. Reduce window to min ~1000×770; scroll to results and verify inputs are usable.
8. On a disposable folder pair: add profile, Preview, Sync, Verify; then remove
   test source file, Preview/Sync/Verify and confirm it disappears from destination.
9. Verify CLI `--version`, `list --json`, `preview --json`, `verify --json`.
10. Build installer, check profiles persist on upgrade, launch from Start Menu,
    then test clean uninstall and confirm profile configuration preserved.
11. Review third-party notices including `proxy_tools` before public distribution.

Public release remains PENDING until Windows testing and licensing gates pass.
