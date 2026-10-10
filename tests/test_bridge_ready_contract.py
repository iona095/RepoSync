"""Regression: only intentional API methods are visible to pywebview JS introspection."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
from reposync_gui import DesktopAPI


def test_native_window_is_private_in_bridge():
    api = DesktopAPI()
    native = object()
    api._window = native
    public = {key for key in dir(api) if not key.startswith('_')}
    assert 'window' not in public
    assert api._window is native
    assert {'browse_folder', 'list_profiles', 'save_profile', 'preview', 'sync', 'verify'}.issubset(public)


def test_ready_listener_is_attached_to_window_and_actions_start_disabled():
    s = (Path(__file__).resolve().parents[1] / 'source' / 'ui' / 'index.html').read_text()
    assert "window.addEventListener('pywebviewready',startup)" in s
    assert "document.addEventListener('pywebviewready'" not in s
    assert "function bridgeAvailable()" in s
    assert 'bridgeConnected=false' in s
