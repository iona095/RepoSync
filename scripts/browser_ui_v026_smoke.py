"""Executable browser integration: native Python API, profile deletion, ordinary mirror."""
from pathlib import Path
import json, os, sys, tempfile
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'source'))
from reposync_gui import DesktopAPI, make_html

def run():
 with tempfile.TemporaryDirectory(prefix='reposync_v026_') as td:
  root=Path(td);os.environ['REPOSYNC_HOME']=str(root/'cfg')
  src,dst=root/'source',root/'destination';src.mkdir();dst.mkdir()
  (src/'original.txt').write_text('source untouched')
  (dst/'existing.txt').write_text('destination untouched')
  api=DesktopAPI()
  profile={'name':'temporary-profile','source':str(src),'destination':str(dst),'preset':'review','exclude':[], 'include':[]}
  api.save_profile(profile)
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1343,'height':1119})
   errors=[];dialogs=[];accept=False
   page.on('pageerror',lambda err: errors.append(str(err)))
   def confirm_handler(dialog):
    nonlocal accept
    dialogs.append((dialog.type,dialog.message))
    if dialog.type=='confirm' and accept: dialog.accept()
    else: dialog.dismiss()
   page.on('dialog',confirm_handler)
   for name in ['list_profiles','save_profile','delete_profile','preview','verify','sync',
                'get_preferences','set_preferences','version','browse_folder']:
    page.expose_function('b_'+name,getattr(api,name))
   bridge_names=['list_profiles','save_profile','delete_profile','preview','verify','sync',
                 'get_preferences','set_preferences','version','browse_folder']
   page.evaluate("window.pywebview={api:{"+','.join(f'{n}:(...a)=>window.b_{n}(...a)' for n in bridge_names)+"}}")
   page.set_content(make_html(),wait_until='load')
   page.wait_for_function("document.getElementById('ready').textContent==='Ready'")
   assert page.locator('#app-version').inner_text()=='v0.2.6'
   assert page.locator('#delete-profile').is_enabled()
   assert page.locator('#profile-count').inner_text()=='1 saved'
   # Disabled during new-profile form.
   page.locator('#new').click()
   assert page.locator('#delete-profile').is_disabled()
   page.locator('[data-name="temporary-profile"]').click()
   assert page.locator('#delete-profile').is_enabled()
   # Always requires confirmation, even with Sync confirm disabled.
   page.locator('#confirm-sync').uncheck(force=True)
   page.wait_for_function("document.getElementById('confirm-sync').checked===false")
   page.locator('#delete-profile').click()
   assert 'temporary-profile' in api.list_profiles() # canceled
   assert len(dialogs)==1 and 'folders/files will NOT be deleted' in dialogs[0][1]
   page.screenshot(path='/mnt/data/RepoSync_v0.2.6_Profile_Delete_Preview.png')
   accept=True
   page.locator('#delete-profile').click()
   page.wait_for_function("document.querySelector('#profile-count').textContent==='0 saved'")
   assert not api.list_profiles()
   assert page.locator('#delete-profile').is_disabled()
   assert (src/'original.txt').read_text()=='source untouched'
   assert (dst/'existing.txt').read_text()=='destination untouched'
   assert len(dialogs)==2
   # JS resize gesture dispatch without actual native Windows call.
   calls=[]
   page.expose_function('b_begin_resize',lambda edge:calls.append(edge) or {'started':True})
   page.evaluate("window.pywebview.api.begin_resize=(...a)=>window.b_begin_resize(...a)")
   page.locator('[data-resize="southeast"]').dispatch_event('pointerdown',{'button':0})
   page.wait_for_timeout(120)
   assert calls and calls[-1]=='southeast',calls
   page.screenshot(path='/mnt/data/RepoSync_v0.2.6_Delete_Complete.png')
   assert not errors,errors
   browser.close()
 print('PASS: actual Python profile delete with cancel/confirm, no folder changes, native resize event dispatch')

if __name__=='__main__':run()
