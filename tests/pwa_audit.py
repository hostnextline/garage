import json
from playwright.sync_api import sync_playwright
IPHONE = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Mobile Safari/537.36'
with sync_playwright() as p:
    b = p.chromium.launch()
    for url in ['http://127.0.0.1:8088/']:
        c = b.new_context(viewport={'width': 412, 'height': 900}, user_agent=IPHONE, is_mobile=True, has_touch=True)
        pg = c.new_page(); pg.goto(url); pg.wait_for_timeout(3000)
        cdp = c.new_cdp_session(pg)
        print('manifest:', json.dumps(cdp.send('Page.getAppManifest'), ensure_ascii=False)[:800])
        print('installability errors:', cdp.send('Page.getInstallabilityErrors'))
        print('sw:', pg.evaluate("navigator.serviceWorker && navigator.serviceWorker.controller ? 'controller' : (navigator.serviceWorker ? 'registered?' : 'none')"))
        print('regs:', pg.evaluate("navigator.serviceWorker.getRegistrations().then(r => r.map(x => x.scope + ' ' + (x.active ? x.active.state : '-')))"))
        c.close()
    b.close()
