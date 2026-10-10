"""HTML/WebView JS late-injection smoke using real Chromium, no native Windows API.
Requires playwright installed and chromium browser downloaded. No mirror operations.
"""
from pathlib import Path
import shutil
from playwright.sync_api import sync_playwright
from reposync_gui import make_html

with sync_playwright() as p:
    browser_path = shutil.which("chromium") or shutil.which("chromium-browser")
    kwargs = {"headless": True}
    if browser_path:
        kwargs["executable_path"] = browser_path
        kwargs["args"] = ["--no-sandbox"]
    browser=p.chromium.launch(**kwargs)
    page=browser.new_page()
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content(make_html(),wait_until='load')
    assert page.locator('#browse-source').is_disabled()
    assert page.locator('#sync').is_disabled()
    assert page.locator('#ready').inner_text() == 'Connecting'
    calls=[]
    page.expose_function('fake_profiles',lambda: {'Test':{'name':'Test','source':'C:\\tmp\\src','destination':'C:\\tmp\\dst','preset':'review','include':[],'exclude':[]}})
    page.expose_function('fake_browse',lambda current: calls.append(current) or 'C:\\tmp\\picked')
    page.evaluate('''() => {
      window.pywebview={api:{list_profiles:()=>window.fake_profiles(),browse_folder:(s)=>window.fake_browse(s),sync:()=>({ok:true})}};
      window.dispatchEvent(new Event('pywebviewready'));
    }''')
    page.wait_for_function("document.getElementById('ready').textContent==='Ready'")
    assert page.locator('#browse-source').is_enabled()
    assert page.locator('.profile.active').count()==1
    page.locator('#browse-source').click()
    page.wait_for_function("document.getElementById('source').value==='C:\\\\tmp\\\\picked'")
    assert calls==['C:\\tmp\\src'],calls
    assert not errors,errors
    print('PASS: delayed native bridge event loads profiles, enables Browse, and routes browse to API')
    browser.close()
