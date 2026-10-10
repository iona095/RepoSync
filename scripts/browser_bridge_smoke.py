"""Chrome UI interaction test backed by the real Python DesktopAPI.
No network, user files, Google Drive, or real Windows shell windows touched.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'source'))
from reposync_gui import DesktopAPI, make_html


def run():
 with tempfile.TemporaryDirectory(prefix='reposync_ui_smoke_') as td:
  root=Path(td)
  os.environ['REPOSYNC_HOME']=str(root/'config')
  a, b=root/'input',root/'mirror'
  a.mkdir()
  (a/'hello.txt').write_text('content v1')
  (a/'ignore').mkdir()
  (a/'ignore'/'ignore.txt').write_text('not selected')
  api=DesktopAPI()
  with sync_playwright() as play:
   browser=play.chromium.launch(headless=True, executable_path='/usr/bin/chromium', args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1343,'height':1119},device_scale_factor=1)
   errors=[]
   page.on('pageerror',lambda err: errors.append(str(err)))
   bridges=['list_profiles','save_profile','preview','verify','sync','browse_folder',
            'minimize_window','toggle_maximize','close_window']
   for name in bridges:
    # Python exposes native bridge methods; JS calls them through window.pywebview.api.
    page.expose_function('b_'+name,getattr(api,name))
   js='window.pywebview={api:{'+','.join(f'{n}:(...a)=>window.b_{n}(...a)' for n in bridges)+'}};window.confirm=()=>true;'
   page.evaluate(js)
   page.set_content(make_html(),wait_until='load')
   page.wait_for_function('document.querySelector("#ready").textContent === "Ready"')
   assert not page.locator('.profile').count()
   page.locator('#profile').fill('ui-demo')
   page.locator('#source').fill(str(a))
   page.locator('#destination').fill(str(b))
   page.locator('#include').fill('hello.txt')
   page.locator('#save').click()
   page.wait_for_function('document.querySelector("#status").textContent.startsWith("Saved profile")')
   page.locator('#preview').click()
   page.wait_for_function('document.querySelector("#status").textContent === "Preview complete."')
   assert '"hello.txt"' in page.locator('#result').inner_text()
   assert page.locator('.profile.active').count()==1
   # Verify icon and selected state are visually present.
   page.screenshot(path='/mnt/data/RepoSync_v0.2.1_Actual_Browser_Preflight.png')
   page.locator('#sync').click()
   page.wait_for_function('document.querySelector("#status").textContent === "Complete."')
   assert (b/'hello.txt').read_text()=='content v1'
   assert not (b/'ignore').exists()
   page.locator('#verify').click()
   page.wait_for_function('document.querySelector("#status").textContent === "Verification complete."')
   (a/'hello.txt').unlink()
   page.locator('#sync').click()
   page.wait_for_function('document.querySelector("#status").textContent === "Complete."')
   assert not (b/'hello.txt').exists()
   assert not errors,errors
   print('PASS: UI save → preview → exact sync → verify → delete (real Python API and Chromium JS)')
   browser.close()


if __name__=='__main__':run()
