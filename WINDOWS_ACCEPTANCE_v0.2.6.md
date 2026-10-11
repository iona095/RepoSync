# RepoSync v0.2.6 Windows acceptance

The product owner confirmed "windows acceptance passed" on 2026-10-11.
This is owner-reported acceptance of the supplied Windows build; the publishing
agent did not independently observe the native GUI or installation/uninstallation.

The supplied GUI and CLI executables were preserved byte-for-byte while the
installer was repackaged to include the missing proxy_tools BSD license notice.

## Publication checks performed on Windows

- Regression suite: `py -3.12 -X utf8 -m pytest -q tests` — 52 passed.
- Compiled CLI: version 0.2.6, profile creation, preview, manual sync,
  SHA-256 verification, stale-file deletion and preservation of a
  `.tmp.driveupload` scratch file passed on disposable workspace folders.
- Dependency license inventory generated from the original build environment;
  all eight listed runtime packages supplied license notices, including the
  pinned upstream proxy_tools 0.1.0 BSD notice.
- Inno Setup 7 compiled the repackaged installer successfully.

## Artifact SHA-256

- GUI: `3F00A05A431EB4D0CAFF98D23FC949FCB49F8342BE91C5EA109EEBE33E807182`
- CLI: `6C51AFD27E2C86388BB1F28CDC3699D60C6B6D604C56479A932828BCC202C6CA`
- Installer: `E7B47595790D6FC585275805E801F20FE7A73D14FA60A294FEB023AC2F064F03`

The installer is unsigned. Google Drive cloud propagation is outside these checks.
Historical kit checks are recorded in `VERIFICATION_v0.2.6.md`.
