"""Real Chromium integration test: +6 saved profiles, custom scrollbar, confirm toggle.

No actual mirror or filesystem changes. Native bridge replaced by a stateful fake.
"""
from pathlib import Path
import shutil,sys
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'source'))
from reposync_gui import make_html

with sync_playwright() as p:
    kwargs={'headless':True}
    if shutil.which('chromium'):
        kwargs.update({'executable_path':shutil.which('chromium'),'args':['--no-sandbox']})
    browser=p.chromium.launch(**kwargs)
    page=browser.new_page(viewport={'width':1343,'height':1119})
    errors=[];dialogs=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def handle(d):
        dialogs.append({'type':d.type,'message':d.message})
        d.accept() if d.type=='confirm' else d.dismiss()
    page.on('dialog',handle)
    page.evaluate('''() => {
      window.__test={ profiles:{}, prefs:{schema:1,confirm_sync:true},previewOwner:'owned',syncCalls:0 };
      for(let i=1;i<=3;i++){const name='Profile'+i;window.__test.profiles[name]={name,source:'C:/Src/'+name,destination:'C:/Dst/'+name,preset:'review',include:[],exclude:[]};}
      window.pywebview={api:{
        list_profiles:async()=>JSON.parse(JSON.stringify(window.__test.profiles)),
        browse_folder:async()=>'',version:async()=>'0.2.6',
        get_preferences:async()=>({...window.__test.prefs}),
        set_preferences:async(data)=>{window.__test.prefs={schema:1,confirm_sync:data.confirm_sync};return {...window.__test.prefs}},
        save_profile:async(data,oldname)=>{
          if(window.__test.profiles[data.name] && data.name!==oldname)throw new Error('Profile already exists');
          window.__test.profiles[data.name]=data;return {ok:true,saved:data.name}
        },
        preview:async()=>({owner:window.__test.previewOwner,copy:[],delete_files:[],delete_dirs:[]}),
        sync:async()=>{window.__test.syncCalls++;return {ok:true}},
        verify:async()=>({ok:true})
      }};
    }''')
    page.set_content(make_html(),wait_until='load')
    page.wait_for_function("document.getElementById('ready').textContent==='Ready'")
    assert page.locator('#profile-count').inner_text()=='3 saved'
    assert page.locator('.profile').count()==3
    # Add 4th, 5th, 6th as user would, assert all persist in UI and API.
    for i in range(4,7):
        page.locator('#new').click()
        page.locator('#profile').fill('Profile'+str(i))
        page.locator('#source').fill('C:/Src/Profile'+str(i))
        page.locator('#destination').fill('C:/Dst/Profile'+str(i))
        page.locator('#save').click()
        page.wait_for_function(f"Object.keys(window.__test.profiles).length=={i}")
        assert page.locator('.profile').count()==i
        assert page.locator('#profile-count').inner_text()==f'{i} saved'
        assert page.locator('.profile.active').get_attribute('data-name')=='Profile'+str(i)
        # Newly saved item is actually visible in the scroll viewport.
        assert page.locator('.profile.active').evaluate('el=>{const a=el.getBoundingClientRect(),b=el.closest(".list").getBoundingClientRect();return a.top>=b.top && a.bottom<=b.bottom+2}')
    assert page.locator('#profile-scrollbar').is_visible()
    assert page.locator('#profile-scroll-thumb').is_visible()
    assert page.locator('#profiles').evaluate("el=>getComputedStyle(el).overflowY")=='auto'
    assert page.locator('#profiles').evaluate('el=>el.scrollHeight>el.clientHeight')
    # Custom visible scrollbar must actually control the list (mouse and keyboard).
    rail=page.locator('#profile-scrollbar')
    rail.click(position={'x':5,'y':5})
    assert page.locator('#profiles').evaluate('el=>el.scrollTop')==0
    rail.focus()
    page.keyboard.press('End')
    assert page.locator('#profiles').evaluate('el=>Math.abs(el.scrollTop-(el.scrollHeight-el.clientHeight))<2')
    page.keyboard.press('Home')
    assert page.locator('#profiles').evaluate('el=>el.scrollTop')==0
    # An attempted fourth save with existing name may not modify stored mapping.
    page.locator('#new').click()
    page.locator('#profile').fill('Profile1')
    page.locator('#source').fill('C:/Src/NOT_THE_SAME')
    page.locator('#destination').fill('C:/Dst/NOT_THE_SAME')
    page.locator('#save').click()
    page.wait_for_function("document.getElementById('status').textContent==='Cannot save profile'")
    assert page.evaluate("window.__test.profiles.Profile1.source")=='C:/Src/Profile1'
    assert page.locator('#profile-count').inner_text()=='6 saved'
    # Saved profile must be selected before sync; default asks once.
    page.locator('[data-name="Profile1"]').click()
    assert page.locator('#confirm-sync').is_checked()
    dialogs.clear()
    page.locator('#sync').click()
    page.wait_for_function('window.__test.syncCalls===1')
    assert len([d for d in dialogs if d['type']=='confirm'])==1
    # Turning off prompt persists via native API and hides only routine confirm.
    page.locator('#confirm-sync').uncheck(force=True)
    page.wait_for_function('window.__test.prefs.confirm_sync===false')
    dialogs.clear()
    page.locator('#sync').click()
    page.wait_for_function('window.__test.syncCalls===2')
    assert not dialogs
    # Explicit ownership adoption must still ask when prompt is OFF.
    page.evaluate("window.__test.previewOwner='unmanaged-populated'")
    page.locator('#sync').click()
    page.wait_for_function('window.__test.syncCalls===3')
    assert len([d for d in dialogs if d['type']=='confirm'])==1
    assert 'Adopting' in dialogs[0]['message']
    page.locator('#confirm-sync').check(force=True)
    page.wait_for_function('window.__test.prefs.confirm_sync===true')
    page.screenshot(path='/mnt/data/RepoSync_v0.2.6_Profile_Scroll_Preview.png')
    assert not errors,errors
    browser.close()
print('PASS: six profiles visible through scroll, no overwrite, persisted confirm toggle, ownership warning maintained')
