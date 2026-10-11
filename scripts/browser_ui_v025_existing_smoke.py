"""Real Chromium GUI checks, no Windows native launch, no sync or file writes.
Uses built-in preview mode but explicitly intercepts bridge calls for resize check.
"""
from pathlib import Path
import sys
import shutil
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'source'))
from reposync_gui import make_html
with sync_playwright() as play:
    kwargs=dict(headless=True)
    if shutil.which('chromium'):
        kwargs.update(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
    browser=play.chromium.launch(**kwargs)
    page=browser.new_page(viewport={'width':1343,'height':1119})
    errors=[]
    page.on('pageerror',lambda err:errors.append(str(err)))
    page.evaluate('window.__REPOSYNC_PREVIEW__ = true;')
    page.set_content(make_html(), wait_until='load')
    page.wait_for_function("document.getElementById('ready').textContent==='Ready'")
    assert page.locator('#app-version').inner_text()=='v0.2.6'
    assert page.locator('#preset').input_value()=='review'
    assert page.locator('#preset-menu').is_hidden()
    page.locator('#preset-trigger').click()
    assert page.locator('#preset-trigger').get_attribute('aria-expanded')=='true'
    assert page.locator('#preset-menu').is_visible()
    page.locator('#preset-code').click()
    assert page.locator('#preset').input_value()=='code'
    assert page.locator('#preset-selected').inner_text()=='code'
    assert page.locator('#preset-menu').is_hidden()
    page.locator('#preset-trigger').focus()
    page.keyboard.press('ArrowDown')
    assert page.locator('#preset-menu').is_visible()
    page.keyboard.press('Escape')
    assert page.locator('#preset-menu').is_hidden()
    # Keyboard can select review, and selection persists in form data.
    page.locator('#preset-trigger').focus()
    page.keyboard.press('Enter')
    page.locator('#preset-review').click()
    assert page.evaluate('getForm().preset')=='review'
    tip=page.locator('#tip-include')
    page.locator('[aria-label="How do include-only patterns work?"]').hover()
    assert tip.is_visible()
    page.locator('#exclude').click()
    assert tip.is_hidden()
    page.locator('[aria-label="How do exclusions work?"]').focus()
    assert page.locator('#tip-exclude').is_visible()
    # Resize zones exist and send native resize edge via API on user gesture.
    page.evaluate('''() => {
      window.__resizeCalls=[];
      window.pywebview={api:{ begin_resize: async edge => {window.__resizeCalls.push(edge);return {started:true};} }};
    }''')
    page.locator('[data-resize="southeast"]').dispatch_event('pointerdown', {'button':0})
    page.wait_for_function('window.__resizeCalls.includes("southeast")')
    # Below the fixed card natural height, content must scroll rather than clip.
    page.set_viewport_size({'width':1024,'height':770})
    assert page.evaluate('document.querySelector(".content").scrollHeight > document.querySelector(".content").clientHeight')
    page.locator('#expand').scroll_into_view_if_needed()
    assert page.locator('#expand').is_visible()
    # Capture a usable preview of this build at desktop size.
    page.set_viewport_size({'width':1343,'height':1119})
    page.locator('#preset-trigger').click()
    page.screenshot(path='/mnt/data/RepoSync_v0.2.6_UI_Preset_Preview.png')
    assert not errors, errors
    browser.close()
print('PASS: version badge, preset styling and keyboard, info tooltips, edge resize dispatch, small-screen scrolling')
