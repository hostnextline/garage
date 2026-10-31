"""Phone screenshots of photos/signature, extra work, parts to bring and truck stock (single-page version), light + dark."""
import sys, os, json
sys.argv = ['x']
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_parts.py'), encoding='utf8').read().split('with sync_playwright() as pw:')[0])
from PIL import Image
from playwright.sync_api import sync_playwright
seed2 = json.loads(json.dumps(seed))
seed2['jobs/j1']['extras'] = [{'id': 'x1', 'items': [{'desc': 'Disques de frein avant', 'price': 180, 'qty': 1}], 'note': 'Disques rainurés, sous le minimum.', 'total': 180, 'status': 'attente', 'at': 1793460000000, 'sentAt': 1793460100000, 'smsStatus': 'sent'}]
seed2['stock/c1__plaquettes-avant-d1089']['qty'] = 0
names = []
def shot(p, n, scheme): path = os.path.join(SC, 'w_%s_%s.png' % (n, scheme)); p.screenshot(path=path); names.append(path)
with sync_playwright() as pw:
    br = pw.chromium.launch()
    for scheme in ('light', 'dark'):
        c = br.new_context(viewport={'width': 390, 'height': 844}, timezone_id='America/Toronto', locale='fr-CA', has_touch=True, user_agent=IPHONE, color_scheme=scheme)
        p = c.new_page(); p.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness({'seed': seed2}, None)) if r.request.url.startswith('https://local.test/') else r.abort())
        p.goto('https://local.test/'); p.wait_for_timeout(700)
        go_job(p, 'j1')
        p.set_input_files('#pin-av', [os.path.join(SC, 'recu_test.jpg')]); p.wait_for_timeout(1800)
        p.set_input_files('#pin-ap', [os.path.join(SC, 'vin/vin_civic.png')]); p.wait_for_timeout(1500)
        p.evaluate("document.querySelector('#ph-fold').open = true"); p.click('#ph-fold [data-act="sig-open"]'); p.wait_for_selector('#sigpad')
        bb = p.locator('#sigpad').bounding_box(); p.mouse.move(bb['x'] + 40, bb['y'] + 120); p.mouse.down()
        for i in range(1, 40): p.mouse.move(bb['x'] + 40 + i * 7, bb['y'] + 110 - 45 * abs(((i % 8) - 4) / 4))
        p.mouse.up(); p.wait_for_timeout(200); shot(p, 'signer', scheme)
        p.click('#sig-save'); p.wait_for_timeout(800)
        go_job(p, 'j1'); p.evaluate("document.querySelector('#xp-fold').open = true; document.querySelector('#xp-fold').scrollIntoView({block:'start'}); window.scrollBy(0, -80)"); p.wait_for_timeout(300); shot(p, 'travaux', scheme)
        p.evaluate("document.querySelector('#ph-fold').open = true; document.querySelector('#ph-fold').scrollIntoView({block:'start'}); window.scrollBy(0, -80)"); p.wait_for_timeout(300); shot(p, 'photos', scheme)
        p.evaluate("document.querySelector('#veh-fold').open = true; document.querySelector('#speccard .bring').scrollIntoView({block:'center'})"); p.wait_for_timeout(300); shot(p, 'apporter', scheme)
        p.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'stock'; window.__garageApi.render(); window.scrollTo(0, 0); }"); p.wait_for_timeout(400); shot(p, 'stock', scheme)
        c.close()
    br.close()
for scheme in ('light', 'dark'):
    ims = [Image.open(n).convert('RGB').crop((0, 0, 390, 844)) for n in names if n.endswith('_%s.png' % scheme)]
    bg = (233, 222, 210) if scheme == 'light' else (30, 25, 21)
    out = Image.new('RGB', (24 + len(ims) * 414, 892), bg)
    for i, im in enumerate(ims): out.paste(im, (24 + i * 414, 24))
    out.save(os.path.join(SC, 'apercu_chantier_%s.png' % scheme))
print('ok', len(names))
