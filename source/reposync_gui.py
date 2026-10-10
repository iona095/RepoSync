"""RepoSync desktop UI entry point — local HTML/CSS, native Windows WebView2.

No cloud authentication, CDN, listening HTTP server or mirror implementation here.
The existing reposync.py engine remains the only data-ownership authority.
"""
from __future__ import annotations

import base64
import logging
from logging.handlers import RotatingFileHandler
import json
import os
import sys
from pathlib import Path

from reposync import (VERSION, RepoSyncError, load_profiles, save_profiles, marker_state,
                      validate_paths, plan, slim_plan, sync, verify)


class DesktopAPI:
    """Small explicit JS bridge for interactive GUI use."""

    def __init__(self):
        self._window = None
        self._maximized = False

    def minimize_window(self):
        if self._window is not None:
            self._window.minimize()
        return True

    def toggle_maximize(self):
        if self._window is not None:
            if self._maximized:
                self._window.restore()
            else:
                self._window.maximize()
            self._maximized = not self._maximized
        return {"maximized": self._maximized}

    # Windows sizing hit tests for an intentionally frameless WinForms window.
    # Merely setting pywebview resizable=True is not enough on the WinForms
    # renderer; these codes ask Windows to enter its native move/size loop.
    _RESIZE_HIT_CODES = {
        'west': 10, 'east': 11, 'north': 12, 'northwest': 13,
        'northeast': 14, 'south': 15, 'southwest': 16, 'southeast': 17,
    }

    def begin_resize(self, edge):
        """Begin native edge/corner resize (user pointer down only, Windows)."""
        if edge not in self._RESIZE_HIT_CODES:
            raise RepoSyncError('Unknown resize edge')
        if sys.platform != 'win32' or self._window is None:
            raise RepoSyncError('Native resize only supported on Windows desktop.')
        # Do not expose the WinForms form via the public JS API.
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = int(self._window.native.Handle.ToInt64())
            if not hwnd:
                raise OSError('Window handle unavailable')
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            user32.ReleaseCapture.argtypes = []
            user32.ReleaseCapture.restype = wintypes.BOOL
            user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.SendMessageW.restype = wintypes.LPARAM
            user32.ReleaseCapture()
            # WM_NCLBUTTONDOWN: let Windows handle cursor tracking, DPI and
            # minimum window dimensions rather than resizing in JavaScript.
            user32.SendMessageW(hwnd, 0x00A1, self._RESIZE_HIT_CODES[edge], 0)
        except Exception as exc:
            raise RepoSyncError('Windows native resize failed') from exc
        return {'started': True}

    def close_window(self):
        if self._window is not None:
            self._window.destroy()
        return True

    def version(self):
        """Installed application/engine version for the visible UI badge."""
        return VERSION

    def list_profiles(self):
        return load_profiles()

    def save_profile(self, data):
        if not isinstance(data, dict):
            raise RepoSyncError('Invalid profile')
        name = str(data.get('name', '')).strip()
        if not name or name.startswith('.') or any(c in name for c in '/\\\r\n'):
            raise RepoSyncError('Enter a valid profile name')
        source, destination = validate_paths(str(data.get('source', '')),
                                             str(data.get('destination', '')))
        preset = data.get('preset', 'review')
        if preset not in ('review', 'code'):
            raise RepoSyncError('Unknown preset')
        excludes, includes = data.get('exclude', []), data.get('include', [])
        if not isinstance(excludes, list) or not isinstance(includes, list):
            raise RepoSyncError('Filter lists must be arrays')
        for values in (excludes, includes):
            if any(not isinstance(x, str) or '\n' in x or '\r' in x for x in values):
                raise RepoSyncError('Invalid filter pattern')
        p = dict(name=name, source=str(source), destination=str(destination),
                 preset=preset, exclude=excludes, include=includes)
        marker_state(p)
        profiles = load_profiles()
        profiles[name] = p
        save_profiles(profiles)
        return dict(ok=True, saved=name, message='Profile saved. No files copied.')

    def _saved(self, name):
        profiles = load_profiles()
        if name not in profiles:
            raise RepoSyncError('Save your profile before continuing')
        return profiles[name]

    def preview(self, name):
        return slim_plan(plan(self._saved(name)))

    def verify(self, name):
        return verify(self._saved(name))

    def sync(self, name, adopt=False, confirmed=False):
        if confirmed is not True:
            raise RepoSyncError('A manual confirmation is required to synchronize.')
        return sync(self._saved(name), yes=True, adopt=bool(adopt))

    def browse_folder(self, start=''):
        import webview
        if self._window is None:
            return ''
        win = self._window
        # Modern pywebview and pre-6 APIs expose slightly different enum styles.
        if hasattr(webview, 'FOLDER_DIALOG'):
            selected = win.create_file_dialog(webview.FOLDER_DIALOG, directory=start or '')
        else:
            selected = win.create_file_dialog(webview.FileDialog.FOLDER, directory=start or '')
        return (selected[0] if isinstance(selected, (list, tuple)) else selected) or ''


def make_html():
    base = Path(sys._MEIPASS) if getattr(sys, '_MEIPASS', None) else Path(__file__).resolve().parent
    html = (base / 'ui' / 'index.html').read_text(encoding='utf-8')
    icon = (base / 'ui' / 'RepoSync.png').read_bytes()
    return html.replace('APP_ICON_DATA_URI', 'data:image/png;base64,' + base64.b64encode(icon).decode())


def configure_bridge_diagnostics():
    """Capture pywebview injection errors locally; no configuration or content logged."""
    try:
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'RepoSync' / 'logs'
        base.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger('pywebview')
        handler = RotatingFileHandler(base / 'webview-bridge.log', maxBytes=256_000,
                                      backupCount=2, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return str(base / 'webview-bridge.log')
    except OSError:
        return None


def run_gui():
    configure_bridge_diagnostics()
    import webview
    api = DesktopAPI()
    api._window = webview.create_window(
        title='RepoSync — Manual Folder Mirror',
        html=make_html(),
        js_api=api,
        width=1343, height=1119,
        min_size=(1000, 770),
        frameless=True, easy_drag=False, shadow=True,
        resizable=True, background_color='#090e17',
    )
    # Never silently fall back to obsolete MSHTML: it cannot run this UI's JS.
    # Edge WebView2 Runtime is a documented prerequisite for Windows releases.
    webview.start(gui='edgechromium', debug=False)


if __name__ == '__main__':
    run_gui()
