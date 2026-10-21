"""v0.2.6 regression: visible profiles, overwrite guard, persistent and safe UI prefs."""
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'source'))
from reposync import RepoSyncError, VERSION
from reposync_gui import DesktopAPI, make_html


def test_four_plus_profiles_are_persistent_and_no_silent_collision(tmp_path,monkeypatch):
    monkeypatch.setenv('REPOSYNC_HOME',str(tmp_path/'config'))
    src=tmp_path/'source';src.mkdir()
    api=DesktopAPI()
    for i in range(1,7):
        p=dict(name=f'Profile{i}',source=str(src),destination=str(tmp_path/f'dst{i}'),preset='review',include=[],exclude=[])
        assert api.save_profile(p)['ok'] is True
    profiles=api.list_profiles()
    assert sorted(profiles)==[f'Profile{i}' for i in range(1,7)]
    original=profiles['Profile1'].copy()
    # New-profile or accidental rename to an existing name must NOT overwrite.
    collision=dict(original,destination=str(tmp_path/'wrong-destination'))
    with pytest.raises(RepoSyncError,match='already exists'):
        api.save_profile(collision,'Profile2')
    with pytest.raises(RepoSyncError,match='already exists'):
        api.save_profile(collision,'')
    assert api.list_profiles()['Profile1']==original
    assert len(api.list_profiles())==6
    # Explicit edit of selected profile is allowed.
    edited=dict(original,exclude=['tests'])
    api.save_profile(edited,'Profile1')
    assert api.list_profiles()['Profile1']['exclude']==['tests']
    assert len(api.list_profiles())==6


def test_prefs_default_persist_survive_corruption_and_reject_invalid(tmp_path,monkeypatch):
    monkeypatch.setenv('REPOSYNC_HOME',str(tmp_path/'config'))
    api=DesktopAPI()
    assert api.get_preferences()=={'schema':1,'confirm_sync':True}
    assert api.set_preferences({'confirm_sync':False})['confirm_sync'] is False
    assert DesktopAPI().get_preferences()['confirm_sync'] is False
    # No sync or source/destination changes occur when toggling preferences.
    assert list((tmp_path/'config').iterdir())==[tmp_path/'config'/'ui-preferences.json']
    for value in (None,0,'false',[],{}):
        with pytest.raises(RepoSyncError,match='Invalid confirmation'):
            api.set_preferences({'confirm_sync':value})
    assert DesktopAPI().get_preferences()['confirm_sync'] is False
    (tmp_path/'config'/'ui-preferences.json').write_text('invalid json',encoding='utf-8')
    with pytest.raises(RepoSyncError,match='routine confirmation will remain enabled'):
        api.get_preferences()


def test_html_has_visible_scroll_count_and_confirmation_is_independent():
    html=make_html()
    assert 'id="profile-count"' in html
    assert 'id="profile-scrollbar"' in html and 'updateProfileScroll' in html
    assert 'scrollIntoView' in html
    assert 'id="confirm-sync" checked disabled' in html
    assert "if(preferences.confirm_sync&&!confirm(desc))return" in html
    assert "summary.owner==='unmanaged-populated'&&!confirm(" in html
    assert "api('get_preferences')" in html and "api('set_preferences'" in html
    assert f'v{VERSION}' in html


def test_disabling_ui_confirm_does_not_bypass_native_confirmation(tmp_path,monkeypatch):
    monkeypatch.setenv('REPOSYNC_HOME',str(tmp_path/'cfg'))
    api=DesktopAPI()
    api.set_preferences({'confirm_sync':False})
    with pytest.raises(RepoSyncError,match='confirmation'):
        api.sync('no-such-profile',confirmed=False)
