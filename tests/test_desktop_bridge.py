"""Desktop API integration tests against disposable real folders, no GUI runtime."""
import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
import reposync
import reposync_gui


@pytest.fixture
def folders(tmp_path, monkeypatch):
    monkeypatch.setenv('REPOSYNC_HOME', str(tmp_path / 'configuration'))
    src, dst = tmp_path / 'source', tmp_path / 'destination'
    src.mkdir()
    (src / 'file.txt').write_text('old content')
    (src / 'test').mkdir()
    (src / 'test' / 'test.txt').write_text('test ignored by include-only')
    return src, dst


def test_bridge_preview_sync_verify_and_deletion(folders):
    src, dst = folders
    api = reposync_gui.DesktopAPI()
    profile = dict(name='demo', source=str(src), destination=str(dst), preset='review',
                   include=['file.txt'], exclude=['test'])
    assert api.save_profile(profile)['ok']
    assert api.list_profiles()['demo']['source'] == str(src)
    assert api.preview('demo')['copy'] == ['file.txt']
    with pytest.raises(reposync.RepoSyncError, match='confirmation'):
        api.sync('demo', confirmed=False)
    assert not dst.exists()
    out = api.sync('demo', confirmed=True)
    assert out['ok'] and (dst/'file.txt').read_text() == 'old content'
    assert api.verify('demo')['ok']
    (src/'file.txt').unlink()
    preview = api.preview('demo')
    assert preview['delete_files'] == ['file.txt']
    result = api.sync('demo', confirmed=True)
    assert result['ok'] and not (dst/'file.txt').exists()
    assert api.verify('demo')['ok']


def test_bridge_blocks_unowned_adoption_without_explicit_permission(folders):
    src, dst = folders
    dst.mkdir()
    (dst/'unrelated.txt').write_text('keep until approval')
    api = reposync_gui.DesktopAPI()
    api.save_profile(dict(name='demo',source=str(src),destination=str(dst),preset='review',exclude=[],include=[]))
    assert api.preview('demo')['owner']=='unmanaged-populated'
    with pytest.raises(reposync.RepoSyncError):
        api.sync('demo', confirmed=True,adopt=False)
    assert (dst/'unrelated.txt').read_text()=='keep until approval'


def test_html_is_embedded_and_window_contract(monkeypatch):
    html = reposync_gui.make_html()
    assert 'APP_ICON_DATA_URI' not in html
    assert 'data:image/png;base64,' in html
    assert 'pywebview-drag-region' in html
    for key in ('minimize_window','toggle_maximize','close_window','save_profile',
                'list_profiles','browse_folder','preview','verify','sync'):
        assert key in html
    class Win:
        def __init__(self): self.calls=[]
        def minimize(self): self.calls.append('minimize')
        def maximize(self): self.calls.append('maximize')
        def restore(self): self.calls.append('restore')
        def destroy(self): self.calls.append('destroy')
        def create_file_dialog(self, *args, **kwargs): return ('C:/Temp/demo',)
    w=Win()
    created={}
    class Web:
        class FileDialog: FOLDER=20
        def create_window(self, **kwargs):
            created.update(kwargs)
            return w
        def start(self, **kwargs):
            assert kwargs['gui']=='edgechromium'
            assert created['frameless'] is True
            assert created['easy_drag'] is False
            assert created['min_size'][0] >= 900
            api = created['js_api']
            assert not hasattr(api,'window')
            assert api._window is w
            assert api.browse_folder('')=='C:/Temp/demo'
            assert api.toggle_maximize()=={'maximized':True}
            assert api.toggle_maximize()=={'maximized':False}
            assert api.minimize_window()
            assert api.close_window()
            assert w.calls==['maximize','restore','minimize','destroy']
    monkeypatch.setitem(sys.modules,'webview',Web())
    reposync_gui.run_gui()
