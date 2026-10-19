#!/usr/bin/env python3
"""Check the reviewed variable-font repertoire and real-stroke playback in Chromium.

Requires Playwright and /usr/bin/chromium. Does not make network requests.
"""

import base64
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
variable_dir = root / 'fonts/seal-individual-variable'
fixed_dir = root / 'fonts/seal-individual'
font_path = variable_dir / 'PanoramaGothicSealIndividualVariable.ttf'
registry = json.loads((root / 'design/quality/accepted-geometry.json').read_text())
expected_codepoints = sorted(int(g['codepoint'].removeprefix('U+'), 16) for g in registry['glyphs'])
assert expected_codepoints and len(expected_codepoints)==len(set(expected_codepoints)), 'Invalid reviewed repertoire'
slider_html = (variable_dir / 'weight-slider.html').read_text()
assert base64.b64encode(font_path.read_bytes()).decode('ascii') in slider_html, 'Slider embeds a stale font'
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1400, 'height': 1200})
    page.route('http://**/*', lambda route: route.abort())
    page.route('https://**/*', lambda route: route.abort())
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.set_content(slider_html)
    page.evaluate("async () => { await document.fonts.ready; await document.fonts.load('400 256px Seal',String.fromCodePoint(0x3d003)); }")
    data = page.evaluate('''() => {
      const samples=[];
      for(const weight of [300,400,600,700]) {
        const canvas=document.createElement('canvas'); canvas.width=400; canvas.height=400;
        const ctx=canvas.getContext('2d'); ctx.font=weight+' 256px Seal';
        const ch=String.fromCodePoint(0x3d003); ctx.fillText(ch,64,300);
        const rgba=ctx.getImageData(0,0,400,400).data;
        let pixels=0; for(let i=3;i<rgba.length;i+=4) if(rgba[i]>=128) pixels++;
        samples.push({weight,pixels,advance:ctx.measureText(ch).width});
      }
      return {
        embedded_variable_font_loaded:document.fonts.check('400 256px Seal',String.fromCodePoint(0x3d003)),
        glyph_count:document.querySelectorAll('#glyphs span').length,
        codepoints:Array.from(document.querySelectorAll('#glyphs span'),e=>e.textContent.codePointAt(0)),
        last_codepoint:document.querySelector('#glyphs span:last-child').textContent.codePointAt(0),
        default_weight:Number(document.querySelector('#weight').value),canvas_actual_font_ink:samples};
    }''')
    assert data['embedded_variable_font_loaded'] and data['default_weight']==400, data
    assert data['last_codepoint']==expected_codepoints[-1], data
    assert data['codepoints']==expected_codepoints, data
    data['all_expected_spans']=True
    samples = data['canvas_actual_font_ink']
    assert all(a['pixels'] < b['pixels'] for a,b in zip(samples,samples[1:])), samples
    assert all(s['advance']==256 for s in samples), samples
    page.locator('#weight').fill('600')
    page.locator('#weight').dispatch_event('input')
    assert page.locator('#number').inner_text()=='600'
    assert '600' in page.locator('#glyphs').evaluate('(e)=>getComputedStyle(e).fontVariationSettings')
    data.update(browser='Chromium / Playwright',live_weight_600_verified=True,
                javascript_errors=errors,font_sha256=hashlib.sha256(font_path.read_bytes()).hexdigest(),
                html_sha256=hashlib.sha256(slider_html.encode()).hexdigest(),embedded_font_matches_ttf=True)
    assert not errors, errors
    (variable_dir / 'browser-check.json').write_text(json.dumps(data,indent=2)+'\n')
    page.set_content((fixed_dir / 'stroke-playback.html').read_text())
    stroke = page.evaluate('''() => ({path_count:document.querySelectorAll('#ink path').length,
      width:Number(getComputedStyle(document.querySelector('#ink')).strokeWidth.replace('px','')),
      viewBox:document.querySelector('svg').getAttribute('viewBox').split(/\\s+/).map(Number)})''')
    assert stroke=={'path_count':4,'width':30,'viewBox':[0,0,1024,1024]},stroke
    page.locator('#show').check()
    assert page.locator('#guides').evaluate('(e)=>getComputedStyle(e).display')=='block'
    page.locator('#width').fill('22')
    page.locator('#width').dispatch_event('input')
    assert page.locator('#ink').evaluate('(e)=>getComputedStyle(e).strokeWidth')=='22px'
    page.locator('#play').click()
    assert page.evaluate('document.getAnimations().length')==4
    stroke.update(browser='Chromium / Playwright',centerlines_toggle=True,width_control=True,replay_animations=4,
                  html_sha256=hashlib.sha256((fixed_dir/'stroke-playback.html').read_bytes()).hexdigest(),javascript_errors=errors)
    assert not errors, errors
    (fixed_dir/'browser-check.json').write_text(json.dumps(stroke,indent=2)+'\n')
    browser.close()
print(f'Browser checks passed: embedded {len(expected_codepoints)}-glyph variable font, default400, live600, increasing weights, constant advances, real-stroke replay.')
