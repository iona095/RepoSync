"""v0.2.6 destructive-profile-only action and pure native geometry tests."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
from reposync import RepoSyncError
from reposync_gui import DesktopAPI, make_html
from native_resize import VALID_EDGES, new_rect


def test_delete_profile_only_removes_one_profile_and_never_touches_folders(tmp_path, monkeypatch):
    monkeypatch.setenv('REPOSYNC_HOME', str(tmp_path/'config'))
    a=tmp_path/'src'; b=tmp_path/'destination'; a.mkdir(); b.mkdir()
    (a/'source.txt').write_text('source must remain')
    (b/'keep.txt').write_text('mirror must remain')
    api=DesktopAPI()
    first={'name':'one','source':str(a),'destination':str(b),'preset':'review','exclude':[],'include':[]}
    second={'name':'two','source':str(a),'destination':str(tmp_path/'elsewhere'),'preset':'review','exclude':[],'include':[]}
    api.save_profile(first);api.save_profile(second)
    snapshot=api.list_profiles()['one']
    with pytest.raises(RepoSyncError,match='Select'):
        api.delete_profile('one',None)
    with pytest.raises(RepoSyncError,match='changed'):
        api.delete_profile('one',dict(snapshot,exclude=['new']))
    assert len(api.list_profiles())==2
    output=api.delete_profile('one',snapshot)
    assert output['ok'] and output['deleted']=='one'
    assert list(api.list_profiles())==['two']
    assert (a/'source.txt').read_text()=='source must remain'
    assert (b/'keep.txt').read_text()=='mirror must remain'
    with pytest.raises(RepoSyncError,match='no longer exists'):
        api.delete_profile('one',snapshot)
    assert list(DesktopAPI().list_profiles())==['two']


def test_delete_conflicts_with_stale_profile_snapshot(tmp_path,monkeypatch):
    monkeypatch.setenv('REPOSYNC_HOME',str(tmp_path/'cfg'))
    src=tmp_path/'src';src.mkdir()
    api=DesktopAPI()
    p={'name':'active','source':str(src),'destination':str(tmp_path/'dst'), 'preset':'review','exclude':[],'include':[]}
    api.save_profile(p)
    old=api.list_profiles()['active']
    api.save_profile(dict(p,exclude=['tests']),'active')
    with pytest.raises(RepoSyncError,match='changed'):
        api.delete_profile('active',old)
    assert api.list_profiles()['active']['exclude']==['tests']


def test_gui_delete_has_always_on_confirmation_and_resets_selection():
    html=make_html()
    assert 'id="delete-profile"' in html
    assert "if(!confirm(`Remove saved profile" in html
    assert "api('delete_profile',name,expected)" in html
    assert "selected='';fill(null);renderProfiles()" in html
    assert "$('delete-profile').disabled=busy||!enabled||!selected||!profiles[selected]" in html
    assert 'v0.2.6' in html


@pytest.mark.parametrize(('edge','delta','expected'),[
    ('east',(130,70),(10,20,1230,800)),
    ('west',(-140,70),(-130,20,1240,800)),
    ('south',(90,150),(10,20,1100,950)),
    ('north',(90,-60),(10,-40,1100,860)),
    ('southeast',(100,150),(10,20,1200,950)),
    ('southwest',(-100,150),(-90,20,1200,950)),
    ('northeast',(100,-150),(10,-130,1200,950)),
    ('northwest',(-100,-150),(-90,-130,1200,950)),
])
def test_native_geometry_all_edges(edge, delta, expected):
    assert new_rect((10,20,1110,820), *delta, edge, (1000,770))==expected


def test_native_geometry_clamps_minimum_with_anchored_opposite_corner():
    rect=(100,100,1300,1000)
    assert new_rect(rect,1000,0,'west',(1000,770))==(300,100,1000,900)
    assert new_rect(rect,-1000,0,'east',(1000,770))==(100,100,1000,900)
    assert new_rect(rect,0,1000,'north',(1000,770))==(100,230,1200,770)
    assert new_rect(rect,0,-1000,'south',(1000,770))==(100,100,1200,770)
    assert len(VALID_EDGES)==8


def test_native_drag_executes_win32_setwindowpos_and_releases_state(monkeypatch):
    import ctypes
    import time
    from ctypes import wintypes
    import native_resize as nr
    seen=[]
    class NativeFn:
        def __init__(self, fun): self.fun=fun; self.argtypes=None; self.restype=None
        def __call__(self, *args): return self.fun(*args)
    class MockWin32:
        def __init__(self):
            self.cursor_step=0
            self.button_step=0
            self.IsWindow=NativeFn(lambda hwnd: 1)
            self.IsZoomed=NativeFn(lambda hwnd: 0)
            self.GetWindowRect=NativeFn(self._get_window_rect)
            self.GetCursorPos=NativeFn(self._get_cursor_pos)
            self.GetAsyncKeyState=NativeFn(self._get_key_state)
            self.GetDpiForWindow=NativeFn(lambda hwnd: 96)
            self.SetWindowPos=NativeFn(lambda *args: seen.append(args) or 1)
        def _get_window_rect(self, hwnd, ptr):
            rect=ctypes.cast(ptr,ctypes.POINTER(wintypes.RECT)).contents
            rect.left=10;rect.top=20;rect.right=1210;rect.bottom=920
            return 1
        def _get_cursor_pos(self, ptr):
            pts=[(400,300),(450,340),(500,380)]
            x,y=pts[min(self.cursor_step,2)]
            self.cursor_step+=1
            point=ctypes.cast(ptr,ctypes.POINTER(wintypes.POINT)).contents
            point.x=x;point.y=y
            return 1
        def _get_key_state(self, virtual_key):
            self.button_step+=1
            return -32768 if self.button_step<=2 else 0
    fake=MockWin32()
    monkeypatch.setattr(nr.ctypes,'WinDLL',lambda *args,**kwargs:fake,raising=False)
    resizer=nr.NativeDragResize()
    assert resizer.start(12345,'southeast')
    deadline=time.monotonic()+1.0
    while resizer._active and time.monotonic()<deadline:
        time.sleep(.005)
    assert not resizer._active
    assert resizer._last_error is None
    assert len(seen)>=2, seen
    assert seen[0][2:6]==(10,20,1250,940)
    assert seen[-1][2:6]==(10,20,1300,980)
    assert all(call[-1]==0x0214 for call in seen)
