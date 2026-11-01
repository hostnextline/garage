"""The trial version (the hosted « version rapide » and the claude.ai page) in English: its screens, nothing left in French."""
import json, re
from playwright.sync_api import sync_playwright
PAGE = open('/home/claude/garage/web/index.html', encoding='utf8').read()
with sync_playwright() as pl:
    b = pl.chromium.launch(); out = {}
    for w in (390, 1280):
        c = b.new_context(viewport={'width': w, 'height': 844}, timezone_id='America/Toronto', locale='en-CA')
        c.add_init_script("try{localStorage.setItem('gm.lang','en')}catch(e){}")
        p = c.new_page(); errs = []; p.on('pageerror', lambda e: errs.append(str(e)))
        p.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=PAGE) if r.request.url == 'https://local.test/' else r.abort())
        p.goto('https://local.test/#agenda'); p.wait_for_timeout(800)
        for t in ['jour', 'accueil', 'agenda', 'clients', 'factures', 'tresor', 'stock', 'reglages', 'plus', 'heures', 'dispos']:
            p.evaluate("location.hash = '%s'" % t); p.wait_for_timeout(500)
        for sel in ['[data-act="new"]', '[data-act="cl-new"]']:
            try: p.evaluate("location.hash = 'agenda'"); p.wait_for_timeout(300); p.locator(sel).first.click(timeout=2000); p.wait_for_timeout(600)
            except Exception: pass
        p.screenshot(path='i18n_trial_%d.png' % w)
        m = [x for x in p.evaluate("Object.keys(window.I18N.misses)") if re.search(r'[a-zà-ÿ]{3}', x)]
        out[w] = m; print(w, 'lang', p.evaluate("window.I18N.lang"), 'misses', len(m), 'errors', errs[:3])
        for x in m[:60]: print('   ', x[:140])
        c.close()
    b.close()
