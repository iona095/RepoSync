"""v0.2.4 GUI contract regressions; no Windows shell/window or mirror writes."""
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
    assert 'app-version' in html and 'v0.2.4' in html
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
    for edge in api._RESIZE_HIT_CODES:
        with pytest.raises(RepoSyncError, match='Windows desktop'):
            api.begin_resize(edge)


def test_native_resize_dispatch_maps_all_windows_hit_test_codes(monkeypatch):
    class HWND:
        def ToInt64(self): return 0x123456
    native=type('Native',(),{'Handle':HWND()})()
    api=reposync_gui.DesktopAPI()
    api._window=type('Window',(),{'native':native})()
    sent=[]
    class KernelFunc:
        def __init__(self, fn): self.fn=fn;self.argtypes=None;self.restype=None
        def __call__(self, *args): return self.fn(*args)
    class MockUser32:
        ReleaseCapture=KernelFunc(lambda :1)
        SendMessageW=KernelFunc(lambda *args:sent.append(args) or 0)
    monkeypatch.setattr(reposync_gui.sys,'platform','win32')
    # Stub OS DLL loading: assert only canonical kernel messages, no WinForms internals leaked to JS.
    monkeypatch.setattr(ctypes,'WinDLL',lambda *a,**k:MockUser32(),raising=False)
    for edge,code in api._RESIZE_HIT_CODES.items():
        assert api.begin_resize(edge)=={'started':True}
        assert sent[-1]==(0x123456,0xA1,code,0)


def test_public_bridge_never_exposes_native_window():
    bridge=reposync_gui.DesktopAPI()
    assert not hasattr(bridge,'window')
    assert 'begin_resize' in dir(bridge)
    assert 'version' in dir(bridge)
