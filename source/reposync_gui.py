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

from reposync import (VERSION, RepoSyncError, base_dir, atomic_json, load_profiles, save_profiles, marker_state,
                      validate_paths, plan, slim_plan, sync, verify)


class DesktopAPI:
    """Small explicit JS bridge for interactive GUI use."""

    def __init__(self):
        self._window = None
        self._maximized = False
        from native_resize import NativeDragResize
        self._native_resizer = NativeDragResize()

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

    _RESIZE_EDGES = frozenset({'west', 'east', 'north', 'northwest',
                                'northeast', 'south', 'southwest', 'southeast'})

    def begin_resize(self, edge):
        """Start a real OS-level pointer drag for frameless Windows sizing."""
        if edge not in self._RESIZE_EDGES:
            raise RepoSyncError('Unknown resize edge')
        if sys.platform != 'win32' or self._window is None:
            raise RepoSyncError('Native resize only supported on Windows desktop.')
        if self._maximized:
            raise RepoSyncError('Restore the window before resizing.')
        try:
            hwnd = int(self._window.native.Handle.ToInt64())
            started = self._native_resizer.start(hwnd, edge)
            return {'started': bool(started)}
        except Exception as exc:
            raise RepoSyncError(f'Windows native resize failed: {exc}') from exc

    def close_window(self):
        if self._window is not None:
            self._window.destroy()
        return True

    def version(self):
        """Installed application/engine version for the visible UI badge."""
        return VERSION

    def list_profiles(self):
        return load_profiles()

    def get_preferences(self):
        """User-scoped UI preference, independent of profiles and CLI."""
        path = base_dir() / 'ui-preferences.json'
        if not path.exists():
            return {'schema': 1, 'confirm_sync': True}
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or data.get('schema') != 1
                    or type(data.get('confirm_sync')) is not bool):
                raise ValueError('invalid preference schema')
        except (OSError, ValueError) as exc:
            raise RepoSyncError('Cannot read UI preferences; routine confirmation will remain enabled') from exc
        return {'schema': 1, 'confirm_sync': data['confirm_sync']}

    def set_preferences(self, data):
        if not isinstance(data, dict) or type(data.get('confirm_sync')) is not bool:
            raise RepoSyncError('Invalid confirmation preference')
        result = {'schema': 1, 'confirm_sync': data['confirm_sync']}
        atomic_json(base_dir() / 'ui-preferences.json', result)
        return result

    def save_profile(self, data, original_name=''):
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
        # Prevent a new profile, or a rename, from silently overwriting an
        # unrelated existing profile. The selected profile name is an optimistic
        # concurrency guard; the CLI and schema remain unchanged.
        if name in profiles and original_name != name:
            raise RepoSyncError(f"Profile '{name}' already exists. Select it to edit, or choose another name.")
        profiles[name] = p
        save_profiles(profiles)
        return dict(ok=True, saved=name, message='Profile saved. No files copied.')

    def delete_profile(self, name, expected_profile):
        """Delete a SAVED PROFILE ENTRY only, never folders or mirror metadata.

        Match the selected profile snapshot to prevent a stale GUI from
        deleting a profile that another agent/session has since modified.
        """
        if not isinstance(name, str) or not name or not isinstance(expected_profile, dict):
            raise RepoSyncError('Select a saved profile to delete.')
        profiles = load_profiles()
        current = profiles.get(name)
        if current is None:
            raise RepoSyncError('Profile no longer exists. Refresh the list.')
        if current != expected_profile:
            raise RepoSyncError('Profile has changed since selection. Refresh before deleting.')
        del profiles[name]
        save_profiles(profiles)
        return {'ok': True, 'deleted': name,
                'message': 'Saved profile removed. Source and destination files were not touched.'}

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
