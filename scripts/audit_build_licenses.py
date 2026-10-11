"""Produce redistributable third-party notices from the Windows build venv.

This checks the known Python runtime dependencies, reports exact installed versions,
and copies on-disk installed license files. It is intentionally separate from the
UI/CLI engine and runs only during the developer's Windows build.
"""
from __future__ import annotations

import importlib.metadata as im
import pathlib
import shutil
import sys

# Runtime dependencies are the libraries bundled by pywebview on Windows.
# All must be free to distribute commercially; unknown or newly introduced
# runtime libraries must be reviewed before extending this list.
LICENSES = {
    'pywebview': ('BSD', 'BSD-3-Clause'),
    'pythonnet': ('MIT',),
    'clr_loader': ('MIT',),
    'bottle': ('MIT',),
    'proxy_tools': ('BSD', 'MIT'),
    'typing_extensions': ('PSF', 'Python Software Foundation', 'MIT'),
    'cffi': ('MIT',),
    'pycparser': ('BSD',),
}
OPTIONAL = {'typing_extensions', 'cffi', 'pycparser'}


def is_verified_clr_loader_mit(pkg, installed_license_paths):
    """Narrow fallback for clr_loader 0.3.1's missing metadata license label.

    The upstream project's LICENSE is MIT (pythonnet/clr-loader, October 2026).
    The installed distribution must supply its own matching legal text. Any
    other version, absent file, or modified/non-MIT content stays BLOCKED.
    """
    if pkg.version != '0.3.1':
        return False
    for path in installed_license_paths:
        try:
            data = path.read_text(encoding='utf-8-sig', errors='replace')
        except (OSError, UnicodeError):
            continue
        normalized = ' '.join(data.split()).lower()
        if (normalized.startswith('mit license')
                and 'benedikt reinartz' in normalized
                and 'permission is hereby granted, free of charge' in normalized
                and 'the above copyright notice and this permission notice shall be included' in normalized
                and 'the software is provided "as is"' in normalized):
            return True
    return False


def run(out):
    out.mkdir(parents=True, exist_ok=True)
    sections = [
        'RepoSync redistributable Python GUI dependency notices',
        'Generated at build time from installed Python environment.',
        'Runtime: Windows WebView2 Evergreen (provided by Microsoft, not bundled).',
        'WARNING: dependency license report is metadata-assisted; review staged',
        'license texts and PyInstaller build warnings before public distribution.',
        '',
    ]
    missing = []
    review = []
    for name, accepted in LICENSES.items():
        try:
            pkg = im.distribution(name)
        except im.PackageNotFoundError:
            if name not in OPTIONAL:
                missing.append(f'{name}: missing package')
            continue
        declared = (' '.join(filter(None, [pkg.metadata.get('License-Expression'), pkg.metadata.get('License')])) + ' ' +
                    ' '.join(pkg.metadata.get_all('Classifier', [])))
        metadata_approved = any(label.lower() in declared.lower() for label in accepted)
        installed_license_paths = []
        for entry in pkg.files or []:
            basename = pathlib.PurePosixPath(str(entry)).name.lower()
            if basename.startswith(('license', 'licence', 'copying')) and len(str(entry).split('/')) < 6:
                src = pathlib.Path(pkg.locate_file(entry))
                if src.is_file() and src.stat().st_size <= 1000000:
                    installed_license_paths.append(src)
        verified_mit_fallback = (name == 'clr_loader' and not metadata_approved
                                 and is_verified_clr_loader_mit(pkg, installed_license_paths))
        if not metadata_approved and not verified_mit_fallback:
            missing.append(f'{name} {pkg.version}: license evidence missing, incompatible, or changed: {declared[:150]}')
        copied = 0
        for src in installed_license_paths:
            suffix = ''.join(src.suffixes) or '.txt'
            target = out / f'{name}-{pkg.version}-{copied}{suffix}'
            shutil.copy2(src, target)
            copied += 1
        if name == 'proxy_tools' and copied == 0:
            # Verified upstream license for proxy_tools 0.1.0; installed wheel omits LICENSE.
            # It is distributed verbatim beside the application source, not downloaded at build time.
            vendor = pathlib.Path(__file__).resolve().parents[1] / 'source' / 'licenses' / 'proxy_tools-0.1.0-BSD-LICENSE.txt'
            if pkg.version == '0.1.0' and vendor.is_file():
                evidence = vendor.read_text(encoding='utf-8', errors='replace')
                normalized = ' '.join(evidence.split()).lower()
                if (normalized.startswith('the bsd license (bsd)')
                        and 'copyright (c) 2013 armin ronacher' in normalized
                        and 'copyright (c) 2014 jonathan tushman' in normalized
                        and 'redistributions in binary form must reproduce' in normalized
                        and 'disclaimer in the documentation' in normalized):
                    shutil.copy2(vendor, out / 'proxy_tools-0.1.0-upstream-BSD-LICENSE.txt')
                    sections.append('proxy_tools 0.1.0: original BSD license bundled from upstream '
                                    'https://github.com/jtushman/proxy_tools/blob/master/LICENSE.txt. '
                                    'Wheel includes license metadata but no LICENSE file.')
                    copied = 1
        if verified_mit_fallback:
            sections.append('clr_loader 0.3.1: MIT confirmed by installed distribution LICENSE '
                            '(metadata license label missing). Authoritative source: '
                            'https://github.com/pythonnet/clr-loader/blob/main/LICENSE ; '
                            'inspected installed license, bundled copy included.')
        sections.append(f'{name} {pkg.version}: license metadata: {declared[:350]} | copied texts: {copied}')
        if not copied:
            if name == 'proxy_tools':
                missing.append(f'{name} {pkg.version}: pinned upstream BSD license not verified or not bundled')
            else:
                review.append(f'{name}: no installed license text available; add authoritative license before public release')
    (out / 'BUILD-THIRD-PARTY-NOTICES.txt').write_text('\n'.join(sections + ['REVIEW ITEMS:'] + review)+'\n',encoding='utf-8')
    if missing:
        print('LICENSING GATE NEEDS REVIEW:')
        for problem in missing:
            print(' - ' + problem)
        return 2
    if review:
        print('NOTICE REVIEW REQUIRED before public redistribution:')
        for item in review:
            print(' - '+item)
    print('Runtime package license metadata gate passed:', len(LICENSES), 'named packages/optional dependencies')
    return 0


if __name__ == '__main__':
    if len(sys.argv)!=2:
        raise SystemExit('usage: audit_build_licenses.py OUTPUT_DIR')
    sys.exit(run(pathlib.Path(sys.argv[1])))
