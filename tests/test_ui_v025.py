"""v0.2.6 GUI contract regressions; no Windows shell/window or mirror writes."""
from pathlib import Path
import ctypes
import sys
from unittest import mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
import reposync_gui
from reposync import RepoSyncError


def test_preset_dropdown_tooltips_version_and_resize_zones():
    html=reposync_gui.make_html()
    assert 'app-version' in html and 'v0.2.6' in html
    assert 'id="preset-trigger"' in html and 'role="listbox"' in html
    assert '<select class="input" id="preset">' not in html
    assert 'data-resize="northwest"' in html
    assert 'data-resize="southeast"' in html
    assert 'role="tooltip"' in html and 'tip-exclude' in html and 'tip-include' in html
    assert 'overflow-y:auto' in html


def test_resize_only_accepts_known_edges():
    api=reposync_gui.DesktopAPI()
    for bad in ('', 'maximize', 'move', None, 'shell'):
        with pytest.raises(RepoSyncError, match='Unknown resize edge'):
            api.begin_resize(bad)
    for edge in api._RESIZE_EDGES:
        with pytest.raises(RepoSyncError, match='Windows desktop'):
            api.begin_resize(edge)


def test_native_resize_dispatch_uses_drag_worker_without_false_native_messages(monkeypatch):
    api = reposync_gui.DesktopAPI()
    class Handle:
        def ToInt64(self): return 0x123456
    api._window = type('Window', (), {'native': type('Native', (), {'Handle': Handle()})()})()
    calls = []
    monkeypatch.setattr(reposync_gui.sys, 'platform', 'win32')
    monkeypatch.setattr(api._native_resizer, 'start', lambda hwnd, edge: calls.append((hwnd,edge)) or True)
    for edge in api._RESIZE_EDGES:
        assert api.begin_resize(edge) == {'started': True}
    assert {edge for _,edge in calls} == api._RESIZE_EDGES
    assert all(hwnd==0x123456 for hwnd,_ in calls)
    api._maximized=True
    with pytest.raises(RepoSyncError, match='Restore'):
        api.begin_resize('southeast')


def test_public_bridge_never_exposes_native_window():
    bridge=reposync_gui.DesktopAPI()
    assert not hasattr(bridge,'window')
    assert 'begin_resize' in dir(bridge)
    assert 'version' in dir(bridge)
